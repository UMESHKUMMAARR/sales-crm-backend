"""
Lead management endpoints.
GET    /api/leads              — list (role-scoped)
POST   /api/leads              — create
GET    /api/leads/unassigned   — unassigned leads (manager)
GET    /api/leads/{id}         — get one
PUT    /api/leads/{id}         — update
DELETE /api/leads/{id}         — delete (cascades followups & comments)
POST   /api/leads/assign       — assign to sales person (manager)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database
from bson import ObjectId
from typing import Optional, List

from app.core.deps import db_dep, get_current_user, get_current_manager, check_lead_access, PaginationParams
from app.schemas.schemas import LeadCreateRequest, LeadUpdateRequest, LeadAssignRequest, OkResponse
from app.services.helpers import serialize, serialize_list, now_utc, log_activity, get_lead_or_404, enrich_lead_with_user

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("")
def list_leads(
    lead_status: Optional[str] = Query(None),
    priority_level: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(db_dep),
):
    query = {}
    if current_user["role"] == "sales_person":
        query["assigned_to"] = current_user["user_id"]
    if lead_status:
        query["lead_status"] = lead_status
    if priority_level:
        query["priority_level"] = priority_level
    if search:
        # Case-insensitive search on name, phone, city
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"city": {"$regex": search, "$options": "i"}},
        ]

    total = db.leads.count_documents(query)
    skip = (page - 1) * page_size
    leads = list(db.leads.find(query).sort("created_at", -1).skip(skip).limit(page_size))

    result = []
    for lead in leads:
        lead = enrich_lead_with_user(db, lead)
        result.append(serialize(lead))

    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),  # Ceiling division
    }


@router.get("/unassigned")
def get_unassigned_leads(
    current_user: dict = Depends(get_current_manager),
    db: Database = Depends(db_dep),
):
    leads = list(db.leads.find({"assigned_to": None}).sort("created_at", -1).limit(50))
    return serialize_list(leads)


@router.post("", status_code=201)
def create_lead(
    body: LeadCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(db_dep),
):
    data = body.model_dump()
    data["created_at"] = now_utc()
    data["updated_at"] = now_utc()
    data["created_by"] = current_user["user_id"]

    # Sales persons auto-assigned to themselves
    if not data.get("assigned_to") and current_user["role"] == "sales_person":
        data["assigned_to"] = current_user["user_id"]

    # Validate assigned_to user exists if provided
    if data.get("assigned_to"):
        if not db.users.find_one({"_id": ObjectId(data["assigned_to"]), "is_active": True}):
            raise HTTPException(status_code=400, detail="Assigned user not found or inactive")

    result = db.leads.insert_one(data)
    log_activity(db, current_user["user_id"], "created", "lead", str(result.inserted_id),
                 {"name": body.name, "status": body.lead_status})

    created = db.leads.find_one({"_id": result.inserted_id})
    return serialize(enrich_lead_with_user(db, created))


@router.get("/{lead_id}")
def get_lead(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(db_dep),
):
    lead = get_lead_or_404(db, lead_id)
    check_lead_access(lead, current_user)
    log_activity(db, current_user["user_id"], "viewed", "lead", lead_id)
    return serialize(enrich_lead_with_user(db, lead))


@router.put("/{lead_id}")
def update_lead(
    lead_id: str,
    body: LeadUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(db_dep),
):
    lead = get_lead_or_404(db, lead_id)
    check_lead_access(lead, current_user)

    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate assigned_to if being changed
    if "assigned_to" in update and update["assigned_to"]:
        if not db.users.find_one({"_id": ObjectId(update["assigned_to"]), "is_active": True}):
            raise HTTPException(status_code=400, detail="Assigned user not found or inactive")

    update["updated_at"] = now_utc()
    db.leads.update_one({"_id": ObjectId(lead_id)}, {"$set": update})
    log_activity(db, current_user["user_id"], "updated", "lead", lead_id, update)

    updated = db.leads.find_one({"_id": ObjectId(lead_id)})
    return serialize(enrich_lead_with_user(db, updated))


@router.delete("/{lead_id}", response_model=OkResponse)
def delete_lead(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(db_dep),
):
    lead = get_lead_or_404(db, lead_id)
    check_lead_access(lead, current_user)

    db.leads.delete_one({"_id": ObjectId(lead_id)})
    # Cascade deletes
    db.followups.delete_many({"lead_id": lead_id})
    db.comments.delete_many({"lead_id": lead_id})
    db.orders.delete_many({"lead_id": lead_id})

    log_activity(db, current_user["user_id"], "deleted", "lead", lead_id, {"name": lead.get("name")})
    return {"message": "Lead deleted"}


@router.post("/assign", response_model=OkResponse)
def assign_lead(
    body: LeadAssignRequest,
    current_user: dict = Depends(get_current_manager),
    db: Database = Depends(db_dep),
):
    lead = get_lead_or_404(db, body.lead_id)

    sales_person = db.users.find_one({"_id": ObjectId(body.assigned_to), "is_active": True})
    if not sales_person:
        raise HTTPException(status_code=404, detail="Sales person not found or inactive")

    db.leads.update_one(
        {"_id": ObjectId(body.lead_id)},
        {"$set": {"assigned_to": body.assigned_to, "assigned_date": now_utc(), "updated_at": now_utc()}},
    )
    log_activity(db, current_user["user_id"], "assigned", "lead", body.lead_id,
                 {"assigned_to": body.assigned_to, "assigned_to_name": sales_person["full_name"]})
    return {"message": f"Lead assigned to {sales_person['full_name']}"}
