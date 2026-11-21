"""Shared adapter core — 1 khung cho 8 platform (port tu dubtool scripts/*_post_one.py).

Moi platform co dung 1 module mong `miro/<platform>/adapter.py` bind spec +
worker duoi day. Guard/journal/reconcile/UNKNOWN-khong-replay giu nguyen
cho tat ca; chi selector/builder/ack dac thu theo platform.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from miro.publishing.publisher import (
    atomic_save,
    claim_attempt,
    load_json_if_exists,
)


class LiveChromeError(RuntimeError):
    """Port tu dubtool social_live_chrome.LiveChromeError.

    before_submit=True -> loi truoc click (FAILED_BEFORE_POST, duoc thu lai).
    False/sau click -> UNKNOWN (chi reconcile read-only, KHONG replay).
    """

    def __init__(self, message: str, before_submit: bool = False):
        super().__init__(message)
        self.before_submit = before_submit


@dataclass
class AdapterSpec:
    """Dac thu 1 platform. kind: caption (social) | prompt (chat/gen) | product."""

    id: str
    publication: str
    job_prefix: str
    kind: str = "caption"
    max_chars: int = 500
    entry_url: str = ""
    ack_hints: tuple = ()
    unsupported: tuple = ()
    account_hint: str = ""


SPECS: dict[str, AdapterSpec] = {
    "threads": AdapterSpec(
        id="threads", publication="publication-threads.json",
        job_prefix="threads-", max_chars=500,
        entry_url="https://www.threads.com/",
        ack_hints=("graphql", "media/configure", "/api/v1/", "broadcast"),
        unsupported=("delete", "draft", "audience"),
        account_hint="@haodaojrk5"),
    "facebook": AdapterSpec(
        id="facebook", publication="publication-facebook.json",
        job_prefix="olichopper-fb-", max_chars=2200,
        entry_url="https://www.facebook.com/",
        ack_hints=("reel", "publish"),
        unsupported=("draft",),
        account_hint="61595997638624"),
    "tiktok": AdapterSpec(
        id="tiktok", publication="publication.json",
        job_prefix="tiktok-", max_chars=2200,
        entry_url="https://www.tiktok.com/tiktokstudio/upload?lang=en",
        ack_hints=("upload", "publish"),
        unsupported=(),
        account_hint="@kemkhongta"),
    "instagram": AdapterSpec(
        id="instagram", publication="publication-instagram.json",
        job_prefix="instagram-", max_chars=2200,
        entry_url="https://www.instagram.com/",
        ack_hints=("/api/v1/media/configure",),
        unsupported=("draft", "audience", "caption_edit"),
        account_hint="Profile 20 actor"),
    "youtube": AdapterSpec(
        id="youtube", publication="publication-youtube.json",
        job_prefix="youtube-", kind="caption", max_chars=4500,
        entry_url="https://www.googleapis.com/youtube/v3",
        ack_hints=("videos.list",),
        unsupported=(),
        account_hint="Banh Love You (UCrUkQHY9OUP-Z_5muDDR6Bg, default)"),
    "shopee": AdapterSpec(
        id="shopee", publication="publication-shopee.json",
        job_prefix="shopee-", kind="product", max_chars=3000,
        entry_url="https://shopee.vn/",
        ack_hints=("seller centre readback",),
        unsupported=("delete", "draft"),
        account_hint="haodaojr (BLOCKED: onboarding 1/5)"),
    "chatgpt": AdapterSpec(
        id="chatgpt", publication="publication-chatgpt.json",
        job_prefix="chatgpt-", kind="prompt", max_chars=8000,
        entry_url="https://chatgpt.com/",
        ack_hints=("streaming done",),
        unsupported=(),
        account_hint="Profile 20 ChatGPT user"),
    "flow": AdapterSpec(
        id="flow", publication="publication-flow.json",
        job_prefix="flow-", kind="prompt", max_chars=4000,
        entry_url="https://flow.google.com/",
        ack_hints=("video src stable",),
        unsupported=("delete", "draft"),
        account_hint="Profile 20 Google actor"),
}


def _norm(text) -> str:
    return str(text or "").replace("\r\n", "\n").strip()


def unique_tag(item: dict) -> str:
    code = re.sub(r"\D", "", str(item.get("shortcode") or ""))
    return f"#dub{(code[-6:] if code else '000000')}"


def text_for(spec: AdapterSpec, item: dict) -> str:
    """caption_for / prompt_for / product_for — port 8 adapter dubtool."""
    if spec.kind == "product":
        name = _norm(item.get("name") or item.get("title"))
        price = item.get("price", 0)
        stock = item.get("stock", 0)
        desc = _norm(item.get("description") or item.get("desc"))
        if not name:
            raise ValueError("Need product name.")
        if int(price) <= 0:
            raise ValueError("Need price>0.")
        if int(stock) < 0:
            raise ValueError("Need stock>=0.")
        if len(desc) > spec.max_chars:
            raise ValueError(f"Product desc exceeds {spec.max_chars} chars.")
        return f"{name}\n\n{desc}".strip() if desc else name
    if spec.kind == "prompt":
        text = _norm(item.get("prompt") or item.get("message")
                      or item.get("text") or item.get("question"))
        if not text:
            raise ValueError("Need nonempty prompt.")
        if len(text) > spec.max_chars:
            raise ValueError(f"Prompt exceeds {spec.max_chars} chars.")
        return text
    title = _norm(item.get("title"))
    description = _norm(item.get("description") or item.get("caption")
                        or item.get("text"))
    if description and (title == description or re.match(r"^Video by \S+$", title)):
        title = ""
    parts = [p for p in (title, description) if p]
    body = "\n\n".join(parts)
    raw_tags = item.get("tags") or item.get("hashtags") or []
    tags = [str(t).strip().lstrip("#") for t in raw_tags if str(t).strip().lstrip("#")]
    missing = [t for t in tags if f"#{t}".lower() not in body.lower()]
    if missing:
        parts.append(" ".join(f"#{t}" for t in missing))
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError("Need nonempty text (title/description/tags).")
    tag = unique_tag(item)
    needs = [tag] if tag.lower() not in text.lower() else []
    if len(text) > spec.max_chars - 20:
        words = text.split()
        keep = []
        for w in words:
            cand = " ".join(keep + [w] + needs)
            if len(cand) > spec.max_chars - 20:
                if w.startswith("#"):
                    continue
                break
            keep.append(w)
        text = " ".join(keep).strip() or text[:spec.max_chars - 20].strip()
    if needs:
        text = f"{text}\n\n{needs[0]}"
    if len(text) > spec.max_chars:
        raise ValueError(f"Text exceeds {spec.max_chars} characters.")
    return text


def job_id_for(spec: AdapterSpec, item: dict) -> str:
    return spec.job_prefix + str(item["shortcode"]).rstrip("-").replace("/", "")


def guard_duplicate(spec: AdapterSpec, base: Path, shortcode: str,
                    journal_name: str, attempts_dir: Path) -> dict | None:
    """Guard 2 lop giong publisher.guard_duplicate nhung theo spec platform."""
    publication = load_json_if_exists(Path(base) / spec.publication, {"items": []})
    if any(x.get("shortcode") == shortcode
           and x.get("status") in ("submitted", "published")
           and x.get("url") for x in publication.get("items", [])):
        return {"skipped": "ALREADY_IN_PUBLICATION", "shortcode": shortcode}
    if (Path(attempts_dir) / journal_name).exists():
        return {"skipped": "UNRECONCILED_ATTEMPT", "shortcode": shortcode,
                "hint": "reconcile read-only, never replay"}
    return None


def merge_publication(spec: AdapterSpec, base: Path, entry: dict,
                      account: str) -> dict:
    publication = load_json_if_exists(Path(base) / spec.publication, {"items": []})
    items = [x for x in publication.get("items", [])
             if x.get("shortcode") != entry["shortcode"]]
    items.append(entry)
    publication["account"] = str(account or "").strip().lstrip("@")
    publication["items"] = items
    atomic_save(Path(base) / spec.publication, publication)
    return publication


class PlatformWorker:
    """Worker 2-phase dung chung 8 platform (port run_batch dubtool).

    - Phase A: guard -> validate text/media -> journal submit TRUOC click ->
      page.submit_once 1 click -> ack check. UNKNOWN/disconnect -> break,
      item sau KHONG submit.
    - Phase B: group reconcile read-only qua page.reconcile(item).
    - Page la interface inject (fake trong test, Playwright production).
    """

    def __init__(self, spec: AdapterSpec):
        self.spec = spec

    def run_batch(self, items: list[dict], base, account: str,
                  page_factory, attempts_dir=None) -> dict:
        from pathlib import Path as _P
        base = _P(base)
        attempts = _P(attempts_dir) if attempts_dir else base / "attempts"
        attempts.mkdir(parents=True, exist_ok=True)
        started = time.time()
        results: list[dict] = []
        page = None
        try:
            page = page_factory()
        except Exception as exc:
            return {"results": [
                {"shortcode": i.get("shortcode", "?"), "receipt": "UNKNOWN",
                 "cause": type(exc).__name__,
                 "hint": "NO_MANAGED_TAB: never replay"} for i in items],
                "report": {"submitted": [], "total_s": 0.0}}
        submitted: list[str] = []
        ambiguous = False
        try:
            for item in items:
                sc = str(item.get("shortcode") or "")
                jid = job_id_for(self.spec, item)
                skip = guard_duplicate(self.spec, base, sc, f"{jid}.json", attempts)
                if skip:
                    results.append({**skip, "platform": self.spec.id})
                    continue
                if ambiguous:
                    results.append({"shortcode": sc, "receipt": "UNKNOWN",
                                    "cause": "STOP_AFTER_AMBIGUOUS",
                                    "hint": "earlier ack ambiguous; never replay"})
                    continue
                try:
                    text = text_for(self.spec, item)
                except ValueError as exc:
                    results.append({"shortcode": sc,
                                    "error": "FAILED_BEFORE_POST",
                                    "cause": str(exc)[:160]})
                    continue
                journal = attempts / f"{jid}.json"
                dup = claim_attempt(journal, {"status": "submit", "shortcode": sc,
                                             "platform": self.spec.id,
                                             "account": account, "text": text[:200]})
                if dup:
                    results.append({**dup, "shortcode": sc})
                    continue
                try:
                    ack = page.submit_once({"shortcode": sc, "text": text,
                                            "account": account, "item": item})
                except LiveChromeError as exc:
                    if exc.before_submit:
                        results.append({"shortcode": sc,
                                        "error": "FAILED_BEFORE_POST",
                                        "cause": str(exc)[:160]})
                    else:
                        ambiguous = True
                        results.append({"shortcode": sc, "receipt": "UNKNOWN",
                                        "cause": str(exc)[:160],
                                        "hint": "UNCONFIRMED_NO_REPLAY"})
                    continue
                except Exception as exc:
                    ambiguous = True
                    results.append({"shortcode": sc, "receipt": "UNKNOWN",
                                    "cause": type(exc).__name__,
                                    "hint": "UNCONFIRMED_NO_REPLAY"})
                    continue
                submitted.append(sc)
                atomic_save(journal, {"status": "submitted", "shortcode": sc,
                                      "platform": self.spec.id, "ack": ack})
                results.append({"shortcode": sc, "posted": True,
                                "receipt": (ack or {}).get("receipt", "SUBMITTED"),
                                "url": (ack or {}).get("url", "")})
            reconciled = []
            try:
                for item in items:
                    sc = str(item.get("shortcode") or "")
                    rec = page.reconcile({"shortcode": sc, "account": account,
                                          "item": item})
                    if isinstance(rec, dict) and rec.get("url"):
                        entry = {"shortcode": sc, "url": rec["url"],
                                 "status": "published" if rec.get("verified")
                                 else "submitted"}
                        merge_publication(self.spec, base, entry, account)
                        reconciled.append(sc)
            except Exception:
                pass
            return {"results": results,
                    "report": {"submitted": submitted, "reconciled": reconciled,
                               "total_s": round(time.time() - started, 1)}}
        finally:
            try:
                if page is not None:
                    page.release()
            except Exception:
                pass
