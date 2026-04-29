"""
Pydantic v2 schemas — strict input validation, no extra fields allowed.
All schemas used for both request body validation and response serialization.
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Literal
from datetime import datetime
import re

# ── Shared ─────────────────────────────────────────────────────────────────────

class OkResponse(BaseModel):
    message: str

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int

# ── Auth ───────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    model_config = {"extra": "forbid"}
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)

class RefreshRequest(BaseModel):
    model_config = {"extra": "forbid"}
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict

class ChangePasswordRequest(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

# ── Users ──────────────────────────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=100)
    role: Literal["manager", "sales_person"]
    phone: Optional[str] = Field(None, max_length=20)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v and not re.match(r"^\+?[\d\s\-\(\)]{7,20}$", v):
            raise ValueError("Invalid phone number format")
        return v

class UserResponse(BaseModel):
    id: str
    username: str
    full_name: str
    role: str
    phone: Optional[str]
    is_active: bool
    created_at: datetime

class UserUpdateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)

# ── Leads ──────────────────────────────────────────────────────────────────────

LEAD_STATUSES = Literal["contacted", "site_visit_done", "quotation_sent", "negotiation", "deal_closed", "lost"]
PRIORITY_LEVELS = Literal["high", "medium", "low"]
PRODUCT_TYPES = Literal["upvc", "aluminium"]

class LeadCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(..., min_length=2, max_length=200)
    phone: str = Field(..., min_length=7, max_length=20)
    city: str = Field(..., min_length=2, max_length=100)
    product: PRODUCT_TYPES
    lead_source: str = Field(..., min_length=2, max_length=100)
    lead_status: LEAD_STATUSES = "contacted"
    priority_level: PRIORITY_LEVELS = "medium"
    assigned_to: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)
    next_followup_date: Optional[str] = None  # ISO date string YYYY-MM-DD

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if not re.match(r"^\+?[\d\s\-\(\)]{7,20}$", v):
            raise ValueError("Invalid phone number format")
        return v

    @field_validator("next_followup_date")
    @classmethod
    def validate_date(cls, v):
        if v:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Date must be YYYY-MM-DD format")
        return v

class LeadUpdateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    phone: Optional[str] = Field(None, min_length=7, max_length=20)
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    product: Optional[PRODUCT_TYPES] = None
    lead_source: Optional[str] = Field(None, min_length=2, max_length=100)
    lead_status: Optional[LEAD_STATUSES] = None
    priority_level: Optional[PRIORITY_LEVELS] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)
    next_followup_date: Optional[str] = None

class LeadAssignRequest(BaseModel):
    model_config = {"extra": "forbid"}
    lead_id: str
    assigned_to: str  # sales person user_id

class LeadResponse(BaseModel):
    id: str
    name: str
    phone: str
    city: str
    product: str
    lead_source: str
    lead_status: str
    priority_level: str
    assigned_to: Optional[str]
    assigned_user: Optional[dict]
    notes: Optional[str]
    next_followup_date: Optional[str]
    created_by: str
    created_at: datetime
    updated_at: datetime

# ── Follow-ups ─────────────────────────────────────────────────────────────────

class FollowUpCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    lead_id: str
    followup_date: str  # YYYY-MM-DD
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("followup_date")
    @classmethod
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be YYYY-MM-DD format")
        return v

class FollowUpUpdateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    status: Literal["pending", "completed", "cancelled"]
    notes: Optional[str] = Field(None, max_length=1000)

class FollowUpResponse(BaseModel):
    id: str
    lead_id: str
    followup_date: str
    notes: Optional[str]
    status: str
    reminder_sent: bool
    created_by: str
    created_at: datetime
    completed_at: Optional[datetime]
    lead_info: Optional[dict] = None

# ── Comments ───────────────────────────────────────────────────────────────────

class CommentCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    lead_id: str
    comment_text: str = Field(..., min_length=1, max_length=2000)

class CommentResponse(BaseModel):
    id: str
    lead_id: str
    comment_text: str
    created_by: str
    created_by_name: str
    created_at: datetime

# ── Orders ─────────────────────────────────────────────────────────────────────

class OrderCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    lead_id: str
    product_type: PRODUCT_TYPES
    quotation_amount: float = Field(..., gt=0)
    deal_amount: float = Field(..., gt=0)
    notes: Optional[str] = Field(None, max_length=2000)

    @model_validator(mode="after")
    def deal_cannot_exceed_quotation_by_too_much(self):
        if self.deal_amount > self.quotation_amount * 1.5:
            raise ValueError("Deal amount seems unusually high compared to quotation — please verify")
        return self

class OrderResponse(BaseModel):
    id: str
    lead_id: str
    product_type: str
    quotation_amount: float
    deal_amount: float
    notes: Optional[str]
    order_date: datetime
    created_by: str
    lead_info: Optional[dict] = None
