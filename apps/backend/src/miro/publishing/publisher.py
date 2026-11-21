"""Unified Threads-style publisher: single implementation for Miro.

Contract (distilled from dubtool scripts/*_post_one.py + JARVIS integrations):
  - Atomic claim against TOCTOU: O_CREAT|O_EXCL on the attempt journal.
    Loser gets ALREADY_CLAIMED / UNRECONCILED_ATTEMPT and never touches browser.
  - Journal (attempt) is written BEFORE the single Post click.
  - Exactly 1 click, no retry. Any ambiguity after click -> UNKNOWN.
  - Only a verified receipt counts: owner + (tag | post_id | video) match.
  - UNKNOWN never replays; it goes to read-only reconcile.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


CLAIMED = "claimed-submit"
VERIFIED = "verified"
UNKNOWN = "unknown"


@dataclass
class Intent:
    intent_id: str
    owner: str
    text: str
    tag: str = ""
    media_sha256: str = ""


def intent_paths(root: Path, intent: Intent) -> tuple[Path, Path]:
    base = Path(root)
    journal = base / "attempts" / f"{intent.intent_id}.json"
    publication = base / "publication.json"
    return journal, publication


def claim_attempt(journal_path: Path, intent: Intent) -> dict | None:
    """Atomic claim via O_CREAT|O_EXCL. Returns skip dict if already claimed."""
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "intent_id": intent.intent_id,
        "owner": intent.owner,
        "status": CLAIMED,
        "at": time.time(),
        "text_sha256": hashlib.sha256(intent.text.encode("utf-8")).hexdigest(),
        "tag": intent.tag,
    }
    payload = json.dumps(record, ensure_ascii=False).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(str(journal_path), flags, 0o644)
    except FileExistsError:
        return {"skipped": "UNRECONCILED_ATTEMPT", "intent_id": intent.intent_id,
                "hint": "reconcile read-only, never replay"}
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    return None


def _load_publication(publication_path: Path) -> dict:
    if publication_path.exists():
        try:
            return json.loads(publication_path.read_text(encoding="utf-8"))
        except Exception:
            return {"items": []}
    return {"items": []}


def _save_publication(publication_path: Path, data: dict) -> None:
    publication_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = publication_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, publication_path)


def guard_duplicate(publication_path: Path, journal_path: Path, intent: Intent) -> dict | None:
    pub = _load_publication(publication_path)
    for item in pub.get("items", []):
        if (item.get("intent_id") == intent.intent_id
                and item.get("status") == "published" and item.get("url")):
            return {"skipped": "ALREADY_IN_PUBLICATION", "intent_id": intent.intent_id}
    if journal_path.exists():
        return {"skipped": "UNRECONCILED_ATTEMPT", "intent_id": intent.intent_id,
                "hint": "reconcile read-only, never replay"}
    return None


def verify_receipt(receipt: dict | None, intent: Intent) -> dict | None:
    """A receipt is verified only with owner + (post_id|tag|video match)."""
    if not isinstance(receipt, dict):
        return None
    if str(receipt.get("owner") or "").lower() != intent.owner.lower():
        return None
    post_id = str(receipt.get("post_id") or "").strip()
    url = str(receipt.get("url") or "").strip()
    tag = str(receipt.get("tag") or "").lower()
    has_video = bool(receipt.get("has_video", True))
    matched = False
    via = ""
    if post_id and url and post_id in url:
        matched, via = True, "post_id"
    elif intent.tag and (tag == intent.tag.lower() or intent.tag.lower() in url.lower()):
        matched, via = True, "tag"
    elif has_video and url and intent.tag.lower() in json.dumps(receipt).lower():
        matched, via = True, "tag"
    if not (matched and url):
        return None
    return {"intent_id": intent.intent_id, "status": "published",
            "url": url, "post_id": post_id or None, "match": via}


class Publisher:
    """Single unified implementation. Browser is injected (mock in tests)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "attempts").mkdir(parents=True, exist_ok=True)

    def publish(self, intent: Intent, browser) -> dict:
        journal_path, publication_path = intent_paths(self.root, intent)
        skip = guard_duplicate(publication_path, journal_path, intent)
        if skip:
            return skip
        skip = claim_attempt(journal_path, intent)
        if skip:
            return skip
        try:
            receipt = browser.post_once(intent)
        except Exception as exc:
            self._mark(journal_path, {"status": UNKNOWN, "cause": type(exc).__name__,
                                      "hint": "UNCONFIRMED_NO_REPLAY"})
            return {"intent_id": intent.intent_id, "receipt": "UNKNOWN",
                    "hint": "reconcile read-only, never replay"}
        verified = verify_receipt(receipt, intent)
        if verified:
            self._mark(journal_path, {"status": VERIFIED, **verified})
            pub = _load_publication(publication_path)
            items = [x for x in pub.get("items", [])
                     if x.get("intent_id") != intent.intent_id]
            items.append(verified)
            pub["items"] = items
            _save_publication(publication_path, pub)
            return {"posted": True, **verified}
        self._mark(journal_path, {"status": UNKNOWN, "hint": "UNCONFIRMED_NO_REPLAY"})
        return {"posted": True, "receipt": "UNCONFIRMED_NO_REPLAY",
                "intent_id": intent.intent_id}

    def reconcile(self, intent: Intent, browser) -> dict:
        """Read-only: never clicks Post. Only promotes UNKNOWN with verified receipt."""
        journal_path, publication_path = intent_paths(self.root, intent)
        if not journal_path.exists():
            return {"reconciled": False, "intent_id": intent.intent_id,
                    "hint": "no attempt journal"}
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if journal.get("status") == VERIFIED:
            return {"reconciled": True, "intent_id": intent.intent_id,
                    "already": "verified"}
        receipt = browser.read_receipt(intent)
        verified = verify_receipt(receipt, intent)
        if verified:
            self._mark(journal_path, {"status": VERIFIED, **verified})
            pub = _load_publication(publication_path)
            items = [x for x in pub.get("items", [])
                     if x.get("intent_id") != intent.intent_id]
            items.append(verified)
            pub["items"] = items
            _save_publication(publication_path, pub)
            return {"reconciled": True, **verified}
        return {"reconciled": False, "intent_id": intent.intent_id,
                "hint": "UNCONFIRMED_NO_REPLAY"}

    def _mark(self, journal_path: Path, patch: dict) -> None:
        try:
            current = json.loads(journal_path.read_text(encoding="utf-8"))
        except Exception:
            current = {}
        current.update(patch)
        tmp = journal_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, journal_path)
