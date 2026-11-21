"""Mac dinh nghiep vu theo platform (port quy uoc dubtool AGENTS.md + registry).

Moi platform co dung 1 account mac dinh — moi lenh khong ghi ro account
deu chay account nay. Chi user moi duoc doi default (set_default).
"""

from __future__ import annotations

BUSINESS_DEFAULTS: dict[str, dict] = {
    "youtube": {"account_id": "UCrUkQHY9OUP-Z_5muDDR6Bg", "display_name": "Banh Love You"},
    "facebook": {"account_id": "61595997638624", "display_name": "olichopper batch"},
    "tiktok": {"account_id": "kemkhongta", "display_name": "kemkhongta"},
    "instagram": {"account_id": "@haodaojrk5", "display_name": "haodaojrk5"},
    "threads": {"account_id": "@haodaojrk5", "display_name": "haodaojrk5"},
    "shopee": {"account_id": "haodaojr", "display_name": "haodaojr"},
    "chatgpt": {"account_id": "profile20-user", "display_name": "Profile 20 ChatGPT user"},
    "flow": {"account_id": "profile20-user", "display_name": "Profile 20 Google actor"},
}


def business_default(platform: str) -> dict | None:
    return BUSINESS_DEFAULTS.get((platform or "").strip().lower())
