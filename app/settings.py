from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gcp_project_id: str = ""
    # Required: must be set in env (e.g. "example.com"). None means unconfigured —
    # auth.py treats that as a hard 500 rather than a silent bypass.
    allowed_hd_claim: str | None = None
    oidc_audience: str = ""
    # Separate audience expected on Cloud Scheduler OIDC tokens.
    scheduler_oidc_audience: str = ""
    # Email of the Cloud Scheduler service account (checked against OIDC sub/email).
    scheduler_service_account_email: str = ""
    google_calendar_scopes: str = "https://www.googleapis.com/auth/calendar.readonly"
    google_admin_scopes: str = "https://www.googleapis.com/auth/admin.directory.user.readonly"
    firestore_database: str = "(default)"
    title_cache_ttl_seconds: int = 3600
    delegated_admin_email: str = ""
    # Comma-separated list of email addresses allowed to call admin (write-config) endpoints.
    admin_emails: str = ""

    model_config = {"env_prefix": "TIMEWASTER_"}
