from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.dependencies import get_settings
from app.settings import Settings


def get_token_from_header(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    return auth[7:]


def verify_oidc_token(
    token: str = Depends(get_token_from_header),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Verify a Google OIDC token and enforce the hosted-domain (hd) claim.

    C2 fix: ``allowed_hd_claim`` must be explicitly set to a domain string.
    A missing / None value is treated as a server misconfiguration (500) rather
    than silently skipping the domain check.
    """
    if settings.allowed_hd_claim is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: TIMEWASTER_ALLOWED_HD_CLAIM is not set",
        )

    try:
        claims = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=settings.oidc_audience,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OIDC token",
        )

    if claims.get("hd") != settings.allowed_hd_claim:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token hd claim does not match allowed domain",
        )

    return claims


def verify_scheduler_oidc_token(
    token: str = Depends(get_token_from_header),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Verify the OIDC token sent by Cloud Scheduler.

    C1 fix: enforces a dedicated audience and, if configured, checks that the
    caller identity (email/sub) matches the expected Cloud Scheduler service account.
    """
    if not settings.scheduler_oidc_audience:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: TIMEWASTER_SCHEDULER_OIDC_AUDIENCE is not set",
        )

    try:
        claims = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=settings.scheduler_oidc_audience,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid scheduler OIDC token",
        )

    if settings.scheduler_service_account_email:
        caller_email = claims.get("email") or claims.get("sub", "")
        if caller_email != settings.scheduler_service_account_email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Caller identity does not match expected scheduler service account",
            )

    return claims


def require_admin(
    claims: dict = Depends(verify_oidc_token),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Extend verify_oidc_token with an admin-email allowlist check.

    C5 fix: config write endpoints must only be accessible by admins, not every
    authenticated org member.  Set TIMEWASTER_ADMIN_EMAILS to a comma-separated
    list of permitted addresses.
    """
    if not settings.admin_emails:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: TIMEWASTER_ADMIN_EMAILS is not set",
        )
    allowed = {e.strip() for e in settings.admin_emails.split(",") if e.strip()}
    caller_email = claims.get("email", "")
    if caller_email not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return claims
