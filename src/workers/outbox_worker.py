"""
Standalone Transactional Email Outbox Worker
AI Powered Smart Hospital Referral System - Phase 2 Task 2B

Provides:
- Dedicated worker process for asynchronous transactional email delivery
- Respects PostgreSQL SKIP LOCKED row concurrency, worker leases, and exponential backoff
- Single-loop execution protection to prevent duplicate worker threads on the same instance
- Graceful shutdown on SIGINT and SIGTERM
- Structured logging with privacy-conscious email masking
- Run-once mode for cron execution or automated testing
"""

import os
import sys
import time
import signal
import logging
import secrets
import argparse
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.database.db_manager import get_session_factory
from src.database.pg_models import WorkerHeartbeat
from src.services.email_outbox_service import (
    EmailOutboxService,
    DEFAULT_MAX_RETRIES,
    DEFAULT_LEASE_TIMEOUT_SECONDS,
)
from src.services.email_service import get_email_provider, BaseEmailProvider

logger = logging.getLogger("outbox_worker")

DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_STALE_HEARTBEAT_THRESHOLD = float(os.getenv("OUTBOX_STALE_HEARTBEAT_THRESHOLD", "30.0"))


class OutboxWorker:
    """
    Autonomous worker for processing transactional outbox emails.
    """

    def __init__(
        self,
        session_factory=None,
        email_provider: Optional[BaseEmailProvider] = None,
        worker_id: Optional[str] = None,
        batch_size: int = 10,
        poll_interval: float = 5.0,
        lease_timeout_seconds: int = DEFAULT_LEASE_TIMEOUT_SECONDS,
    ):
        self.session_factory = session_factory or get_session_factory()
        self.email_provider = email_provider or get_email_provider()
        self.worker_id = worker_id or f"worker_{os.getpid()}_{secrets.token_hex(4)}"
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.lease_timeout_seconds = lease_timeout_seconds

        self._stop_event = threading.Event()
        self._is_running = False
        self._lock = threading.Lock()

        global _ACTIVE_WORKER_INSTANCE
        _ACTIVE_WORKER_INSTANCE = self

        # Operational metrics tracking
        self.metrics: Dict[str, Any] = {
            "worker_id": self.worker_id,
            "total_passes": 0,
            "total_processed": 0,
            "total_succeeded": 0,
            "total_failed": 0,
            "total_reclaimed": 0,
            "last_pass_at": None,
            "last_error": None,
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Return operational worker statistics."""
        return {**self.metrics, "is_running": self._is_running}

    def stop(self, *args, **kwargs):
        """Signal the worker to stop gracefully."""
        logger.info("Worker %s received stop signal. Shutting down gracefully...", self.worker_id)
        self._stop_event.set()
        try:
            self._record_heartbeat(status="STOPPED")
        except Exception:
            pass

    def _record_heartbeat(
        self,
        status: str = "RUNNING",
        processed: int = 0,
        failed: int = 0,
        duration_seconds: float = 0.0,
        last_error: Optional[str] = None,
    ):
        """
        Record worker heartbeat in PostgreSQL worker_heartbeats table.
        This provides a reliable, cross-container shared heartbeat mechanism.
        """
        now = datetime.now(timezone.utc)
        session = self.session_factory()
        try:
            hb = session.query(WorkerHeartbeat).filter_by(worker_name="outbox_worker").one_or_none()
            if hb is None:
                hb = WorkerHeartbeat(
                    worker_name="outbox_worker",
                    worker_id=self.worker_id,
                    status=status,
                    last_heartbeat=now,
                    processed_total=processed,
                    failed_total=failed,
                    batch_size=self.batch_size,
                    duration_seconds=round(duration_seconds, 3),
                    last_success_at=now if failed == 0 and not last_error else None,
                    last_error_at=now if last_error else None,
                    last_error=last_error[:500] if last_error else None,
                )
                session.add(hb)
            else:
                hb.worker_id = self.worker_id
                hb.status = status
                hb.last_heartbeat = now
                hb.processed_total += processed
                hb.failed_total += failed
                hb.batch_size = self.batch_size
                hb.duration_seconds = round(duration_seconds, 3)
                if failed == 0 and not last_error:
                    hb.last_success_at = now
                if last_error:
                    hb.last_error_at = now
                    hb.last_error = last_error[:500]
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning("Failed to record outbox worker heartbeat: %s", exc)
        finally:
            session.close()

    def run_once(self) -> Dict[str, Any]:
        """
        Executes a single processing pass:
        1. Reclaims expired processing leases.
        2. Claims and processes candidate outbox events.
        3. Commits transaction and returns summary metrics.
        """
        start_time = time.time()
        session = self.session_factory()
        outbox_svc = EmailOutboxService(session, self.email_provider)
        try:
            # 1. Reclaim any expired leases from abandoned/crashed workers
            reclaimed = outbox_svc.reclaim_expired_leases(
                lease_timeout_seconds=self.lease_timeout_seconds
            )
            session.commit()

            # 2. Process pending & eligible retry events with SKIP LOCKED
            result = outbox_svc.process_outbox(
                batch_size=self.batch_size,
                worker_id=self.worker_id,
                lease_timeout_seconds=self.lease_timeout_seconds,
            )
            session.commit()

            duration = time.time() - start_time
            total_reclaimed = reclaimed + result.get("reclaimed", 0)
            summary = {
                "worker_id": self.worker_id,
                "reclaimed": total_reclaimed,
                "processed": result["processed"],
                "succeeded": result["succeeded"],
                "failed": result["failed"],
            }

            # Update cumulative metrics
            self.metrics["total_passes"] += 1
            self.metrics["total_processed"] += result["processed"]
            self.metrics["total_succeeded"] += result["succeeded"]
            self.metrics["total_failed"] += result["failed"]
            self.metrics["total_reclaimed"] += total_reclaimed
            self.metrics["last_pass_at"] = datetime.now(timezone.utc).isoformat()
            self.metrics["last_error"] = None

            if result["processed"] > 0 or total_reclaimed > 0:
                logger.info(
                    "OutboxWorker %s pass: processed=%d, succeeded=%d, failed=%d, reclaimed=%d",
                    self.worker_id,
                    result["processed"],
                    result["succeeded"],
                    result["failed"],
                    total_reclaimed,
                )

            self._record_heartbeat(
                status="RUNNING",
                processed=result["processed"],
                failed=result["failed"],
                duration_seconds=duration,
            )
            return summary

        except Exception as exc:
            session.rollback()
            duration = time.time() - start_time
            self.metrics["total_passes"] += 1
            self.metrics["last_error"] = str(exc)
            self.metrics["last_pass_at"] = datetime.now(timezone.utc).isoformat()
            logger.error("OutboxWorker %s encountered unhandled error during pass: %s", self.worker_id, exc)
            self._record_heartbeat(
                status="FAILED",
                processed=0,
                failed=1,
                duration_seconds=duration,
                last_error=str(exc),
            )
            return {
                "worker_id": self.worker_id,
                "error": str(exc),
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "reclaimed": 0,
            }
        finally:
            session.close()

    def run_forever(self):
        """
        Continuously polls the outbox queue until stop() is called.
        Protected against concurrent duplicate loops on the same worker instance.
        """
        with self._lock:
            if self._is_running:
                raise RuntimeError(f"Worker {self.worker_id} is already running a loop.")
            self._is_running = True

        logger.info(
            "OutboxWorker %s started (poll_interval=%.1fs, batch_size=%d, lease_timeout=%ds).",
            self.worker_id,
            self.poll_interval,
            self.batch_size,
            self.lease_timeout_seconds,
        )

        try:
            self._record_heartbeat(status="RUNNING")
            while not self._stop_event.is_set():
                self.run_once()
                # Sleep in short increments for responsive shutdown
                sleep_start = time.time()
                while time.time() - sleep_start < self.poll_interval:
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.2)
        finally:
            with self._lock:
                self._is_running = False
            self._record_heartbeat(status="STOPPED")
            logger.info("OutboxWorker %s stopped cleanly.", self.worker_id)


def setup_signal_handlers(worker: OutboxWorker):
    """Attach SIGINT and SIGTERM handlers to signal graceful shutdown."""
    def _handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Caught signal %s (%d). Triggering graceful shutdown...", sig_name, signum)
        worker.stop()

    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except (ValueError, AttributeError):
        # In non-main threads signal handlers may not be allowed
        pass


def check_worker_health(
    session_factory=None,
    stale_threshold_seconds: float = DEFAULT_STALE_HEARTBEAT_THRESHOLD,
) -> bool:
    """
    Container healthcheck probe:
    1. Verifies database connectivity.
    2. Verifies that the outbox_worker heartbeat is fresh and in RUNNING status.
    Returns True if healthy, False otherwise.
    """
    try:
        factory = session_factory or get_session_factory()
        with factory() as session:
            # 1. DB ping
            from sqlalchemy import text
            session.execute(text("SELECT 1"))

            # 2. Check heartbeat
            hb = session.query(WorkerHeartbeat).filter_by(worker_name="outbox_worker").one_or_none()
            if not hb:
                logger.warning("Healthcheck: No worker_heartbeats row found for outbox_worker.")
                return False

            now = datetime.now(timezone.utc)
            if not hb.last_heartbeat:
                logger.warning("Healthcheck: Heartbeat timestamp missing.")
                return False

            last_hb = hb.last_heartbeat
            if last_hb.tzinfo is None:
                last_hb = last_hb.replace(tzinfo=timezone.utc)

            age = (now - last_hb).total_seconds()
            if age > stale_threshold_seconds:
                logger.warning(
                    "Healthcheck: Outbox worker heartbeat is stale (age=%.1fs > threshold=%.1fs).",
                    age,
                    stale_threshold_seconds,
                )
                return False

            if hb.status != "RUNNING":
                logger.warning("Healthcheck: Outbox worker status is '%s', expected 'RUNNING'.", hb.status)
                return False

            return True
    except Exception as exc:
        logger.error("Healthcheck probe failed with exception: %s", exc)
        return False


def main():
    """CLI entrypoint for standalone outbox worker process."""
    parser = argparse.ArgumentParser(description="Standalone Transactional Outbox Worker")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("OUTBOX_BATCH_SIZE", "10")),
        help="Maximum outbox events to fetch per batch (default: 10)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("OUTBOX_POLL_INTERVAL", "5.0")),
        help="Polling interval in seconds between passes (default: 5.0)",
    )
    parser.add_argument(
        "--lease-timeout",
        type=int,
        default=int(os.getenv("OUTBOX_LEASE_TIMEOUT", str(DEFAULT_LEASE_TIMEOUT_SECONDS))),
        help="Processing lease duration in seconds before recovery (default: 300)",
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default=None,
        help="Optional custom worker identifier tag",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Execute a single pass and exit (ideal for cron or test harnesses)",
    )
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Check worker health via database heartbeat and exit (0=healthy, 1=unhealthy)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=os.getenv("LOG_LEVEL", "INFO").upper(),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )

    if args.healthcheck:
        is_healthy = check_worker_health()
        sys.exit(0 if is_healthy else 1)

    worker = OutboxWorker(
        worker_id=args.worker_id,
        batch_size=args.batch_size,
        poll_interval=args.interval,
        lease_timeout_seconds=args.lease_timeout,
    )

    setup_signal_handlers(worker)

    if args.run_once:
        logger.info("Executing OutboxWorker in run-once mode...")
        summary = worker.run_once()
        print(f"Pass complete: {summary}")
        sys.exit(0 if summary.get("failed", 0) == 0 else 1)
    else:
        worker.run_forever()


_ACTIVE_WORKER_INSTANCE: Optional["OutboxWorker"] = None


def get_active_worker_metrics() -> Dict[str, Any]:
    """Retrieve operational metrics from the active in-process outbox worker (if running)."""
    global _ACTIVE_WORKER_INSTANCE
    if _ACTIVE_WORKER_INSTANCE is not None:
        return _ACTIVE_WORKER_INSTANCE.get_metrics()
    return {
        "status": "NOT_RUNNING_IN_PROCESS",
        "is_running": False,
        "message": "Outbox worker runs as a dedicated standalone background process.",
    }


if __name__ == "__main__":
    main()
