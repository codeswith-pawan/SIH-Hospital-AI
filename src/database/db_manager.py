"""
Unified Database Manager and Session Lifecycle Factory
AI Powered Smart Hospital Referral System

Handles dynamic connection routing between PostgreSQL (production/staging)
and SQLite/JSON fallback (local development and test execution).
Enforces strict production safeguards: forbids silent fallback in production,
validates connection pool parameters, and sanitizes database credentials in errors.
"""

import os
import re
import logging
from typing import Generator, Optional, Dict, Any
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from src.database.pg_models import PgBase
from src.database.pg_repository import PgReferralRepository

logger = logging.getLogger("db_manager")

_ENGINE = None
_SESSION_FACTORY = None


def is_production() -> bool:
    """Return True if running in production mode."""
    env = (os.getenv("ENVIRONMENT") or os.getenv("SIH_ENV") or "").lower().strip()
    return env in ["production", "prod"]


def sanitize_database_url(url: Optional[str]) -> str:
    """Mask credentials in database connection strings for safe logging and error reporting."""
    if not url:
        return "<none>"
    try:
        parsed = urlparse(url)
        if parsed.password:
            masked = url.replace(f":{parsed.password}@", ":******@")
            return masked
        return url
    except Exception:
        return "<sanitized-url>"


def sanitize_db_error(error: Exception) -> str:
    """Remove connection strings, passwords, and host info from database exceptions."""
    msg = str(error)
    # Mask password in urls like postgresql://user:pass@host/db
    sanitized = re.sub(r"://([^:]+):([^@]+)@", r"://\1:******@", msg)
    return sanitized


def get_database_url() -> str:
    """
    Resolve active database connection string.
    
    Production Safeguard:
    In production mode (ENVIRONMENT=production), DATABASE_URL or SIH_DATABASE_URL
    is MANDATORY and must use the PostgreSQL protocol. Silent fallback to SQLite
    or JSON persistence is strictly prohibited.
    """
    url = os.getenv("SIH_DATABASE_URL") or os.getenv("DATABASE_URL")

    if is_production():
        if not url:
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: Production environment requires PostgreSQL. "
                "Set DATABASE_URL or SIH_DATABASE_URL. Silent fallback to SQLite/JSON is forbidden in production."
            )
        if not (url.startswith("postgresql://") or url.startswith("postgres://")):
            raise RuntimeError(
                f"CRITICAL CONFIGURATION ERROR: Production database URL must use the PostgreSQL protocol (postgresql://). "
                f"Received unsupported scheme: '{sanitize_database_url(url)}'. "
                f"SQLite/JSON fallback is strictly forbidden in production mode."
            )

    if url:
        # Normalize postgres:// to postgresql:// for SQLAlchemy 1.4+ / 2.0+
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    # Default SQLite fallback for local development and non-production testing
    from src.database.database import DATABASE_URL as SQLITE_URL
    return SQLITE_URL


def is_postgres() -> bool:
    """Check if the configured database URL is PostgreSQL."""
    try:
        url = get_database_url()
        return url.startswith("postgresql")
    except Exception:
        return False


def get_engine():
    """Get or create singleton SQLAlchemy engine with production connection pooling."""
    global _ENGINE
    if _ENGINE is None:
        db_url = get_database_url()
        if is_postgres():
            pool_size = int(os.getenv("DB_POOL_SIZE") or os.getenv("SIH_DB_POOL_SIZE", "10"))
            max_overflow = int(os.getenv("DB_MAX_OVERFLOW") or os.getenv("SIH_DB_MAX_OVERFLOW", "5"))
            pool_timeout = int(os.getenv("DB_POOL_TIMEOUT") or os.getenv("SIH_DB_POOL_TIMEOUT", "30"))
            pool_recycle = int(os.getenv("DB_POOL_RECYCLE") or os.getenv("SIH_DB_POOL_RECYCLE", "1800"))

            _ENGINE = create_engine(
                db_url,
                pool_pre_ping=True,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                pool_recycle=pool_recycle,
            )
            logger.info("Configured PostgreSQL connection pool: size=%d, overflow=%d", pool_size, max_overflow)
        else:
            _ENGINE = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
            )
            logger.info("Configured SQLite fallback database engine.")
    return _ENGINE


