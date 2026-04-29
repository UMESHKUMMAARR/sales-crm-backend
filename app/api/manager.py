"""
Manager-only analytics and reporting endpoints.
GET /api/manager/stats
GET /api/manager/team-performance
GET /api/manager/activity-log
GET /api/manager/sales-report
"""
from fastapi import APIRouter, Depends, Query
from pymongo.database import Database
from bson import ObjectId
from datetime import datetime, timedelta, timezone, date
from typing import Optional

from app.core.deps import db_dep, get_current_manager
from app.services.helpers import serialize_list, now_utc

router = APIRouter(prefix="/api/manager", tags=["manager"])


def _start_of_month() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


@router.get("/stats")
def get_manager_stats(current_user: dict = Depends(get_current_manager), db: Database = Depends(db_dep)):
    today = date.today().isoformat()
    som = _start_of_month()

    total_leads = db.leads.count_documents({})
    unassigned_leads = db.leads.count_documents({"assigned_to": None})

    statuses = {}
    for s in ["contacted", "site_visit_done", "quotation_sent", "negotiation", "deal_closed", "lost"]:
        statuses[s] = db.leads.count_documents({"lead_status": s})

    today_followups = db.followups.count_documents({"followup_date": today, "status": "pending"})
    overdue_followups = db.followups.count_documents({"followup_date": {"$lt": today}, "status": "pending"})
    active_sales = db.users.count_documents({"role": "sales_person", "is_active": True})

    monthly_orders = list(db.orders.find({"order_date": {"$gte": som}}))
    monthly_sales = sum(o.get("deal_amount", 0) for o in monthly_orders)

    monthly_leads = db.leads.count_documents({"created_at": {"$gte": som}})
    closed_deals = db.leads.count_documents({"lead_status": "deal_closed", "updated_at": {"$gte": som}})
    conversion_ratio = round((closed_deals / monthly_leads * 100) if monthly_leads > 0 else 0, 1)

    return {
        "total_leads": total_leads,
        "unassigned_leads": unassigned_leads,
        "statuses": statuses,
        "today_followups": today_followups,
        "overdue_followups": overdue_followups,
        "active_sales_persons": active_sales,
        "monthly_sales": monthly_sales,
        "monthly_orders": len(monthly_orders),
        "conversion_ratio": conversion_ratio,
        "closed_deals": closed_deals,
    }


@router.get("/team-performance")
def get_team_performance(current_user: dict = Depends(get_current_manager), db: Database = Depends(db_dep)):
    sales_persons = list(db.users.find({"role": "sales_person", "is_active": True}))
    seven_days_ago = now_utc() - timedelta(days=7)
    som = _start_of_month()

    result = []
    for person in sales_persons:
        person_id = str(person["_id"])
        total_leads = db.leads.count_documents({"assigned_to": person_id})
        lead_ids = [str(l["_id"]) for l in db.leads.find({"assigned_to": person_id}, {"_id": 1})]

        total_followups = db.followups.count_documents({"lead_id": {"$in": lead_ids}}) if lead_ids else 0
        completed_followups = db.followups.count_documents({"lead_id": {"$in": lead_ids}, "status": "completed"}) if lead_ids else 0
        closed_deals = db.leads.count_documents({"assigned_to": person_id, "lead_status": "deal_closed"})
        recent_activity = db.activity_log.count_documents({"user_id": person_id, "timestamp": {"$gte": seven_days_ago}})

        # Monthly revenue
        monthly_orders = list(db.orders.find({"lead_id": {"$in": lead_ids}, "order_date": {"$gte": som}})) if lead_ids else []
        monthly_revenue = sum(o.get("deal_amount", 0) for o in monthly_orders)

        result.append({
            "user_id": person_id,
            "name": person["full_name"],
            "username": person["username"],
            "phone": person.get("phone"),
            "total_leads": total_leads,
            "closed_deals": closed_deals,
            "total_followups": total_followups,
            "completed_followups": completed_followups,
            "followup_completion_rate": round((completed_followups / total_followups * 100) if total_followups > 0 else 0, 1),
            "recent_activity_count": recent_activity,
            "monthly_revenue": monthly_revenue,
            "monthly_orders": len(monthly_orders),
        })

    return result


@router.get("/activity-log")
def get_activity_log(
    user_id: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=90),
    current_user: dict = Depends(get_current_manager),
    db: Database = Depends(db_dep),
):
    query = {"timestamp": {"$gte": now_utc() - timedelta(days=days)}}
    if user_id:
        query["user_id"] = user_id

    activities = list(db.activity_log.find(query).sort("timestamp", -1).limit(200))
    result = []
    for a in activities:
        # Enrich with user name
        try:
            user = db.users.find_one({"_id": ObjectId(a["user_id"])}, {"full_name": 1})
            a["user_name"] = user["full_name"] if user else "Unknown"
        except Exception:
            a["user_name"] = "Unknown"
        from app.services.helpers import serialize
        result.append(serialize(a))
    return result


@router.get("/sales-report")
def get_sales_report(current_user: dict = Depends(get_current_manager), db: Database = Depends(db_dep)):
    som = _start_of_month()
    orders = list(db.orders.find({"order_date": {"$gte": som}}))
    total_sales = sum(o.get("deal_amount", 0) for o in orders)
    total_orders = len(orders)
    total_leads = db.leads.count_documents({"created_at": {"$gte": som}})
    closed_deals = db.leads.count_documents({"lead_status": "deal_closed", "updated_at": {"$gte": som}})
    conversion_ratio = round((closed_deals / total_leads * 100) if total_leads > 0 else 0, 1)

    # Per-product breakdown
    upvc_sales = sum(o.get("deal_amount", 0) for o in orders if o.get("product_type") == "upvc")
    aluminium_sales = sum(o.get("deal_amount", 0) for o in orders if o.get("product_type") == "aluminium")

    return {
        "period": som.strftime("%B %Y"),
        "total_orders": total_orders,
        "total_sales": total_sales,
        "upvc_sales": upvc_sales,
        "aluminium_sales": aluminium_sales,
        "conversion_ratio": conversion_ratio,
        "closed_deals": closed_deals,
        "total_leads": total_leads,
    }
