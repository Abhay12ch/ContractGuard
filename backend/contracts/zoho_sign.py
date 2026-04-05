"""Zoho Sign digital signature verification module.

Provides OAuth 2.0 token management, document signature verification,
and audit trail retrieval from the Zoho Sign API.

Token Flow: Uses a refresh_token grant to obtain short-lived access tokens,
cached in memory with expiry tracking. Auto-refreshes on 401/expiry.

Environment variables required:
    ZOHO_CLIENT_ID       - OAuth client ID
    ZOHO_CLIENT_SECRET   - OAuth client secret  
    ZOHO_REFRESH_TOKEN   - Long-lived refresh token
    ZOHO_API_DOMAIN      - e.g. "https://sign.zoho.in" or "https://sign.zoho.com"
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("contractguard.zoho_sign")

# ── In-memory token cache ──────────────────────────────────────────

_token_cache: Dict[str, Any] = {
    "access_token": None,
    "expires_at": 0,  # epoch seconds
}

# ── Configuration helpers ──────────────────────────────────────────

def _get_env(key: str) -> str:
    """Get an environment variable or return empty string."""
    return os.getenv(key, "").strip()


def zoho_configured() -> bool:
    """Check whether Zoho Sign credentials are configured."""
    return bool(
        _get_env("ZOHO_CLIENT_ID")
        and _get_env("ZOHO_CLIENT_SECRET")
        and _get_env("ZOHO_REFRESH_TOKEN")
    )


def _api_domain() -> str:
    """Get the Zoho Sign API domain."""
    domain = _get_env("ZOHO_API_DOMAIN")
    return domain.rstrip("/") if domain else "https://sign.zoho.com"


def _accounts_domain() -> str:
    """Derive the Zoho accounts domain from the API domain.
    
    sign.zoho.in  → accounts.zoho.in
    sign.zoho.com → accounts.zoho.com
    sign.zoho.eu  → accounts.zoho.eu
    """
    api = _api_domain()
    # Extract TLD from the API domain
    if ".zoho.in" in api:
        return "https://accounts.zoho.in"
    elif ".zoho.eu" in api:
        return "https://accounts.zoho.eu"
    elif ".zoho.com.au" in api:
        return "https://accounts.zoho.com.au"
    return "https://accounts.zoho.com"


# ── Date parsing ───────────────────────────────────────────────────

def _parse_zoho_date(value: Any) -> Optional[str]:
    """Parse a Zoho date (epoch ms or ISO string) into ISO 8601 string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Zoho sometimes returns epoch milliseconds
        if value > 1e12:  # likely milliseconds
            value = value / 1000
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        # Try parsing as epoch string
        try:
            epoch = float(value)
            if epoch > 1e12:
                epoch = epoch / 1000
            return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
        except ValueError:
            pass
        # Return as-is if it looks like an ISO string
        return value
    return None


# ── OAuth Token Management ─────────────────────────────────────────

