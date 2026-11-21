"""Connections router — account/profile/thiet bi/trang thai ket noi."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from miro.browser.errors import RegistryError
from miro.connections import service
from miro.connections.models import AccountCreate, AccountOut, VerifyEvidence

router = APIRouter(prefix="/connections", tags=["connections"])


class ReconnectRequest(BaseModel):
    evidence: VerifyEvidence
    credential_ref: str = ""


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except RegistryError as exc:
        message = str(exc)
        code = 404 if message.startswith("ACCOUNT_NOT_FOUND") else 400
        raise HTTPException(status_code=code, detail=message) from None


@router.post("/accounts", status_code=status.HTTP_201_CREATED, response_model=AccountOut)
def add_account(body: AccountCreate) -> AccountOut:
    return _guard(service.add_account, body)


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(platform: str = "", status: str = "") -> list[AccountOut]:
    return service.list_accounts(platform, status)


@router.get("/accounts/{account_id:path}", response_model=AccountOut)
def get_account(account_id: str) -> AccountOut:
    return _guard(service.get_account, account_id)


@router.post("/accounts/{account_id:path}/verify", response_model=AccountOut)
def verify_account(account_id: str, evidence: VerifyEvidence) -> AccountOut:
    return _guard(service.verify_account, account_id, evidence)


@router.post("/accounts/{account_id:path}/pause", response_model=AccountOut)
def pause_account(account_id: str) -> AccountOut:
    return _guard(service.pause_account, account_id)


@router.post("/accounts/{account_id:path}/reconnect", response_model=AccountOut)
def reconnect_account(account_id: str, body: ReconnectRequest) -> AccountOut:
    return _guard(service.reconnect_account, account_id, body.evidence, body.credential_ref)


@router.post("/accounts/{account_id:path}/revoke", response_model=AccountOut)
def revoke_account(account_id: str) -> AccountOut:
    return _guard(service.revoke_account, account_id)


@router.post("/accounts/{account_id:path}/default", response_model=AccountOut)
def set_default(account_id: str) -> AccountOut:
    return _guard(service.set_default, account_id)


@router.get("/defaults/{platform}")
def resolve_default(platform: str) -> dict:
    return service.resolve_default(platform)


class MockTab(BaseModel):
    """Mock tab de test verify: doc observed identity tu snapshot, khong doc cookie/token."""

    tab_id: str = Field(min_length=1)
    platform_id: str = Field(min_length=1)
    profile_binding_id: str = ""
    observed_account_id: str = Field(min_length=1)
    target_id: str = ""


@router.post("/mock/verify-tab", response_model=AccountOut)
def mock_verify_tab(account_id: str, tab: MockTab) -> AccountOut:
    evidence = VerifyEvidence(
        tab_id=tab.tab_id,
        platform_id=tab.platform_id,
        profile_binding_id=tab.profile_binding_id,
        observed_account_id=tab.observed_account_id,
        target_id=tab.target_id,
    )
    return _guard(service.verify_account, account_id, evidence)
