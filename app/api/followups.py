"""
Follow-up endpoints.
GET  /api/followups/today
GET  /api/followups/upcoming
GET  /api/followups/overdue
GET  /api/leads/{id}/followups
POST /api/followups
PUT  /api/followups/{id}
"""
from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database
from bson import ObjectId
from datetime import date

from app.core.deps import db_dep, get_current_user, check_lead_access
from app.schemas.schemas import FollowUpCreateRequest, FollowUpUpdateRequest
from app.services.helpers import serialize, serialize_list, now_utc, log_activity, get_lead_or_404

router = APIRouter(tags=["followups"])


def _enrich_followup(db, followup: dict) -> dict:
    lead = db.leads.find_one({"_id": ObjectId(followup["lead_id"])})
    if lead:
        followup["lead_info"] = {
            "id": str(lead["_id"]),
            "name": lead["name"],
            "phone": lead.get("phone"),
            "city": lead.get("city"),
            "lead_status": lead.get("lead_status"),
            "priority_level": lead.get("priority_level"),
        }
    return followup


def _is_accessible(lead: dict, current_user: dict) -> bool:
    if current_user["role"] == "sales_person":
        return lead.get("assigned_to") == current_user["user_id"]
    return True


@router.get("/api/followups/today")
def get_today_followups(current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    today = date.today().isoformat()
    followups = list(db.followups.find({"followup_date": today, "status": "pending"}).sort("created_at", 1))
    result = []
    for f in followups:
        lead = db.leads.find_one({"_id": ObjectId(f["lead_id"])})
        if lead and _is_accessible(lead, current_user):
            result.append(serialize(_enrich_followup(db, f)))
    return result


@router.get("/api/followups/upcoming")
def get_upcoming_followups(current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    today = date.today().isoformat()
    followups = list(db.followups.find(
        {"followup_date": {"$gte": today}, "status": "pending"}
    ).sort("followup_date", 1).limit(50))
    result = []
    for f in followups:
        lead = db.leads.find_one({"_id": ObjectId(f["lead_id"])})
        if lead and _is_accessible(lead, current_user):
            result.append(serialize(_enrich_followup(db, f)))
    return result


@router.get("/api/followups/overdue")
def get_overdue_followups(current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    today = date.today().isoformat()
    followups = list(db.followups.find(
        {"followup_date": {"$lt": today}, "status": "pending"}
    ).sort("followup_date", 1))
    result = []
    for f in followups:
        lead = db.leads.find_one({"_id": ObjectId(f["lead_id"])})
        if lead and _is_accessible(lead, current_user):
            f["is_overdue"] = True
            result.append(serialize(_enrich_followup(db, f)))
    return result


@router.get("/api/leads/{lead_id}/followups")
def get_lead_followups(lead_id: str, current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    lead = get_lead_or_404(db, lead_id)
    check_lead_access(lead, current_user)
    followups = list(db.followups.find({"lead_id": lead_id}).sort("followup_date", -1).limit(50))
    return serialize_list(followups)


@router.post("/api/followups", status_code=201)
def create_followup(body: FollowUpCreateRequest, current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    lead = get_lead_or_404(db, body.lead_id)
    check_lead_access(lead, current_user)

    data = body.model_dump()
    data["status"] = "pending"
    data["reminder_sent"] = False
    data["created_at"] = now_utc()
    data["completed_at"] = None
    data["created_by"] = current_user["user_id"]

    result = db.followups.insert_one(data)
    log_activity(db, current_user["user_id"], "created", "followup", str(result.inserted_id),
                 {"lead_id": body.lead_id, "date": body.followup_date})
    created = db.followups.find_one({"_id": result.inserted_id})
    return serialize(created)


@router.put("/api/followups/{followup_id}")
def update_followup(followup_id: str, body: FollowUpUpdateRequest, current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    try:
        followup = db.followups.find_one({"_id": ObjectId(followup_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid followup ID")
    if not followup:
        raise HTTPException(status_code=404, detail="Follow-up not found")

    lead = get_lead_or_404(db, followup["lead_id"])
    check_lead_access(lead, current_user)

    update = body.model_dump(exclude_none=True)
    if update.get("status") == "completed":
        update["completed_at"] = now_utc()

    db.followups.update_one({"_id": ObjectId(followup_id)}, {"$set": update})
    log_activity(db, current_user["user_id"], "updated", "followup", followup_id, update)
    updated = db.followups.find_one({"_id": ObjectId(followup_id)})
    return serialize(updated)
