"""
User management endpoints (manager-only except profile update).
GET    /api/users              — list sales persons
POST   /api/users              — create user (manager)
GET    /api/users/{id}         — get user
PUT    /api/users/{id}         — update profile
PUT    /api/users/{id}/deactivate
PUT    /api/users/{id}/activate
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from bson import ObjectId
from typing import List

from app.core.deps import db_dep, get_current_user, get_current_manager
from app.core.security import hash_password, validate_password_strength
from app.schemas.schemas import UserCreateRequest, UserUpdateRequest, UserResponse, OkResponse
from app.services.helpers import serialize, serialize_list, now_utc, log_activity

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=List[dict])
def list_users(
    current_user: dict = Depends(get_current_manager),
    db: Database = Depends(db_dep),
):
    """List all sales persons. Manager only."""
    users = list(db.users.find({"role": "sales_person"}).sort("full_name", 1))
    return serialize_list(users)


@router.post("", response_model=dict, status_code=201)
def create_user(
    body: UserCreateRequest,
    current_user: dict = Depends(get_current_manager),
    db: Database = Depends(db_dep),
):
    """Create new user (sales_person or manager). Manager only."""
    if db.users.find_one({"username": body.username}):
        raise HTTPException(status_code=409, detail="Username already taken")

    error = validate_password_strength(body.password)
    if error:
        raise HTTPException(status_code=400, detail=error)

    data = body.model_dump()
    data["password"] = hash_password(data["password"])
    data["is_active"] = True
    data["created_at"] = now_utc()
    data["created_by"] = current_user["user_id"]

    result = db.users.insert_one(data)
    log_activity(db, current_user["user_id"], "created", "user", str(result.inserted_id),
                 {"username": body.username, "role": body.role})

    created = db.users.find_one({"_id": result.inserted_id})
    return serialize(created)


@router.get("/{user_id}", response_model=dict)
def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_manager),
    db: Database = Depends(db_dep),
):
    try:
        user = db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return serialize(user)


@router.put("/{user_id}", response_model=dict)
def update_user(
    user_id: str,
    body: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(db_dep),
):
    """Users can update their own profile. Managers can update any."""
    if current_user["role"] == "sales_person" and current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Cannot update other users' profiles")

    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = now_utc()

    result = db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    updated = db.users.find_one({"_id": ObjectId(user_id)})
    return serialize(updated)


@router.put("/{user_id}/deactivate", response_model=OkResponse)
def deactivate_user(
    user_id: str,
    current_user: dict = Depends(get_current_manager),
    db: Database = Depends(db_dep),
):
    if user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    result = db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_active": False, "updated_at": now_utc()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    log_activity(db, current_user["user_id"], "updated", "user", user_id, {"action": "deactivated"})
    return {"message": "User deactivated"}


@router.put("/{user_id}/activate", response_model=OkResponse)
def activate_user(
    user_id: str,
    current_user: dict = Depends(get_current_manager),
    db: Database = Depends(db_dep),
):
    result = db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_active": True, "updated_at": now_utc()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    log_activity(db, current_user["user_id"], "updated", "user", user_id, {"action": "activated"})
    return {"message": "User activated"}
