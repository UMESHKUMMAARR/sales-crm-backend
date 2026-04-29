"""
Database connection and index management.
Indexes are created on startup to ensure query performance.
"""
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

_client: MongoClient = None
_db: Database = None


def get_db() -> Database:
    global _client, _db
    if _db is None:
        _client = MongoClient(
            settings.MONGO_URL,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            maxPoolSize=50,
            minPoolSize=5,
        )
        _db = _client[settings.DB_NAME]
        _ensure_indexes(_db)
    return _db


def _ensure_indexes(db: Database):
    """Create all required indexes. Idempotent — safe to call multiple times."""
    try:
        # users
        db.users.create_index("username", unique=True)
        db.users.create_index("role")
        db.users.create_index("is_active")

        # leads
        db.leads.create_index("assigned_to")
        db.leads.create_index("lead_status")
        db.leads.create_index("priority_level")
        db.leads.create_index("created_at")
        db.leads.create_index([("assigned_to", ASCENDING), ("lead_status", ASCENDING)])
        db.leads.create_index([("assigned_to", ASCENDING), ("created_at", DESCENDING)])

        # followups
        db.followups.create_index("lead_id")
        db.followups.create_index("followup_date")
        db.followups.create_index("status")
        db.followups.create_index([("followup_date", ASCENDING), ("status", ASCENDING)])
        db.followups.create_index([("lead_id", ASCENDING), ("status", ASCENDING)])

        # comments
        db.comments.create_index([("lead_id", ASCENDING), ("created_at", DESCENDING)])

        # orders
        db.orders.create_index("lead_id", unique=True)  # One order per lead
        db.orders.create_index("order_date")
        db.orders.create_index("created_by")

        # activity_log  (time-series pattern — TTL keeps it from growing forever)
        db.activity_log.create_index("user_id")
        db.activity_log.create_index("timestamp")
        db.activity_log.create_index(
            "timestamp",
            expireAfterSeconds=90 * 24 * 3600,  # Auto-delete logs after 90 days
            name="activity_ttl"
        )

        # refresh_tokens
        db.refresh_tokens.create_index("user_id")
        db.refresh_tokens.create_index("token", unique=True)
        db.refresh_tokens.create_index(
            "expires_at",
            expireAfterSeconds=0,  # MongoDB TTL — auto-deletes expired tokens
            name="refresh_token_ttl"
        )

        logger.info("Database indexes ensured")
    except Exception as e:
        logger.warning(f"Index creation warning (may already exist): {e}")


def close_db():
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