async def get_access_token(force_refresh: bool = False) -> str:
    """Obtain a valid Zoho Sign access token.

    Uses a refresh_token grant to get short-lived access tokens.
    Caches the token in memory and only refreshes when expired or forced.

    Returns:
        The access_token string.

    Raises:
        RuntimeError: If Zoho credentials are not configured.
        Exception: If the token request fails.
    """
    if not zoho_configured():
        raise RuntimeError("Zoho Sign credentials not configured. Set ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN.")

    # Return cached token if still valid (with 60s buffer)
    if not force_refresh and _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    token_url = f"{_accounts_domain()}/oauth/v2/token"
    params = {
        "grant_type": "refresh_token",
        "client_id": _get_env("ZOHO_CLIENT_ID"),
        "client_secret": _get_env("ZOHO_CLIENT_SECRET"),
        "refresh_token": _get_env("ZOHO_REFRESH_TOKEN"),
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(token_url, params=params)
        except httpx.RequestError as exc:
            logger.error("Zoho token request network error: %s", exc)
            raise RuntimeError(f"Zoho auth failed: network error — {exc}") from exc

    if resp.status_code != 200:
        detail = resp.text[:500]
        logger.error("Zoho token request failed [%d]: %s", resp.status_code, detail)
        raise RuntimeError(f"Zoho auth failed: HTTP {resp.status_code} — {detail}")

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        error = data.get("error", "unknown")
        raise RuntimeError(f"Zoho auth failed: no access_token in response — {error}")

    expires_in = int(data.get("expires_in", 3600))
    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = time.time() + expires_in

    logger.info("Zoho access token refreshed, expires in %ds", expires_in)
    return access_token


# ── API Request Helper ─────────────────────────────────────────────

async def _zoho_api_request(
    method: str,
    path: str,
    *,
    request_id: str = "",
    retry_count: int = 0,
) -> Optional[Dict[str, Any]]:
    """Make an authenticated request to the Zoho Sign API.

    Handles:
    - 401: auto-refreshes token and retries once
    - 429: waits 2 seconds and retries once
    - 404: returns None
    - Other errors: raises with descriptive message
    """
    token = await get_access_token()
    url = f"{_api_domain()}/api/v1{path}"
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.request(method, url, headers=headers)
        except httpx.RequestError as exc:
            logger.error("Zoho API network error [%s %s]: %s", method, path, exc)
            raise RuntimeError(f"Zoho API request failed: {exc}") from exc

    # 404 — not found
    if resp.status_code == 404:
        logger.warning("Zoho API 404: %s (requestId=%s)", path, request_id)
        return None

    # 401 — token expired, refresh and retry once
    if resp.status_code == 401 and retry_count < 1:
        logger.info("Zoho API 401 — refreshing token and retrying (requestId=%s)", request_id)
        _token_cache["access_token"] = None  # force refresh
        return await _zoho_api_request(method, path, request_id=request_id, retry_count=retry_count + 1)

    # 429 — rate limited, wait and retry once
    if resp.status_code == 429 and retry_count < 1:
        logger.warning("Zoho API 429 rate limited — waiting 2s then retrying (requestId=%s)", request_id)
        await asyncio.sleep(2)
        return await _zoho_api_request(method, path, request_id=request_id, retry_count=retry_count + 1)

    # Other errors
    if resp.status_code >= 400:
        detail = resp.text[:500]
        logger.error("Zoho API error [%d] %s (requestId=%s): %s", resp.status_code, path, request_id, detail)
        raise RuntimeError(f"Zoho Sign API error {resp.status_code}: {detail}")

    return resp.json()


# ── Signature Verification ─────────────────────────────────────────

async def verify_signature(request_id: str) -> Optional[Dict[str, Any]]:
    """Verify the digital signature status of a Zoho Sign document.

    Args:
        request_id: The Zoho Sign request ID (document ID).

    Returns:
        A structured verification result dict, or None if not found (404).
        Structure:
        {
            "zohoStatus": "completed" | "inprogress" | "expired" | "declined",
            "isFullySigned": bool,
            "signers": [{
                "name": str,
                "email": str,
                "status": "SIGNED" | "PENDING" | "DECLINED",
                "signedAt": ISO string or None,
                "ipAddress": str or None
            }],
            "completedAt": ISO string or None,
            "expiresAt": ISO string or None,
            "documentName": str or None,
            "auditTrailAvailable": bool
        }

    Raises:
        RuntimeError: If the API request fails (non-404 errors).
    """
    data = await _zoho_api_request("GET", f"/requests/{request_id}", request_id=request_id)
    if data is None:
        return None

    # Navigate Zoho's response structure
    requests_data = data.get("requests", data)
    if isinstance(requests_data, dict):
        doc = requests_data
    elif isinstance(requests_data, list) and requests_data:
        doc = requests_data[0]
    else:
        doc = data

    # Extract document-level info
    zoho_status = str(doc.get("request_status", doc.get("status", "unknown"))).lower()
    document_name = doc.get("request_name", doc.get("document_name"))

    # Map Zoho status to our categories
    status_map = {
        "completed": "completed",
        "signed": "completed",
        "inprogress": "inprogress",
        "in-progress": "inprogress",
        "pending": "inprogress",
        "expired": "expired",
        "declined": "declined",
        "recalled": "declined",
    }
    normalized_status = status_map.get(zoho_status, zoho_status)

    # Parse signers / actions
    actions = doc.get("actions", [])
    signers: List[Dict[str, Any]] = []
    all_signed = True

    for action in actions:
        signer_status_raw = str(action.get("action_status", action.get("status", "PENDING"))).upper()
        if signer_status_raw in ("SIGNED", "COMPLETED"):
            signer_status = "SIGNED"
        elif signer_status_raw in ("DECLINED", "REJECTED"):
            signer_status = "DECLINED"
            all_signed = False
        else:
            signer_status = "PENDING"
            all_signed = False

        signers.append({
            "name": action.get("recipient_name", action.get("action_name", "")),
            "email": action.get("recipient_email", action.get("email", "")),
            "status": signer_status,
            "signedAt": _parse_zoho_date(action.get("signed_time", action.get("action_time"))),
            "ipAddress": action.get("ip_address", action.get("signing_ip")),
        })

    is_fully_signed = normalized_status == "completed" and all_signed and len(signers) > 0

    return {
        "zohoStatus": normalized_status,
        "isFullySigned": is_fully_signed,
        "signers": signers,
        "completedAt": _parse_zoho_date(doc.get("completed_time", doc.get("modified_time"))),
        "expiresAt": _parse_zoho_date(doc.get("expiry_date", doc.get("validity"))),
        "documentName": document_name,
        "auditTrailAvailable": True,
    }


# ── Audit Trail ────────────────────────────────────────────────────

async def get_audit_trail(request_id: str) -> List[Dict[str, Any]]:
    """Retrieve the audit trail (history) for a Zoho Sign document.

    Args:
        request_id: The Zoho Sign request ID.

    Returns:
        List of audit events, each containing:
        {
            "action": str,
            "performedBy": str,
            "performedAt": ISO string or None,
            "ipAddress": str or None
        }

    Raises:
        RuntimeError: If the API request fails.
    """
    data = await _zoho_api_request("GET", f"/requests/{request_id}/history", request_id=request_id)
    if data is None:
        return []

    # Parse history entries
    history = data.get("history", data.get("document_history", []))
    if not isinstance(history, list):
        history = []

    events: List[Dict[str, Any]] = []
    for entry in history:
        events.append({
            "action": entry.get("action", entry.get("activity", "Unknown")),
            "performedBy": entry.get("performed_by_name", entry.get("email", entry.get("user", ""))),
            "performedAt": _parse_zoho_date(entry.get("performed_at", entry.get("time", entry.get("created_time")))),
            "ipAddress": entry.get("ip_address", entry.get("ip")),
        })

    return events


__all__ = [
    "zoho_configured",
    "get_access_token",
    "verify_signature",
    "get_audit_trail",
]
