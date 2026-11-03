"""
Authentication & Authorization Request Dependencies
AI Powered Smart Hospital Referral System - Phase 17
"""

from fastapi import Header, HTTPException
from src.auth.jwt_utils import decode_access_token
from src.auth.rate_limiter import is_token_revoked


def require_current_user(
    authorization: str | None = Header(default=None)
):
    """
    Validate Bearer JWT token and return the authenticated user payload.
    Checks authorization header format, verifies token signature and expiration,
    and enforces distributed token revocation blocklist.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization token required."
        )

    parts = authorization.split()

    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header."
        )

    token = parts[1]

    # Explicit check against distributed token revocation blocklist
    if is_token_revoked(token):
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked."
        )

    user = decode_access_token(token)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token."
        )

    return user
