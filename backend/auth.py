"""Authentication endpoints for ContractGuard.

Provides email-based signup/signin and anonymous guest login.
User credentials are stored in MongoDB with bcrypt-hashed passwords.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, HTTPException

if __package__ is None or __package__ == "":
    from api.schemas import AuthResponse, SigninRequest, SignupRequest
    from contracts.store import MongoContractStore
    from core.config import settings
else:
    from .api.schemas import AuthResponse, SigninRequest, SignupRequest
    from .contracts.store import MongoContractStore
    from .core.config import settings

logger = logging.getLogger("contractguard.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Shared MongoDB store (initialized lazily on first request)
_store: MongoContractStore | None = None


# In-memory users cache (fallback when MongoDB is unreachable or for fast lookup)
_mem_users: dict[str, dict] = {}


def _get_store() -> MongoContractStore:
    global _store
    if _store is None:
        _store = MongoContractStore(settings.mongo_uri, settings.mongo_db_name)
    return _store


def _users_collection():
    return _get_store().db.users


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


@router.post("/signup", response_model=AuthResponse)
async def signup(payload: SignupRequest):
    """Register a new user with email and password."""
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Check in-memory first
    if email in _mem_users:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Check MongoDB if available
    store = _get_store()
    if store.is_available:
        try:
            users = _users_collection()
            existing = await users.find_one({"email": email})
            if existing:
                raise HTTPException(status_code=409, detail="An account with this email already exists")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("MongoDB unavailable during signup email check: %s", exc)
            store.is_available = False

    user_id = str(uuid.uuid4())
    display_name = payload.display_name.strip() or email.split("@")[0]
    password_hash = _hash_password(payload.password)
    user_doc = {
        "_id": user_id,
        "email": email,
        "password_hash": password_hash,
        "display_name": display_name,
        "is_guest": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store in memory
    _mem_users[email] = user_doc

    # Store in MongoDB (best-effort)
    if store.is_available:
        try:
            users = _users_collection()
            await users.insert_one(user_doc)
        except Exception as exc:
            logger.warning("MongoDB unavailable during signup insert, user saved in-memory: %s", exc)
            store.is_available = False

    logger.info("New user registered: %s (%s)", display_name, email)
    return AuthResponse(
        user_id=user_id,
        email=email,
        display_name=display_name,
        is_guest=False,
    )


@router.post("/signin", response_model=AuthResponse)
async def signin(payload: SigninRequest):
    """Sign in an existing user with email and password."""
    email = payload.email.strip().lower()
    store = _get_store()

    user = None
    # 1. Try MongoDB if available
    if store.is_available:
        try:
            users = _users_collection()
            user = await users.find_one({"email": email})
            if user:
                # Sync to in-memory
                _mem_users[email] = user
        except Exception as exc:
            logger.warning("MongoDB unavailable during signin, checking in-memory store: %s", exc)
            store.is_available = False

    # 2. Fall back to in-memory store
    if not user:
        user = _mem_users.get(email)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not _verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    logger.info("User signed in: %s", email)
    return AuthResponse(
        user_id=str(user.get("_id", uuid.uuid4())),
        email=user.get("email"),
        display_name=user.get("display_name", email.split("@")[0]),
        is_guest=False,
    )


@router.post("/guest", response_model=AuthResponse)
async def guest_login():
    """Create an anonymous guest session."""
    user_id = str(uuid.uuid4())
    guest_number = random.randint(1000, 9999)
    display_name = f"Guest-{guest_number}"
    user_doc = {
        "_id": user_id,
        "email": None,
        "password_hash": None,
        "display_name": display_name,
        "is_guest": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    _mem_users[user_id] = user_doc
    store = _get_store()

    if store.is_available:
        try:
            users = _users_collection()
            await users.insert_one(user_doc)
            logger.info("Guest session created in DB: %s", display_name)
        except Exception as exc:
            logger.warning(
                "MongoDB unavailable during guest login, proceeding with in-memory session: %s",
                exc,
            )
            store.is_available = False

    return AuthResponse(
        user_id=user_id,
        email=None,
        display_name=display_name,
        is_guest=True,
    )

