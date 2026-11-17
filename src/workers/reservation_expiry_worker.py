"""
Standalone Automated Bed Reservation Expiry Worker
AI Powered Smart Hospital Referral System - Phase 4D-1

Provides:
- Autonomous background worker to detect and expire overdue bed reservations
- Direct integration with authoritative PostgreSQL database time
- Row-level locking (SELECT ... FOR UPDATE SKIP LOCKED) for multi-worker concurrency
- Category-specific inventory restoration (General, ICU, Emergency)
- Atomic batch processing with sub-transaction savepoint isolation
- PostgreSQL-backed worker heartbeats for cross-container observability
- Graceful shutdown on SIGINT and SIGTERM
- Configurable batch size, poll interval, and error backoff
- CLI entrypoint and container healthcheck (--healthcheck)
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
from src.database.pg_repository import PgReferralRepository
from src.database.pg_models import WorkerHeartbeat

logger = logging.getLogger("reservation_expiry_worker")

DEFAULT_BATCH_SIZE = 100
DEFAULT_POLL_INTERVAL = 30.0
DEFAULT_MAX_BACKOFF = 300.0  # 5 minutes
DEFAULT_STALE_HEARTBEAT_THRESHOLD = 90.0  # 3x poll interval


class ReservationExpiryWorker:
    """
    Autonomous worker for detecting and expiring overdue bed reservations.
    """

    def __init__(
        self,
        session_factory=None,
        worker_id: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
    ):
        self.session_factory = session_factory or get_session_factory()
        self.worker_id = worker_id or f"expiry_worker_{os.getpid()}_{secrets.token_hex(4)}"
        self.batch_size = max(1, batch_size)
        self.poll_interval = max(0.5, poll_interval)
        self.max_backoff = max(5.0, max_backoff)

        self._stop_event = threading.Event()
        self._is_running = False
        self._lock = threading.Lock()
        self._consecutive_errors = 0

        global _ACTIVE_EXPIRY_WORKER_INSTANCE
        _ACTIVE_EXPIRY_WORKER_INSTANCE = self

        self.metrics: Dict[str, Any] = {
            "worker_id": self.worker_id,
            "total_passes": 0,
            "total_processed": 0,
            "total_succeeded": 0,
            "total_failed": 0,
            "last_pass_at": None,
            "last_success_at": None,
            "last_error": None,
            "last_error_at": None,
            "last_duration_seconds": 0.0,
            "batch_size": self.batch_size,
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Return in-memory operational metrics."""
        return {**self.metrics, "is_running": self._is_running}

    def stop(self, *args, **kwargs):
        """Signal the worker to stop gracefully."""
        logger.info("ReservationExpiryWorker %s received stop signal. Shutting down gracefully...", self.worker_id)
        self._stop_event.set()

    def record_heartbeat(
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
            hb = session.query(WorkerHeartbeat).filter_by(worker_name="reservation_expiry_worker").one_or_none()
            if hb is None:
                hb = WorkerHeartbeat(
                    worker_name="reservation_expiry_worker",
                    worker_id=self.worker_id,
                    status=status,
                    last_heartbeat=now,
                    processed_total=processed,
                    failed_total=failed,
                    batch_size=self.batch_size,
                    duration_seconds=round(duration_seconds, 3),
                    last_success_at=now if failed == 0 and not last_error else None,
                    last_error_at=now if last_error else None,
                    last_error=last_error,
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
                if last_error:
                    hb.last_error = last_error
                    hb.last_error_at = now
                elif processed > 0 or failed == 0:
                    hb.last_success_at = now
                    hb.last_error = None
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning("Could not persist worker heartbeat to database: %s", exc)
        finally:
            session.close()

    def run_once(self) -> Dict[str, Any]:
        """
        Executes a single processing pass:
        1. Opens short-lived PostgreSQL session.
        2. Queries and expires batch of overdue reservations with FOR UPDATE SKIP LOCKED.
        3. Updates metrics and writes heartbeat.
        4. Handles transient database errors with bounded backoff.
        """
        start_time = time.perf_counter()
        session = None
        now_utc = datetime.now(timezone.utc).isoformat()

        try:
            session = self.session_factory()
            repo = PgReferralRepository(session)
            result = repo.process_expired_reservations_batch(
                batch_size=self.batch_size,
                user_id=self.worker_id,
            )
            duration = time.perf_counter() - start_time

            self._consecutive_errors = 0
            self.metrics["total_passes"] += 1
            self.metrics["total_processed"] += result["processed"]
            self.metrics["total_succeeded"] += result["succeeded"]
            self.metrics["total_failed"] += result["failed"]
            self.metrics["last_pass_at"] = now_utc
            self.metrics["last_duration_seconds"] = round(duration, 3)
            if result["failed"] == 0:
                self.metrics["last_success_at"] = now_utc

            self.record_heartbeat(
                status="RUNNING",
                processed=result["succeeded"],
                failed=result["failed"],
                duration_seconds=duration,
                last_error=None,
            )

            if result["processed"] > 0:
                logger.info(
                    "ReservationExpiryWorker %s pass: processed=%d, succeeded=%d, failed=%d in %.2fs",
                    self.worker_id,
                    result["processed"],
                    result["succeeded"],
                    result["failed"],
                    duration,
                )

            return {
                "worker_id": self.worker_id,
                "processed": result["processed"],
                "succeeded": result["succeeded"],
                "failed": result["failed"],
                "duration_seconds": round(duration, 3),
            }

        except Exception as exc:
            duration = time.perf_counter() - start_time
            self._consecutive_errors += 1
            err_msg = str(exc)

            self.metrics["total_passes"] += 1
            self.metrics["total_failed"] += 1
            self.metrics["last_error"] = err_msg
            self.metrics["last_error_at"] = now_utc
            self.metrics["last_duration_seconds"] = round(duration, 3)

            logger.error(
                "ReservationExpiryWorker %s error during pass (error #%d): %s",
                self.worker_id,
                self._consecutive_errors,
                exc,
            )

            try:
                self.record_heartbeat(
                    status="RUNNING",
                    processed=0,
                    failed=1,
                    duration_seconds=duration,
                    last_error=err_msg,
                )
            except Exception:
                pass

            return {
                "worker_id": self.worker_id,
                "error": err_msg,
                "processed": 0,
                "succeeded": 0,
                "failed": 1,
                "duration_seconds": round(duration, 3),
            }
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    def run_forever(self):
        """
        Continuously polls for expired reservations until stop() is called.
        """
        with self._lock:
            if self._is_running:
                raise RuntimeError(f"Worker {self.worker_id} is already running a loop.")
            self._is_running = True

        logger.info(
            "ReservationExpiryWorker %s started (poll_interval=%.1fs, batch_size=%d).",
            self.worker_id,
            self.poll_interval,
            self.batch_size,
        )

        try:
            while not self._stop_event.is_set():
                res = self.run_once()

                # Calculate adaptive sleep interval with error backoff
                current_interval = self.poll_interval
                if self._consecutive_errors > 0:
                    # Exponential backoff capped at max_backoff
                    backoff = min(self.max_backoff, self.poll_interval * (2 ** min(self._consecutive_errors, 5)))
                    current_interval = backoff
                    logger.warning(
                        "ReservationExpiryWorker backing off for %.1fs after %d consecutive errors.",
                        current_interval,
                        self._consecutive_errors,
                    )

                sleep_start = time.time()
                while time.time() - sleep_start < current_interval:
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.2)
        finally:
            with self._lock:
                self._is_running = False
            # Record STOPPED state in database
            self.record_heartbeat(status="STOPPED")
            logger.info("ReservationExpiryWorker %s stopped cleanly.", self.worker_id)


def setup_signal_handlers(worker: ReservationExpiryWorker):
    """Attach SIGINT and SIGTERM handlers for graceful termination."""
    def _handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Caught signal %s (%d). Triggering graceful worker shutdown...", sig_name, signum)
        worker.stop()

    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except (ValueError, AttributeError):
        pass


def check_worker_health(stale_threshold_seconds: float = DEFAULT_STALE_HEARTBEAT_THRESHOLD) -> bool:
    """
    Container healthcheck probe:
    1. Verifies database connectivity.
    2. Verifies that the reservation_expiry_worker heartbeat is fresh and in RUNNING status.
    Returns True if healthy, False otherwise.
    """
    try:
        SessionFactory = get_session_factory()
        with SessionFactory() as session:
            # 1. DB ping
            from sqlalchemy import text
            session.execute(text("SELECT 1"))

            # 2. Check heartbeat
            hb = session.query(WorkerHeartbeat).filter_by(worker_name="reservation_expiry_worker").one_or_none()
            if not hb:
                logger.warning("Healthcheck: No worker_heartbeats row found for reservation_expiry_worker.")
                return False

            now = datetime.now(timezone.utc)
            if not hb.last_heartbeat:
                logger.warning("Healthcheck: Heartbeat timestamp missing.")
                return False

            age = (now - hb.last_heartbeat).total_seconds()
            if age > stale_threshold_seconds:
                logger.warning("Healthcheck: Worker heartbeat is stale (age=%.1fs > threshold=%.1fs).", age, stale_threshold_seconds)
                return False

            if hb.status != "RUNNING":
                logger.warning("Healthcheck: Worker status is '%s', expected 'RUNNING'.", hb.status)
                return False

            return True
    except Exception as exc:
        logger.error("Healthcheck probe failed with exception: %s", exc)
        return False


_ACTIVE_EXPIRY_WORKER_INSTANCE: Optional[ReservationExpiryWorker] = None


def get_active_expiry_worker_metrics() -> Dict[str, Any]:
    """Retrieve in-process metrics if running in the same Python process."""
    global _ACTIVE_EXPIRY_WORKER_INSTANCE
    if _ACTIVE_EXPIRY_WORKER_INSTANCE is not None:
        return _ACTIVE_EXPIRY_WORKER_INSTANCE.get_metrics()
    return {
        "status": "NOT_RUNNING_IN_PROCESS",
        "is_running": False,
        "message": "Reservation expiry worker runs as a dedicated standalone background process.",
    }


def main():
    """CLI entrypoint for standalone reservation expiry worker."""
    parser = argparse.ArgumentParser(description="Standalone Automated Bed Reservation Expiry Worker")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("RESERVATION_EXPIRY_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))),
        help=f"Maximum expired reservations to process per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("RESERVATION_EXPIRY_POLL_INTERVAL", str(DEFAULT_POLL_INTERVAL))),
        help=f"Polling interval in seconds between passes (default: {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--max-backoff",
        type=float,
        default=float(os.getenv("RESERVATION_EXPIRY_MAX_BACKOFF", str(DEFAULT_MAX_BACKOFF))),
        help=f"Maximum backoff interval in seconds on consecutive errors (default: {DEFAULT_MAX_BACKOFF})",
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default=None,
        help="Optional custom worker identifier",
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

    worker = ReservationExpiryWorker(
        worker_id=args.worker_id,
        batch_size=args.batch_size,
        poll_interval=args.interval,
        max_backoff=args.max_backoff,
    )

    setup_signal_handlers(worker)

    if args.run_once:
        logger.info("Executing ReservationExpiryWorker in run-once mode...")
        summary = worker.run_once()
        print(f"Pass complete: {summary}")
        sys.exit(0 if summary.get("failed", 0) == 0 else 1)
    else:
        worker.run_forever()


if __name__ == "__main__":
    main()
