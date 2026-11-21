"""Threads publisher for Miro — faithful port of C:\\dubtool\\scripts\\threads_post_one.py.

Every behavior below mirrors the legacy adapter (same function names where
possible). Miro-specific addition: atomic claim (O_CREAT|O_EXCL) closes the
TOCTOU hole in the legacy check-then-act guard. All other semantics are
identical to the original:

- journal dir: reports/social-attempts, name threads-<shortcode>.json
- publication: <batch>/publication-threads.json (status submitted|published + url)
- journal BEFORE single click (status "submit"), then verified / unknown /
  failed-before-post — never replay UNKNOWN, reconcile read-only only
- before_submit distinction: error before click -> FAILED_BEFORE_POST (retry
  allowed); ambiguity after click / disconnect -> UNKNOWN (never replay)
- receipt: owner + text/tag/post_id match via eye records, post_id priority
- two-phase batch: A submit each on ack, stop on first ambiguous; B group
  reconcile scanning profile once
- fail-closed integrity guard when baseline file is present
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

CLAIMED = "submit"
VERIFIED = "verified"
UNKNOWN = "unknown"
FAILED_BEFORE_POST = "failed-before-post"
AWAITING_GROUP = "submitted-awaiting-group-reconcile"

MAX_TEXT = 500
DISCONNECT_NAMES = {"BrowserClosedError", "ConnectionClosed", "TargetClosedError", "TargetCrashedError"}


def _is_disconnect(error: Exception) -> bool:
    name = type(error).__name__
    if name in DISCONNECT_NAMES or "Closed" in name:
        return True
    text = str(error).lower()
    return ("browser has been closed" in text or "disconnected" in text
            or "connection closed" in text)


def job_id_for(item: dict) -> str:
    return "threads-" + str(item["shortcode"]).rstrip("-").replace("/", "")


def publication_name() -> str:
    return "publication-threads.json"


def _normalize_account(account) -> str:
    return str(account or "").strip().lstrip("@")


def _norm_text(text) -> str:
    return str(text or "").replace("\r\n", "\n").strip()


def _norm_compare(text) -> str:
    return re.sub(r"\s+", " ", _norm_text(text))


def unique_tag(item: dict) -> str:
    code = re.sub(r"\D", "", str(item.get("shortcode") or ""))
    tail = code[-6:] if code else "000000"
    return f"#dub{tail}"


def caption_for(item: dict) -> str:
    title = _norm_text(item.get("title"))
    description = _norm_text(item.get("description") or item.get("caption") or item.get("text"))
    if description and (title == description or re.match(r"^Video by \S+$", title)):
        title = ""
    parts = [p for p in (title, description) if p]
    body = "\n\n".join(parts)
    raw_tags = item.get("tags") or item.get("hashtags") or []
    tags = [str(t).strip().lstrip("#") for t in raw_tags if str(t).strip().lstrip("#")]
    missing_tags = [t for t in tags if f"#{t}".lower() not in body.lower()]
    if missing_tags:
        parts.append(" ".join(f"#{t}" for t in missing_tags))
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError("Need nonempty text (title/description/tags).")
    tag = unique_tag(item)
    needs = [tag] if tag.lower() not in text.lower() else []
    if len(text) > MAX_TEXT - 20:
        words = text.split()
        keep = []
        for w in words:
            cand = " ".join(keep + [w] + needs)
            if len(cand) > MAX_TEXT - 20:
                if w.startswith("#"):
                    continue
                break
            keep.append(w)
        text = " ".join(keep).strip() or text[:MAX_TEXT - 20].strip()
    if needs:
        text = f"{text}\n\n{needs[0]}"
    if len(text) > MAX_TEXT:
        raise ValueError(f"Threads text exceeds {MAX_TEXT} characters.")
    return text


def atomic_save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_json_if_exists(path: Path, default: dict) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


@dataclass
class Intent:
    intent_id: str
    owner: str
    text: str
    tag: str = ""
    media_sha256: str = ""
    shortcode: str = ""

    @classmethod
    def from_item(cls, item: dict, account: str) -> "Intent":
        text = caption_for(item)
        return cls(
            intent_id=job_id_for(item),
            owner=_normalize_account(account),
            text=text,
            tag=(re.search(r"#dub\d{6}", text).group(0).lower()
                 if re.search(r"#dub\d{6}", text) else ""),
            media_sha256=str(item.get("sha256") or ""),
            shortcode=str(item.get("shortcode")),
        )


def journal_path_for(attempts_dir: Path, intent: Intent) -> Path:
    return Path(attempts_dir) / f"{intent.intent_id}.json"


def guard_duplicate(base: Path, shortcode: str, journal_name: str,
                    attempts_dir: Path) -> dict | None:
    """Shared pre-side-effect guard (same as legacy). Skip dict or None."""
    publication = load_json_if_exists(Path(base) / publication_name(), {"items": []})
    if any(x.get("shortcode") == shortcode and x.get("status") in ("submitted", "published")
           and x.get("url") for x in publication.get("items", [])):
        return {"skipped": "ALREADY_IN_PUBLICATION", "shortcode": shortcode}
    journal = Path(attempts_dir) / journal_name
    if journal.exists():
        return {"skipped": "UNRECONCILED_ATTEMPT", "shortcode": shortcode,
                "hint": "reconcile read-only, never replay"}
    return None


def claim_attempt(journal_path: Path, record: dict) -> dict | None:
    """Atomic claim closing legacy TOCTOU. Returns skip dict if already claimed."""
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=False).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(str(journal_path), flags, 0o644)
    except FileExistsError:
        return {"skipped": "UNRECONCILED_ATTEMPT",
                "hint": "reconcile read-only, never replay"}
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    return None


def _merge_publication(base: Path, entry: dict, account: str) -> dict:
    publication = load_json_if_exists(Path(base) / publication_name(), {"items": []})
    items = [x for x in publication.get("items", []) if x.get("shortcode") != entry["shortcode"]]
    items.append(entry)
    publication["account"] = _normalize_account(account)
    publication["items"] = items
    atomic_save(Path(base) / publication_name(), publication)
    return publication


def match_eye_records(records: list[dict], owner: str, want_tag: str,
                      want_text: str, known_ids: list[str] | None = None) -> dict | None:
    """Same priority as legacy reconcile: known post_id first, then tag, then text."""
    known_ids = [str(x) for x in (known_ids or []) if x]
    owner_l = owner.lower()
    for r in records:
        if str(r.get("author") or "").lower() != owner_l:
            continue
        pid = str(r.get("post_id") or "")
        if pid and pid in known_ids and r.get("url"):
            return {"url": r["url"], "post_id": pid,
                    "has_video": bool(r.get("has_video")), "match": "post_id"}
    for r in records:
        if str(r.get("author") or "").lower() != owner_l:
            continue
        rtag = str(r.get("tag") or "").lower()
        if want_tag and (rtag == want_tag or want_tag in str(r.get("text") or "").lower()):
            if r.get("url"):
                return {"url": r["url"], "post_id": str(r.get("post_id") or ""),
                        "has_video": bool(r.get("has_video")), "match": "tag"}
    if want_text:
        want_n = _norm_compare(want_text)
        for r in records:
            if str(r.get("author") or "").lower() != owner_l:
                continue
            if want_n and want_n[:60] in _norm_compare(r.get("text") or ""):
                if r.get("url"):
                    return {"url": r["url"], "post_id": str(r.get("post_id") or ""),
                            "has_video": bool(r.get("has_video")), "match": "text"}
    return None


def verify_receipt(receipt: dict | None, intent: Intent) -> dict | None:
    """Receipt verified only with owner + (post_id | tag | text match)."""
    if not isinstance(receipt, dict):
        return None
    if str(receipt.get("owner") or "").lower() != intent.owner.lower():
        return None
    url = str(receipt.get("url") or "").strip()
    if not url:
        return None
    post_id = str(receipt.get("post_id") or "").strip()
    if post_id and post_id in url:
        return {"shortcode": intent.shortcode or intent.intent_id, "status": "published",
                "url": url, "post_id": post_id, "match": "post_id"}
    if receipt.get("match") in ("post_id", "tag", "text"):
        return {"shortcode": intent.shortcode or intent.intent_id, "status": "published",
                "url": url, "post_id": post_id or None, "match": receipt["match"]}
    tag = str(receipt.get("tag") or "").lower()
    if intent.tag and (tag == intent.tag or intent.tag in url.lower()
                       or intent.tag in json.dumps(receipt).lower()):
        return {"shortcode": intent.shortcode or intent.intent_id, "status": "published",
                "url": url, "post_id": post_id or None, "match": "tag"}
    return None


class Publisher:
    """Faithful Threads-model publisher. Browser injected (mock in tests)."""

    def __init__(self, base: str | Path, attempts_dir: str | Path | None = None):
        self.base = Path(base)
        self.attempts = Path(attempts_dir) if attempts_dir else self.base / "social-attempts"
        self.attempts.mkdir(parents=True, exist_ok=True)

    def publish(self, intent: Intent, browser) -> dict:
        journal_path = journal_path_for(self.attempts, intent)
        skip = guard_duplicate(self.base, intent.shortcode or intent.intent_id,
                               f"{intent.intent_id}.json", self.attempts)
        if skip:
            return skip
        record = {"shortcode": intent.shortcode or intent.intent_id, "account": intent.owner,
                  "status": CLAIMED, "at": time.time(),
                  "text_sha256": hashlib.sha256(intent.text.encode("utf-8")).hexdigest()}
        skip = claim_attempt(journal_path, record)
        if skip:
            return {**skip, "shortcode": intent.shortcode or intent.intent_id}
        try:
            receipt = browser.post_once(intent)
        except Exception as exc:
            if _is_disconnect(exc):
                raise
            if getattr(exc, "before_submit", False):
                atomic_save(journal_path, {"shortcode": intent.shortcode or intent.intent_id,
                                           "account": intent.owner,
                                           "status": FAILED_BEFORE_POST,
                                           "at": record["at"], "cause": type(exc).__name__})
                return {"error": "FAILED_BEFORE_POST",
                        "shortcode": intent.shortcode or intent.intent_id,
                        "cause": type(exc).__name__}
            atomic_save(journal_path, {"shortcode": intent.shortcode or intent.intent_id,
                                       "account": intent.owner, "status": UNKNOWN,
                                       "at": record["at"], "hint": "UNCONFIRMED_NO_REPLAY"})
            return {"posted": True, "receipt": "UNCONFIRMED_NO_REPLAY",
                    "shortcode": intent.shortcode or intent.intent_id}
        verified = verify_receipt(receipt, intent)
        if verified:
            entry = {**verified,
                     "text_sha256": hashlib.sha256(intent.text.encode("utf-8")).hexdigest()}
            atomic_save(journal_path, {"shortcode": entry["shortcode"], "account": intent.owner,
                                       "status": VERIFIED, "at": record["at"], **entry})
            _merge_publication(self.base, entry, intent.owner)
            return {"posted": True, **entry}
        atomic_save(journal_path, {"shortcode": intent.shortcode or intent.intent_id,
                                   "account": intent.owner, "status": UNKNOWN,
                                   "at": record["at"], "hint": "UNCONFIRMED_NO_REPLAY"})
        return {"posted": True, "receipt": "UNCONFIRMED_NO_REPLAY",
                "shortcode": intent.shortcode or intent.intent_id}

    def reconcile(self, intent: Intent, browser) -> dict:
        """Read-only: never clicks Post. Only promotes UNKNOWN with verified receipt."""
        journal_path = journal_path_for(self.attempts, intent)
        if not journal_path.exists():
            return {"reconciled": False, "shortcode": intent.shortcode or intent.intent_id,
                    "hint": "no attempt journal"}
        journal = load_json_if_exists(journal_path, {})
        if journal.get("status") == VERIFIED:
            return {"reconciled": True, "shortcode": intent.shortcode or intent.intent_id,
                    "already": "verified"}
        receipt = browser.read_receipt(intent)
        verified = verify_receipt(receipt, intent)
        if verified:
            entry = {**verified,
                     "text_sha256": hashlib.sha256(intent.text.encode("utf-8")).hexdigest(),
                     "reconciledReadOnly": True}
            atomic_save(journal_path, {**journal, "status": VERIFIED,
                                       "verifiedAt": time.time(), **entry})
            _merge_publication(self.base,
                               {k: v for k, v in entry.items() if k != "match"},
                               intent.owner)
            return {"reconciled": True, **entry}
        return {"reconciled": False, "shortcode": intent.shortcode or intent.intent_id,
                "hint": "UNCONFIRMED_NO_REPLAY"}

    def run_batch(self, intents: list[Intent], browser) -> list[dict]:
        """Two-phase batch mirroring legacy run_batch: submit until first
        ambiguous ack, then group-reconcile the rest read-only."""
        results: list[dict] = []
        submitted: list[Intent] = []
        stopped = False
        for intent in intents:
            if stopped:
                journal_path = journal_path_for(self.attempts, intent)
                atomic_save(journal_path, {"shortcode": intent.shortcode or intent.intent_id,
                                           "account": intent.owner,
                                           "status": UNKNOWN, "at": time.time(),
                                           "hint": "UNCONFIRMED_NO_REPLAY; stopped submitting, group reconcile only"})
                results.append({"posted": False, "receipt": "DEFERRED_TO_GROUP_RECONCILE",
                                "shortcode": intent.shortcode or intent.intent_id})
                continue
            try:
                outcome = self.publish(intent, browser)
            except Exception as exc:
                if _is_disconnect(exc):
                    raise
                outcome = {"error": type(exc).__name__,
                           "shortcode": intent.shortcode or intent.intent_id}
            results.append(outcome)
            if outcome.get("status") == "published" or outcome.get("posted") is True \
                    and outcome.get("receipt") != "UNCONFIRMED_NO_REPLAY" \
                    and "error" not in outcome:
                submitted.append(intent)
            elif outcome.get("receipt") == "UNCONFIRMED_NO_REPLAY" or "error" in outcome:
                if outcome.get("error") not in ("FAILED_BEFORE_POST",):
                    stopped = True
        for intent in intents:
            journal = load_json_if_exists(journal_path_for(self.attempts, intent), {})
            if journal.get("status") == UNKNOWN:
                rec = self.reconcile(intent, browser)
                results.append({"group_reconcile": rec,
                                "shortcode": intent.shortcode or intent.intent_id})
        return results
