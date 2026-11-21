"""Lỗi runtime browser. Tên lỗi là contract, giữ ổn định."""
from __future__ import annotations


class RegistryError(RuntimeError):
    pass


class LeaseBusy(RegistryError):
    """Tài nguyên đang có lease active của owner khác."""


class LeaseLost(RegistryError):
    """Lease hết hạn / bị release / fence-token không khớp. Worker phải dừng."""


class TabBusy(LeaseBusy):
    """Tab khớp đã bị task khác lease. Không tạo tab trùng."""


class TabProtected(RegistryError):
    """Tab có upload đang chạy / form chưa lưu / vùng Flag-watched: cấm navigate."""


class ProfileUnverified(RegistryError):
    """Chưa có bằng chứng chrome://version cùng window/profile yêu cầu."""


class WorkerStopped(RegistryError):
    """Worker hết quyền (lease mất/hết hạn): dừng, không replay."""
