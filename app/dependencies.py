from __future__ import annotations

import functools

import google.auth
from google.cloud import firestore
from googleapiclient.discovery import build

from app.settings import Settings


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()


@functools.lru_cache
def get_firestore_client() -> firestore.Client:
    settings = get_settings()
    return firestore.Client(
        project=settings.gcp_project_id,
        database=settings.firestore_database,
    )


def get_calendar_service():
    """Build a Google Calendar API v3 service using default credentials."""
    return build("calendar", "v3")


def get_admin_service():
    """Build a Google Admin SDK Directory service.

    C4 fix: the previous implementation called ``from_service_account_info()``
    with a ``Credentials`` object instead of a ``dict``, causing a ``TypeError``
    at runtime.  On Cloud Run the attached service account already has the
    necessary scopes via Workload Identity; we pass the scopes explicitly to
    ``google.auth.default()`` so the credential is correctly scoped for the
    Admin SDK.  Domain-wide delegation (``subject``) is handled by configuring
    the SA in Google Admin Console — no separate key file is required.
    """
    settings = get_settings()
    credentials, _ = google.auth.default(scopes=[settings.google_admin_scopes])
    return build("admin", "directory_v1", credentials=credentials)
