"""
FastAPI dependency injection functions.
Used as Depends() in route handlers.
"""
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pymongo.database import Database
from bson import ObjectId
from typing import Optional

from app.core.database import get_db
from app.core.security import decode_token

bearer_scheme = HTTPBearer(auto_error=True)


# ── Database ──────────────────────────────────────────────────────────────────

def db_dep() -> Database:
    return get_db()


# ── Auth dependencies ──────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Database = Depends(db_dep),
) -> dict:
    """Validate JWT and return user payload. Raises 401 if invalid."""
    payload = decode_token(credentials.credentials, expected_type="access")
    user_id = payload["sub"]

    # Verify user still exists and is active
    user = db.users.find_one({"_id": ObjectId(user_id), "is_active": True})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    return {
        "user_id": user_id,
        "username": payload.get("username"),
        "role": payload.get("role"),
        "full_name": user.get("full_name"),
    }


def get_current_manager(current_user: dict = Depends(get_current_user)) -> dict:
    """Ensures user is a manager. Raises 403 otherwise."""
    if current_user["role"] not in ("manager", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required",
        )
    return current_user


# ── Pagination ─────────────────────────────────────────────────────────────────

class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.page_size = page_size
        self.skip = (page - 1) * page_size


# ── Lead access check ──────────────────────────────────────────────────────────

def check_lead_access(lead: dict, current_user: dict) -> None:
    """Raises 403 if sales_person tries to access a lead not assigned to them."""
    if current_user["role"] == "sales_person":
        if lead.get("assigned_to") != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied — this lead is not assigned to you",
            )
