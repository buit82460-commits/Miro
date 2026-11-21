"""ChatGPT adapter (MAINTAINED) — port C:\dubtool\scripts\chatgpt_post_one.py.

- run_shortcode/run_batch: 1 prompt -> Send -> _wait_reply_done (nut Stop
  bien mat + text on dinh 3 rounds) -> entry reply_sha256/reply_chars/preview.
- Du CRUD hoi thoai: read_conversation / new_chat / rename / delete /
  get_or_set_model / verify_profile.
"""
from __future__ import annotations

import hashlib
import re

from miro.adapters.core import SPECS, LiveChromeError, PlatformWorker

SPEC = SPECS["chatgpt"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)


def extract_reply(page_text: str, prompt: str) -> str:
    """Port _extract_reply: lay phan reply sau prompt."""
    text = str(page_text or "")
    idx = text.rfind(str(prompt or "").strip()[:60])
    if idx >= 0:
        return text[idx + len(str(prompt or "").strip()[:60]):].strip()
    return text.strip()[-4000:]


def reply_record(reply: str, conversation_url: str = "") -> dict:
    digest = hashlib.sha256(reply.encode("utf-8")).hexdigest()
    return {"reply_sha256": digest, "reply_chars": len(reply),
            "reply_preview": reply[:200],
            "url": conversation_url, "receipt": "SUBMITTED"}


def resolve_conversation_url(arg: str) -> str:
    text = str(arg or "").strip()
    match = re.search(r"chatgpt\.com/c/([A-Za-z0-9-]+)", text)
    if match:
        return f"https://chatgpt.com/c/{match.group(1)}"
    if re.fullmatch(r"[A-Za-z0-9-]{6,}", text):
        return f"https://chatgpt.com/c/{text}"
    raise ValueError("Need a ChatGPT conversation URL or ID.")


def read_conversation(arg: str) -> dict:
    """Read-only transcript (live tren page; offline mo ta)."""
    return {"url": resolve_conversation_url(arg), "transcript": "LIVE_ONLY",
            "hint": "read-only tren page that"}


def new_chat(account: str = "") -> dict:
    return {"account": account, "conversation": "LIVE_ONLY",
            "hint": "unsent session = draft equivalent"}


def rename_conversation(arg: str, new_title: str) -> dict:
    return {"url": resolve_conversation_url(arg), "title": new_title,
            "rename": "LIVE_ONLY"}


def delete_conversation(arg: str) -> dict:
    return {"url": resolve_conversation_url(arg), "delete": "LIVE_ONLY",
            "hint": "xoa tren page that"}


def get_or_set_model(model: str = "", account: str = "") -> dict:
    return {"account": account, "model": model or "current",
            "runtime": "button GPT switcher + [role=option]",
            "hint": "live tren page that"}


def verify_profile(account: str = "") -> dict:
    return {"account": account, "runtime": "verify_profile read-only",
            "hint": "live tren page that"}
