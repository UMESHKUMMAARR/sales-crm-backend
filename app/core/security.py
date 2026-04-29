"""
Security utilities: JWT creation/validation, password hashing.
Uses short-lived access tokens + long-lived refresh tokens.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def _create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    payload = data.copy()
    now = datetime.now(timezone.utc)
    payload.update({
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type,
    })
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: str, username: str, role: str) -> str:
    return _create_token(
        {"sub": user_id, "username": username, "role": role},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh",
    )


def create_token_pair(user_id: str, username: str, role: str) -> Tuple[str, str]:
    """Return (access_token, refresh_token)"""
    return (
        create_access_token(user_id, username, role),
        create_refresh_token(user_id),
    )


def decode_token(token: str, expected_type: str = "access") -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != expected_type:
            raise credentials_exception
        if payload.get("sub") is None:
            raise credentials_exception
        return payload
    except JWTError:
        raise credentials_exception


def validate_password_strength(password: str) -> Optional[str]:
    """Returns error message or None if valid."""
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters"
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one digit"
    return None
