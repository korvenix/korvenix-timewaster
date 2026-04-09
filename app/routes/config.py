from fastapi import APIRouter, Depends

from app.auth import require_admin, verify_oidc_token
from app.dependencies import get_firestore_client
from app.firestore_client import FirestoreWrapper
from app.models import ConfigResponse, SettingsUpdate, TitleCostUpdate, UserCostUpdate

router = APIRouter(prefix="/api/config", tags=["config"])


def _get_store(client=Depends(get_firestore_client)) -> FirestoreWrapper:
    return FirestoreWrapper(client)


@router.get("", response_model=ConfigResponse)
def get_config(
    _claims: dict = Depends(verify_oidc_token),
    store: FirestoreWrapper = Depends(_get_store),
):
    return store.get_config()


@router.patch("/settings")
def update_settings(
    body: SettingsUpdate,
    _claims: dict = Depends(require_admin),
    store: FirestoreWrapper = Depends(_get_store),
):
    data = body.model_dump(by_alias=True, exclude_none=True)
    store.update_settings(data)
    return {"status": "ok"}


@router.patch("/titles/{title}")
def set_title_cost(
    title: str,
    body: TitleCostUpdate,
    # C5 fix: require admin, not just any authenticated org member.
    _claims: dict = Depends(require_admin),
    store: FirestoreWrapper = Depends(_get_store),
):
    store.set_title_cost(title, body.hourly_rate)
    return {"status": "ok", "title": title, "hourlyRate": body.hourly_rate}


@router.patch("/users/{email:path}")
def set_user_override(
    email: str,
    body: UserCostUpdate,
    # C5 fix: require admin, not just any authenticated org member.
    _claims: dict = Depends(require_admin),
    store: FirestoreWrapper = Depends(_get_store),
):
    store.set_user_override(email, body.hourly_rate)
    return {"status": "ok", "email": email, "hourlyRate": body.hourly_rate}


@router.delete("/users/{email:path}")
def delete_user_override(
    email: str,
    _claims: dict = Depends(require_admin),
    store: FirestoreWrapper = Depends(_get_store),
):
    store.delete_user_override(email)
    return {"status": "ok", "email": email}
