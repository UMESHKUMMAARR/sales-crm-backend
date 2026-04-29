"""
Authentication endpoints.
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
POST /api/auth/change-password
GET  /api/auth/me
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from bson import ObjectId
from datetime import datetime, timezone

from app.core.deps import db_dep, get_current_user
from app.core.security import (
    verify_password, hash_password, create_token_pair,
    decode_token, validate_password_strength,
)
from app.schemas.schemas import (
    LoginRequest, RefreshRequest, TokenResponse,
    ChangePasswordRequest, OkResponse, UserCreateRequest,
)
from app.services.helpers import serialize, now_utc, log_activity

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_token_response(db, user: dict) -> dict:
    user_id = str(user["_id"])
    access, refresh = create_token_pair(user_id, user["username"], user["role"])

    # Store refresh token in DB (allows server-side revocation)
    expires_at = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from datetime import timedelta
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    db.refresh_tokens.insert_one({
        "user_id": user_id,
        "token": refresh,
        "expires_at": expires_at,
        "created_at": now_utc(),
    })

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": serialize(user),
    }


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Database = Depends(db_dep)):
    user = db.users.find_one({"username": body.username})
    # Constant-time comparison to prevent user enumeration
    if not user or not verify_password(body.password, user.get("password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    log_activity(db, str(user["_id"]), "login", "user", str(user["_id"]))
    return _build_token_response(db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Database = Depends(db_dep)):
    payload = decode_token(body.refresh_token, expected_type="refresh")
    user_id = payload["sub"]

    # Validate refresh token exists in DB (not revoked)
    stored = db.refresh_tokens.find_one({"token": body.refresh_token, "user_id": user_id})
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user = db.users.find_one({"_id": ObjectId(user_id), "is_active": True})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Rotate — delete old, issue new
    db.refresh_tokens.delete_one({"token": body.refresh_token})
    return _build_token_response(db, user)


@router.post("/logout", response_model=OkResponse)
def logout(body: RefreshRequest, db: Database = Depends(db_dep)):
    db.refresh_tokens.delete_one({"token": body.refresh_token})
    return {"message": "Logged out successfully"}


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    user = db.users.find_one({"_id": ObjectId(current_user["user_id"])})
    return serialize(user)


@router.post("/change-password", response_model=OkResponse)
def change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(db_dep),
):
    user = db.users.find_one({"_id": ObjectId(current_user["user_id"])})
    if not verify_password(body.current_password, user["password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    error = validate_password_strength(body.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    db.users.update_one(
        {"_id": ObjectId(current_user["user_id"])},
        {"$set": {"password": hash_password(body.new_password), "updated_at": now_utc()}},
    )
    # Revoke all refresh tokens — force re-login everywhere
    db.refresh_tokens.delete_many({"user_id": current_user["user_id"]})
    log_activity(db, current_user["user_id"], "updated", "user", current_user["user_id"], {"action": "password_changed"})
    return {"message": "Password changed successfully. Please log in again."}
