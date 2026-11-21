"""Pydantic models cho Connections.

Quy ước (port từ dubtool + JARVIS-Assistant):
- Mỗi account gắn đúng 1 platform + 1 profile binding (thiết bị/Chrome profile).
- Credential CHỈ lưu tham chiếu (vault:/ref:/env:/keychain:/oauth:), không plaintext.
- Verify danh tính thật: đúng account + đúng tab (platform + profile binding khớp,
  observed account từ provider khớp expected) mới chuyển connected.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    platform: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    display_name: str = ""
    credential_ref: str = Field(min_length=1)
    profile_binding_id: str = ""
    browser_instance_id: str = ""


class VerifyEvidence(BaseModel):
    """Bằng chứng từ đúng tab đang mở: provider đọc observed identity trên tab này."""

    tab_id: str = Field(min_length=1)
    platform_id: str = Field(min_length=1)
    profile_binding_id: str = ""
    observed_account_id: str = Field(min_length=1)
    target_id: str = ""


class AccountOut(BaseModel):
    id: str
    platform: str
    account_id: str
    display_name: str = ""
    credential_ref: str | None = None
    profile_binding_id: str = ""
    browser_instance_id: str = ""
    is_default: bool = False
    status: str
    verified_at: float | None = None
    verified_target_id: str = ""
    evidence_sha: str = ""
