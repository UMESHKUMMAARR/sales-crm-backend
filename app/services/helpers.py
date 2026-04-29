"""
Shared service utilities used across route handlers.
"""
from datetime import datetime, timezone
from bson import ObjectId
from pymongo.database import Database
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def serialize(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serializable dict."""
    if not doc:
        return doc
    result = {}
    for k, v in doc.items():
        if k == "_id":
            result["id"] = str(v)
        elif k == "password":
            pass  # Never expose password hash
        elif isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


def serialize_list(docs: list) -> list:
    return [serialize(d) for d in docs]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def log_activity(
    db: Database,
    user_id: str,
    action: str,           # created | updated | deleted | viewed | assigned | login
    entity_type: str,      # lead | followup | comment | order | user
    entity_id: str,
    details: Optional[dict] = None,
):
    """Fire-and-forget activity logging. Errors are logged but never raised."""
    try:
        db.activity_log.insert_one({
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details or {},
            "timestamp": now_utc(),
        })
    except Exception as e:
        logger.warning(f"Activity log write failed: {e}")


def get_lead_or_404(db: Database, lead_id: str):
    """Fetch lead by ID, raise 404 if not found."""
    from fastapi import HTTPException, status
    try:
        lead = db.leads.find_one({"_id": ObjectId(lead_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def enrich_lead_with_user(db: Database, lead: dict) -> dict:
    """Add assigned_user info to a lead dict."""
    if lead.get("assigned_to"):
        try:
            user = db.users.find_one({"_id": ObjectId(lead["assigned_to"])})
            if user:
                lead["assigned_user"] = {
                    "id": str(user["_id"]),
                    "name": user["full_name"],
                    "username": user["username"],
                }
        except Exception:
            pass
    return lead
