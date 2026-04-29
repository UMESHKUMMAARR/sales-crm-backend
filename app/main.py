"""
Sales CRM Pro — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import get_db, close_db
from app.core.security import hash_password
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.api import auth, users, leads, followups, manager
from app.api.comments_orders import comments_router, orders_router
from app.services.helpers import now_utc


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    db = get_db()
    _seed_default_admin(db)
    yield
    close_db()


def _seed_default_admin(db):
    """Create default admin account if no users exist."""
    if db.users.count_documents({}) == 0:
        db.users.insert_one({
            "username": "admin",
            "password": hash_password("Admin@1234"),  # Force change on first login
            "full_name": "System Admin",
            "role": "manager",
            "phone": None,
            "is_active": True,
            "created_at": now_utc(),
            "must_change_password": True,
        })
        print("✅ Default admin created — username: admin, password: Admin@1234")
        print("⚠️  Change the password immediately after first login!")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,   # Disable Swagger in production
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── Middleware (order matters — first added = outermost) ──────────────────────
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(leads.router)
app.include_router(followups.router)
app.include_router(comments_router)
app.include_router(orders_router)
app.include_router(manager.router)


@app.get("/")
def health():
    return {"status": "healthy", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/health")
def health_check():
    return {"status": "ok"}
