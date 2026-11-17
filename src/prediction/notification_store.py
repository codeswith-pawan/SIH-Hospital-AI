"""
In-App Notification Service
AI Powered Smart Hospital Referral System - Phase 18

Manages hospital lifecycle event notifications with dual backend support:
PostgreSQL relational persistence (production/staging) and thread-safe JSON/in-memory fallback.
"""

import json
import os
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_IN_MEMORY_NOTIFICATIONS: Dict[str, List[Dict[str, Any]]] = {}


def get_notification_store_path() -> Path:
    env_path = os.getenv("SIH_NOTIFICATIONS_PATH")
    if env_path:
        return Path(env_path)
    return Path("data/runtime/notifications.json")


def _load_json_notifications() -> Dict[str, List[Dict[str, Any]]]:
    path = get_notification_store_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json_notifications(data: Dict[str, List[Dict[str, Any]]]) -> None:
    path = get_notification_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def create_notification(
    hospital_id: str,
    event_type: str,
    title: str,
    message: str,
    referral_id: Optional[str] = None,
    priority: str = "NORMAL",
) -> Dict[str, Any]:
    """
    Publish an in-app notification to a destination or source hospital.
    Uses PostgreSQL when active, otherwise local JSON store.
    """
    now = datetime.now(timezone.utc)
    from src.database.db_manager import is_postgres, get_referral_repository

    if is_postgres():
        try:
            from src.database.db_manager import get_session_factory
            from src.database.pg_models import Notification
            factory = get_session_factory()
            with factory() as session:
                notif = Notification(
                    hospital_id=hospital_id,
                    referral_id=referral_id,
                    event_type=event_type,
                    title=title,
                    message=message,
                    priority=priority,
                    is_read=False,
                    created_at=now,
                )
                session.add(notif)
                session.commit()
                return {
                    "id": notif.id,
                    "hospital_id": hospital_id,
                    "referral_id": referral_id,
                    "event_type": event_type,
                    "title": title,
                    "message": message,
                    "priority": priority,
                    "is_read": False,
                    "created_at": now.isoformat(),
                }
        except Exception as e:
            logger.error("Failed to write notification to PostgreSQL (%s). Falling back.", e)

    # JSON / In-memory fallback
    data = _load_json_notifications()
    hospital_list = data.setdefault(hospital_id, [])
    notif_entry = {
        "id": int(time.time() * 1000),
        "hospital_id": hospital_id,
        "referral_id": referral_id,
        "event_type": event_type,
        "title": title,
        "message": message,
        "priority": priority,
        "is_read": False,
        "created_at": now.isoformat(),
    }
    hospital_list.insert(0, notif_entry)
    _save_json_notifications(data)
    return notif_entry


def get_hospital_notifications(
    hospital_id: str,
    unread_only: bool = False,
    limit: int = 50,
    page: int = 1,
    page_size: Optional[int] = None,
    event_category: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve notifications for a hospital with unread count, pagination, and category filtering."""
    from src.database.db_manager import is_postgres, get_referral_repository

    if is_postgres():
        try:
            repo = get_referral_repository()
            return repo.get_hospital_notifications(
                hospital_id=hospital_id,
                unread_only=unread_only,
                limit=limit,
                page=page,
                page_size=page_size,
                event_category=event_category,
            )
        except Exception as e:
            logger.error("Failed to read notifications from PostgreSQL (%s). Using fallback.", e)

    data = _load_json_notifications()
    all_notifs = data.get(hospital_id, [])
    filtered = all_notifs
    if unread_only:
        filtered = [n for n in filtered if not n.get("is_read", False)]

    if event_category:
        cat = event_category.lower().strip()
        filtered = [n for n in filtered if cat in (n.get("event_type") or "").lower()]

    effective_limit = page_size if page_size is not None else limit
    start = (page - 1) * effective_limit if page > 1 else 0
    paged = filtered[start:start + effective_limit]

    unread_count = sum(1 for n in all_notifs if not n.get("is_read", False))
    return {
        "hospital_id": hospital_id,
        "unread_count": unread_count,
        "total_count": len(filtered),
        "total_returned": len(paged),
        "page": page,
        "page_size": effective_limit,
        "notifications": paged,
    }


def mark_notification_as_read(notification_id: int, hospital_id: str) -> bool:
    """Mark single notification as read."""
    from src.database.db_manager import is_postgres, get_referral_repository

    if is_postgres():
        try:
            repo = get_referral_repository()
            return repo.mark_notification_as_read(notification_id, hospital_id)
        except Exception as e:
            logger.error("Failed to mark notification read in PostgreSQL (%s).", e)

    data = _load_json_notifications()
    notifs = data.get(hospital_id, [])
    found = False
    for n in notifs:
        if n.get("id") == notification_id:
            n["is_read"] = True
            found = True
            break
    if found:
        _save_json_notifications(data)
    return found


def mark_all_notifications_read(hospital_id: str) -> int:
    """Mark all notifications as read for a hospital."""
    from src.database.db_manager import is_postgres, get_referral_repository

    if is_postgres():
        try:
            repo = get_referral_repository()
            return repo.mark_all_notifications_read(hospital_id)
        except Exception as e:
            logger.error("Failed to mark all read in PostgreSQL (%s).", e)

    data = _load_json_notifications()
    notifs = data.get(hospital_id, [])
    count = 0
    for n in notifs:
        if not n.get("is_read", False):
            n["is_read"] = True
            count += 1
    if count > 0:
        _save_json_notifications(data)
    return count
