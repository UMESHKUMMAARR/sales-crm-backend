"""Comments and Orders endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database
from bson import ObjectId

from app.core.deps import db_dep, get_current_user, check_lead_access
from app.schemas.schemas import CommentCreateRequest, OrderCreateRequest, OkResponse
from app.services.helpers import serialize, serialize_list, now_utc, log_activity, get_lead_or_404

comments_router = APIRouter(tags=["comments"])
orders_router = APIRouter(tags=["orders"])


# ── Comments ───────────────────────────────────────────────────────────────────

@comments_router.post("/api/comments", status_code=201)
def create_comment(body: CommentCreateRequest, current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    lead = get_lead_or_404(db, body.lead_id)
    check_lead_access(lead, current_user)

    data = body.model_dump()
    data["created_at"] = now_utc()
    data["created_by"] = current_user["user_id"]
    data["created_by_name"] = current_user.get("full_name") or current_user["username"]

    result = db.comments.insert_one(data)
    log_activity(db, current_user["user_id"], "created", "comment", str(result.inserted_id))
    return serialize(db.comments.find_one({"_id": result.inserted_id}))


@comments_router.get("/api/leads/{lead_id}/comments")
def get_lead_comments(lead_id: str, current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    lead = get_lead_or_404(db, lead_id)
    check_lead_access(lead, current_user)
    comments = list(db.comments.find({"lead_id": lead_id}).sort("created_at", -1).limit(50))
    return serialize_list(comments)


# ── Orders ─────────────────────────────────────────────────────────────────────

@orders_router.post("/api/orders", status_code=201)
def create_order(body: OrderCreateRequest, current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    lead = get_lead_or_404(db, body.lead_id)
    check_lead_access(lead, current_user)

    if lead.get("lead_status") != "deal_closed":
        raise HTTPException(status_code=400, detail="Orders can only be created for leads with status 'deal_closed'")
    if db.orders.find_one({"lead_id": body.lead_id}):
        raise HTTPException(status_code=409, detail="An order already exists for this lead")

    data = body.model_dump()
    data["order_value"] = body.deal_amount  # Convenience field
    data["order_date"] = now_utc()
    data["created_by"] = current_user["user_id"]
    data["created_at"] = now_utc()

    result = db.orders.insert_one(data)
    log_activity(db, current_user["user_id"], "created", "order", str(result.inserted_id),
                 {"lead_id": body.lead_id, "deal_amount": body.deal_amount})
    return serialize(db.orders.find_one({"_id": result.inserted_id}))


@orders_router.get("/api/orders")
def list_orders(current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    query = {}
    if current_user["role"] == "sales_person":
        lead_ids = [str(l["_id"]) for l in db.leads.find({"assigned_to": current_user["user_id"]}, {"_id": 1})]
        query["lead_id"] = {"$in": lead_ids}

    orders = list(db.orders.find(query).sort("order_date", -1).limit(100))
    result = []
    for order in orders:
        o = serialize(order)
        lead = db.leads.find_one({"_id": ObjectId(order["lead_id"])})
        if lead:
            o["lead_info"] = {"name": lead["name"], "phone": lead.get("phone"), "city": lead.get("city")}
        result.append(o)
    return result


@orders_router.get("/api/leads/{lead_id}/order")
def get_lead_order(lead_id: str, current_user: dict = Depends(get_current_user), db: Database = Depends(db_dep)):
    lead = get_lead_or_404(db, lead_id)
    check_lead_access(lead, current_user)
    order = db.orders.find_one({"lead_id": lead_id})
    return serialize(order) if order else None