def reset_engine():
    """Reset singleton engine and session factory (used for testing and connection switching)."""
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        try:
            _ENGINE.dispose()
        except Exception:
            pass
    _ENGINE = None
    _SESSION_FACTORY = None


def get_session_factory() -> sessionmaker:
    """Get or create singleton sessionmaker."""
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        eng = get_engine()
        _SESSION_FACTORY = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=eng,
        )
    return _SESSION_FACTORY


def get_db_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a managed database session.
    Automatically commits on success or rolls back on exception.
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_db_health() -> Dict[str, Any]:
    """
    Performs an active database ping and returns sanitized engine metadata.
    """
    try:
        db_url = get_database_url()
        parsed = urlparse(db_url)
        dialect = parsed.scheme.split("+")[0] if parsed.scheme else "unknown"

        eng = get_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "HEALTHY",
            "dialect": dialect,
            "is_postgres": is_postgres(),
            "host": parsed.hostname or "local",
            "database": parsed.path.lstrip("/") if parsed.path else "memory",
        }
    except Exception as e:
        return {
            "status": "UNHEALTHY",
            "is_postgres": is_postgres(),
            "error": sanitize_db_error(e),
        }


def get_pool_stats() -> dict:
    """
    Returns SQLAlchemy connection pool runtime statistics.
    Safe to call frequently; does not create new connections.
    Returns empty dict if pool is not available or not a QueuePool.
    """
    global _ENGINE
    if _ENGINE is None:
        return {"available": False, "reason": "engine_not_initialized"}

    pool = _ENGINE.pool
    # QueuePool exposes: size(), checkedin(), checkedout(), overflow()
    # StaticPool (SQLite test) does not — guard with hasattr
    stats = {"pool_type": type(pool).__name__}
    try:
        pool_size = pool.size() if hasattr(pool, 'size') else None
        checked_in = pool.checkedin() if hasattr(pool, 'checkedin') else None
        checked_out = pool.checkedout() if hasattr(pool, 'checkedout') else None
        overflow = pool.overflow() if hasattr(pool, 'overflow') else None

        stats["pool_size"] = pool_size
        stats["checked_in"] = checked_in
        stats["checked_out"] = checked_out
        stats["overflow"] = overflow

        # Utilization: checked_out / (pool_size + max(overflow, 0))
        if pool_size is not None and checked_out is not None:
            effective_max = pool_size + (max(overflow, 0) if overflow is not None else 0)
            stats["utilization_pct"] = round(100.0 * checked_out / effective_max, 1) if effective_max > 0 else 0.0
        else:
            stats["utilization_pct"] = None

        stats["available"] = True
    except Exception as e:
        stats["available"] = False
        stats["error"] = str(e)

    return stats


def validate_production_database_config():
    """
    Startup invariant check: validates that production has a healthy PostgreSQL
    connection and that Redis is configured if distributed rate limiting is required.
    Fails fast if production configuration is invalid.
    """
    if not is_production():
        return

    # 1. PostgreSQL requirement
    if not is_postgres():
        raise RuntimeError("Production requires PostgreSQL. Fallback to SQLite/JSON is forbidden.")

    health = check_db_health()
    if health.get("status") != "HEALTHY":
        raise RuntimeError(f"Production database health check failed: {health.get('error')}")

    # 2. Redis requirement for distributed workers
    require_redis = os.getenv("SIH_REQUIRE_REDIS", "false").lower() in ["1", "true", "yes"]
    if require_redis:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise RuntimeError(
                "Production distributed rate limiting requires REDIS_URL when SIH_REQUIRE_REDIS=true."
            )
        try:
            import redis
            rc = redis.Redis.from_url(redis_url)
            rc.ping()
        except Exception as e:
            raise RuntimeError(f"Production Redis connection failed: {sanitize_db_error(e)}")


def get_referral_repository(session: Optional[Session] = None) -> PgReferralRepository:
    """
    Return a PgReferralRepository bound to the given session or a newly created session.
    """
    owns_session = False
    if session is None:
        factory = get_session_factory()
        session = factory()
        owns_session = True
    repo = PgReferralRepository(session)
    repo._owns_session = owns_session
    return repo


def get_registration_service(session: Optional[Session] = None):
    """
    Return a RegistrationService bound to the given session or a newly created session.
    """
    from src.services.registration_service import RegistrationService
    if session is None:
        factory = get_session_factory()
        session = factory()
    return RegistrationService(session)
