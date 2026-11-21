"""Single-owner browser runtime: one CDP connection, SQLite leases, profile/account verify.

Hợp nhất từ 2 nguồn legacy:
- C:\\dubtool (core/browser_runtime.py, core/tab_acquisition.py,
  scripts/social_chrome_daemon.py, shared/browser_contracts.py):
  SharedStore fence/token/TTL, owner daemon single-connection, TAB_BUSY /
  TAB_PROTECTED_NO_NAVIGATE, bind_profile qua chrome://version, read-only eye.
- D:\\JARVIS-Assistant (backend/app/integrations/live_chrome_worker.py):
  connect_over_cdp tới Chrome có sẵn (không launch), verify profile cùng
  window + verify account trước/sau read, lease hợp tác qua SharedStore.

Quy tắc: KHÔNG Post thật. Worker chỉ đọc/điều hướng tab đã lease; hết quyền
(lease hết hạn/mất) thì dừng, không replay.
"""
from miro.browser.errors import (
    LeaseBusy,
    LeaseLost,
    ProfileUnverified,
    RegistryError,
    TabBusy,
    TabProtected,
    WorkerStopped,
)
from miro.browser.lease_store import LeaseStore, tab_resource
from miro.browser.runtime import AcquiredTab, BrowserRuntime

__all__ = [
    "AcquiredTab",
    "BrowserRuntime",
    "LeaseBusy",
    "LeaseLost",
    "LeaseStore",
    "ProfileUnverified",
    "RegistryError",
    "TabBusy",
    "TabProtected",
    "WorkerStopped",
    "tab_resource",
]
