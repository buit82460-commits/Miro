"""Threads publisher for Miro — port of C:\\dubtool\\scripts\\threads_post_one.py.

Legacy source & mapping (vong 1, Checker verify-publisher.md):
- caption_for / unique_tag : threads_post_one.py:128-168 — port giong het.
- journal/publication layout + guard_duplicate : threads_post_one.py:228,
  run_batch two-phase : threads_post_one.py:744-901 — port giu nguyen.
- single submit : _post_live_chrome_on_page :670-700 — journal giu "submit"
  khi loi sau click roi RE-RAISE de caller (run_batch) ghi unknown + dung
  submit; khong tu ghi UNKNOWN tai cho.
- receipt : core/rea_eye.py:31-53 (match_eye_records: post_id trong want_ids
  truoc, roi exact tag equality sau normalize, CUNG 1 record; khong co text
  fallback) + _match_post_on_page/_reconcile_group + run_reconcile:1019
  (known_ids = journal ack_post_codes).
- JSON runtime : shared/execution_policy.atomic_save (UTF-8 no-BOM,
  tmp+replace) + shared/json_io.load_json/load_json_if_exists (chiu BOM).
  Miro goi thang code cu qua bien import ro (xem _legacy). Khi C:\\dubtool
  khong mount duoc, fallback copy local giu semantics + ghi ro ly do.
- media gate : media_for/check_video/probe_video :171-225 — port day du;
  publish cam khi co media chua verify (out-of-scope: khong attach bytes).
- integrity guard : _enforce_adapter_integrity :93-105 — port fail-closed:
  neu thay baseline file thi tu choi truoc moi side-effect.
- actor/tab lease : _verify_threads_actor :251-268 + _acquire_threads_tab
  :646-668 — uy thac cho browser inject NHUNG bat buoc contract:
  browser phai verify actor @username truoc Post (goi browser.verify_actor
  neu co, neu khong thi assert browser da lam qua declared_actor).
- Cai tien co chu y duy nhat: claim_attempt dung O_CREAT|O_EXCL dong TOCTOU
  cua legacy check-then-act (da khai bao, co test 2-thread).

Scope cam (ghi ro theo Checker muc 7):
- Media attach bytes: OUT-OF-SCOPE — Intent co media_sha256/media_path thi
  publish() tu choi FAILED_BEFORE_POST (ma MEDIA_NOT_PORTED), khong bao gio
  post "chay" khi chua gate video.
- Browser that (CDP/Profile 20/tab lease): OUT-OF-SCOPE — browser inject
  phai tuan thu contract verify actor; khong co browser that trong Miro.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# ---- Bien goi code cu (dieu kien bat buoc 1) ----
# Import thang shared/execution_policy + shared/json_io + core/rea_eye cua
# C:\\dubtool. Grep: dubtool|sys.path|legacy.
_DUBTOOL_ROOT = Path(r"C:\dubtool")
if str(_DUBTOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_DUBTOOL_ROOT))
_legacy = {"atomic_save": None, "load_json": None, "load_json_if_exists": None,
           "eye_match": None, "eye_norm": None, "caption_for": None,
           "guard_duplicate": None}
try:  # noqa: E402
    from shared.execution_policy import atomic_save as _dub_atomic_save  # type: ignore
    _legacy["atomic_save"] = _dub_atomic_save
except Exception:
    pass
try:  # noqa: E402
    from shared.json_io import load_json as _dub_load_json, load_json_if_exists as _dub_load_if_exists  # type: ignore
    _legacy["load_json"] = _dub_load_json
    _legacy["load_json_if_exists"] = _dub_load_if_exists
except Exception:
    pass
try:  # noqa: E402
    from core.rea_eye import match_eye_records as _dub_eye_match, normalize_tag as _dub_eye_norm  # type: ignore
    _legacy["eye_match"] = _dub_eye_match
    _legacy["eye_norm"] = _dub_eye_norm
except Exception:
    pass
try:  # noqa: E402
    import threads_post_one as _legacy_threads  # type: ignore  # scripts/threads_post_one.py
    _legacy["caption_for"] = _legacy_threads.caption_for
    _legacy["guard_duplicate"] = _legacy_threads.guard_duplicate
except Exception:
    try:  # noqa: E402
        from scripts import threads_post_one as _legacy_threads2  # type: ignore
        _legacy["caption_for"] = _legacy_threads2.caption_for
        _legacy["guard_duplicate"] = _legacy_threads2.guard_duplicate
    except Exception:
        pass

CLAIMED = "submit"
VERIFIED = "verified"
UNKNOWN = "unknown"
FAILED_BEFORE_POST = "failed-before-post"
AWAITING_GROUP = "submitted-awaiting-group-reconcile"

MAX_TEXT = 500
DISCONNECT_NAMES = {"BrowserClosedError", "ConnectionClosed", "TargetClosedError", "TargetCrashedError"}

THREADS_VIDEO_MAX_MB = 100
THREADS_VIDEO_MAX_S = 300


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


# ---- JSON runtime: dung code cu, fallback copy co ghi nguon ----
def atomic_save(path: Path, data: dict) -> None:
    """shared/execution_policy.atomic_save cua dubtool (UTF-8 no-BOM, tmp+replace).

    Fallback copy local chi dung khi C:\\dubtool khong import duoc (Miro chay
    doc lap). Semantics giu nguyen: tmp file rieng + os.replace.
    """
    if _legacy["atomic_save"] is not None:
        _legacy["atomic_save"](Path(path), data)
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".miro-tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    try:
        with open(tmp, "rb") as handle:
            os.fsync(handle.fileno())
    except OSError:
        pass
    os.replace(tmp, path)


def load_json_if_exists(path: Path, default: dict) -> dict:
    """shared/json_io.load_json_if_exists cua dubtool (chiu BOM utf-8-sig).

    Fallback copy local chi dung khi C:\\dubtool khong import duoc.
    """
    if _legacy["load_json_if_exists"] is not None:
        try:
            out = _legacy["load_json_if_exists"](Path(path), default)
            return out if out is not None else default
        except Exception:
            return default
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return default


# ---- Media gate (port tu threads_post_one.py:171-225) ----
def probe_video(path: Path) -> dict:
    """Read-only ffprobe: duration/container/size. {} khi khong co ffprobe."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration,size", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30)
        data = json.loads(out.stdout or "{}").get("format", {})
        return {"duration_s": float(data.get("duration") or 0),
                "bytes": int(data.get("size") or 0)}
    except Exception:
        return {}


def check_video(path: Path) -> list:
    """Pre-upload gate: reject corrupt/oversize/overlong truoc Post."""
    problems = []
    try:
        size = Path(path).stat().st_size
    except OSError:
        return ["khong doc duoc file"]
    if size <= 0:
        problems.append("file rong")
    if size > THREADS_VIDEO_MAX_MB * 1024 * 1024:
        problems.append(f"qua {THREADS_VIDEO_MAX_MB}MB ({size / 1048576:.1f}MB)")
    info = probe_video(Path(path))
    if info.get("duration_s", 0) > THREADS_VIDEO_MAX_S:
        problems.append(f"dai qua {THREADS_VIDEO_MAX_S}s ({info['duration_s']:.0f}s)")
    if not info and size > 0:
        with open(path, "rb") as f:
            head = f.read(12)
        if len(head) < 12:
            problems.append("file khong doc duoc header")
    return problems


def media_for(item: dict) -> Path | None:
    """Optional single media attach (image/video). Port tu legacy :171-185."""
    path = item.get("media_path") or item.get("local_path")
    if not path:
        return None
    p = Path(str(path))
    if not p.exists():
        return None
    if p.suffix.lower() not in (".mp4", ".mov", ".jpg", ".jpeg", ".png", ".webp"):
        return None
    if p.suffix.lower() in (".mp4", ".mov"):
        problems = check_video(p)
        if problems:
            raise ValueError(f"Video khong dat ({p.name}): {'; '.join(problems)}")
    return p


def _media_gate(intent: "Intent") -> None:
    """Media gate that opens the real media path (M2 fix #3).

    - No media (no sha256, no path) → pass (text-only).
    - media_path/local_path points to a real file → run media_for +
      check_video; pass → allowed through (browser attaches bytes at
      submit); fail → ValueError(before_submit) → FAILED_BEFORE_POST.
    - sha256 set but no resolvable file → still blocked (bytes cannot be
      verified): ValueError(before_submit) with MEDIA_UNVERIFIED.
    """
    has_claim = bool(intent.media_sha256 or intent.media_path)
    if not has_claim:
        return
    item = {"media_path": intent.media_path, "local_path": intent.media_path}
    try:
        resolved = media_for(item)
    except ValueError as exc:
        err = ValueError(f"MEDIA_GATE_REJECTED: {exc}")
        err.before_submit = True  # type: ignore[attr-defined]
        raise err from None
    if resolved is not None:
        return
    err = ValueError(
        "MEDIA_UNVERIFIED: media claimed but no readable file to gate; "
        "refusing to post.")
    err.before_submit = True  # type: ignore[attr-defined]
    raise err


def enforce_adapter_integrity(baseline: Path | None = None) -> None:
    """Fail-closed guard (port _enforce_adapter_integrity :93-105).

    Neu file baseline ton tai (mac dinh tim adapter_baseline.json canh base
    hoac bien MIRO_ADAPTER_BASELINE) thi tu choi moi side-effect truoc khi
    post — caller phai xoa/sua baseline sau khi xac minh chu y. Khong co file
    thi no-op (moi truong Miro khong pack baseline cua dubtool).
    """
    cand = None
    if baseline is not None:
        cand = Path(baseline)
    else:
        env = os.environ.get("MIRO_ADAPTER_BASELINE", "")
        if env:
            cand = Path(env)
    if cand is not None and cand.exists():
        raise RuntimeError(f"INTEGRITY_DRIFT: baseline {cand} present; refusing to post.")


def _actor_relaxation_enabled() -> bool:
    """Chi test/fake: MIRO_ALLOW_UNVERIFIED_ACTOR=1 bo qua contract actor.

    Production KHONG dat bien nay: mac dinh fail-closed, thieu verify ro
    rang la tu choi truoc moi side-effect.
    """
    return os.environ.get("MIRO_ALLOW_UNVERIFIED_ACTOR") == "1"


def verify_actor_contract(browser, intent: "Intent") -> None:
    """Contract: browser inject phai verify actor @username truoc Post.

    Fail-closed mac dinh (production): chi cho post khi co ket qua xac minh
    RO RANG:
    - browser.verify_actor(owner) callable -> phai tra ve dung True; False /
      None / UNKNOWN / bat ky gia tri nao khac -> tu choi (before_submit).
    - neu khong co verify_actor: browser phai khai bao declared_actor da
      verify; mismatch -> tu choi (before_submit).
    - khong co gi ca -> tu choi (before_submit), tru khi
      MIRO_ALLOW_UNVERIFIED_ACTOR=1 (chi test/fake, khong dung production).
    """
    expected = _normalize_account(intent.owner).lower()
    if not expected:
        err = RuntimeError("Thieu tai khoan Threads dich.")
        err.before_submit = True  # type: ignore[attr-defined]
        raise err
    verify = getattr(browser, "verify_actor", None)
    if callable(verify):
        ok = verify(intent.owner)
        if ok is True:
            return
        err = RuntimeError("ACTOR_UNVERIFIED: browser chua xac minh actor ro rang.")
        err.before_submit = True  # type: ignore[attr-defined]
        raise err
    declared = getattr(browser, "declared_actor", None)
    if declared is not None:
        if _normalize_account(declared).lower() != expected:
            err = RuntimeError("ACTOR_MISMATCH: browser actor khac intent owner.")
            err.before_submit = True  # type: ignore[attr-defined]
            raise err
        return
    if _actor_relaxation_enabled():
        return
    err = RuntimeError("ACTOR_UNVERIFIED: browser chua verify actor.")
    err.before_submit = True  # type: ignore[attr-defined]
    raise err


@dataclass
class Intent:
    intent_id: str
    owner: str
    text: str
    tag: str = ""
    media_sha256: str = ""
    shortcode: str = ""
    media_path: str = ""

    @classmethod
    def from_item(cls, item: dict, account: str) -> "Intent":
        text = caption_for(item)
        # S4: thong nhat alphabet tag 6-so voi mat (TAG_RE #dub\d{6}(?!\d)).
        # Tag ngan/dai hon (vd #dub001, #dub1234567) -> tag rong de mat nao
        # miss ro rang (UNKNOWN) thay vi miss cam; caller can ly do doc caption.
        found = re.search(r"#dub\d{6}(?!\d)", text.lower())
        return cls(
            intent_id=job_id_for(item),
            owner=_normalize_account(account),
            text=text,
            tag=(found.group(0).lower() if found else ""),
            media_sha256=str(item.get("sha256") or ""),
            shortcode=str(item.get("shortcode")),
            media_path=str(item.get("media_path") or item.get("local_path") or ""),
        )


def journal_path_for(attempts_dir: Path, intent: Intent) -> Path:
    return Path(attempts_dir) / f"{intent.intent_id}.json"


def guard_duplicate(base: Path, shortcode: str, journal_name: str,
                    attempts_dir: Path) -> dict | None:
    """Shared pre-side-effect guard (same as legacy :228). Skip dict or None."""
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


def _norm_tag_exact(text) -> str:
    if _legacy["eye_norm"] is not None:
        try:
            return _legacy["eye_norm"](text)
        except Exception:
            pass
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


# P0 mat (A rea_eye.py + dap HOI-eye-01): chi 2 pattern locator, giu hep.
_EYE_LINK_SELECTOR = 'a[href*="/@{user}/post/"], a[href*="/@{user}/t/"]'
# Fix B3 (A TAG_RE khong boundary hit 6 so dau cua tag dai): chan bang (?!\d).
TAG_RE = re.compile(r"#dub\d{6}(?!\d)")


def extract_eye_tag(text: str) -> str:
    """Tag eye: #dub dung 6 so (A :18 + fix B3 boundary). Khong co -> ''."""
    hit = TAG_RE.search(str(text or "").lower())
    return hit.group(0) if hit else ""


def _strip_post_id(href: str) -> str:
    """Fix B2: post_id = segment cuoi, cat query/fragment."""
    seg = (href or "").strip().split("?")[0].split("#")[0].strip("/").split("/")[-1]
    return seg.strip()


async def collect_post_records(page, username: str, limit: int = 40,
                             diag: dict | None = None) -> list[dict]:
    """Mat that trong C (port rea_eye.collect_post_records :56-89 + fix B1-B8).

    - Locator hep 2 pattern theo A (khong mo rong mu).
    - has_video chi trong article (fix B1: khong fallback document).
    - post_id cat query/fragment (fix B2); TAG boundary 6 so (fix B3).
    - Dedup theo post_id/url, limit theo record unique (fix B6).
    - text preview giu tag (fix B7); dem loi thay vi nuot cam (fix B5).
    - B4: dem link/article/hit/miss vao `diag` (truyen dict vao de nhan;
      khong tron record diagnostic vao ket qua de giu contract cu).
    - B8: doc author live tu DOM (link href/@username quan sat duoc); caller
      van acquire/verify truoc, nao tu choi khi author lech tab (verified o
      match_eye_records, khong tin author tu khai o day).
    """
    from contextlib import suppress

    user = str(username or "").lstrip("@")
    records: list[dict] = []
    scan: dict = {"links": 0, "articles": 0, "skipped_no_article": 0,
                  "skipped_no_pid": 0, "dupes": 0, "errors": 0}
    links: list = []
    with suppress(Exception):
        links = await page.locator(
            f'a[href*="/@{user}/post/"], a[href*="/@{user}/t/"]').all()
    scan["links"] = len(links or [])
    with suppress(Exception):
        scan["articles"] = await page.locator("article").count()
    seen: set[str] = set()
    for link in (links or [])[: max(1, int(limit)) * 3]:
        if len(records) >= max(1, int(limit)):
            break
        try:
            href = await link.get_attribute("href")
            if not href:
                continue
            parent_text = await link.evaluate(
                "el => (el.closest('article') || el.parentElement).innerText || ''")
            in_article = await link.evaluate(
                "el => !!el.closest('article')")
            if not in_article:
                scan["skipped_no_article"] += 1
            norm = _norm_tag_exact(parent_text)
            # Fix B1: chi query video trong article, khong lan sang document.
            has_video = await link.evaluate(
                "el => { const a = el.closest('article');"
                " return a ? !!a.querySelector('video') : false; }")
            url = href if href.startswith("http") else f"https://www.threads.com{href}"
            pid = _strip_post_id(href)
            if not pid:
                scan["skipped_no_pid"] += 1
                continue
            if not url:
                continue
            # B8: author live tu href quan sat duoc, khong tin username truyen vao.
            live_author = _author_of_href(href) or f"@{user}"
            key = pid or url
            if key in seen:
                scan["dupes"] += 1
                continue
            seen.add(key)
            # Fix B7: preview giu tag (dau + duoi) thay vi cat cung 300 ky tu.
            preview = norm[:300] if extract_eye_tag(norm) in norm[:300] else (
                norm[:240] + " … " + norm[-60:] if len(norm) > 300 else norm)
            records.append({
                "author": live_author,
                "tag": extract_eye_tag(norm),
                "url": url,
                "post_id": pid,
                "has_video": bool(has_video),
                "text": preview,
            })
        except Exception:
            scan["errors"] += 1
            continue
    if isinstance(diag, dict):
        diag.update(scan)
    return [r for r in records if "post_id" in r and "url" in r]


def _author_of_href(href: str) -> str:
    """B8: trich @username tu href quan sat duoc (/...@user/post/...)."""
    import re

    hit = re.search(r"/@([A-Za-z0-9._-]+)/", str(href or ""))
    return f"@{hit.group(1)}" if hit else ""


def match_eye_records(records: list[dict], owner: str, want_tag: str,
                      want_text: str = "", known_ids: list[str] | None = None
                      ) -> dict | None:
    """Same-record exact semantics cua core/rea_eye.match_eye_records.

    - S1: record-major nhu A (voi moi record: post_id truoc roi tag, skip sc
      da receipts). Loc author truoc la that chat co loi (thong nhat o day
      cho ca 2 path). Path delegate goi ham goc; path fallback duoi day cung
      record-major de da pending cung ket qua.
    - known post_id (tu journal ack_post_codes) truoc, trong CUNG record.
    - roi exact tag equality sau normalize, trong CUNG record.
    - S5: KHONG substring/prefix, KHONG text fallback (rea_eye khong co).
      `want_text` giu cho de khong vo caller (4 cho truyen intent.text),
      CO Y KHONG DUNG — khong fallback text du co truyen.
    Uy thac cho eye goc khi import duoc (pending {sc:{tag,post_ids}}).
    """
    known_ids = [str(x).strip() for x in (known_ids or []) if str(x).strip()]
    want_tag_n = _norm_tag_exact(want_tag)
    owner_l = owner.lower().lstrip("@")
    if _legacy["eye_match"] is not None:
        try:
            pending = {"_want": {"tag": want_tag or "",
                                 "post_ids": list(known_ids)}}
            norm_recs = [r for r in records or []
                         if str(r.get("author") or "").lower().lstrip("@") == owner_l]
            receipts, _ = _legacy["eye_match"](pending, norm_recs)
            rec = receipts.get("_want")
            if rec and rec.get("url"):
                via = "post_id" if (known_ids and str(rec.get("post_id") or "").strip() in set(known_ids)) else "tag"
                return {"url": rec["url"], "post_id": str(rec.get("post_id") or ""),
                        "has_video": bool(rec.get("has_video")), "match": f"eye-{via}"}
        except Exception:
            pass
    # S1 fallback record-major (giong A: record -> post_id truoc roi tag).
    for r in records or []:
        if str(r.get("author") or "").lower().lstrip("@") != owner_l:
            continue
        if not r.get("url"):
            continue
        pid = str(r.get("post_id") or "").strip()
        if pid and pid in (known_ids or []):
            return {"url": r["url"], "post_id": pid,
                    "has_video": bool(r.get("has_video")), "match": "eye-post_id"}
        rtag = _norm_tag_exact(r.get("tag") or "")
        if want_tag_n and rtag == want_tag_n:
            return {"url": r["url"], "post_id": str(r.get("post_id") or ""),
                    "has_video": bool(r.get("has_video")), "match": "eye-tag"}
    return None


def verify_receipt(receipt: dict | None, intent: Intent,
                   known_ids: list[str] | None = None) -> dict | None:
    """Receipt verified chi khi owner + same-record exact (post_id | tag).

    - owner phai khop (case-insensitive).
    - post_id: chap nhan khi nam trong known_ids (uu tien, tu journal
      ack_post_codes) hoac post_id xuat hien trong url CUNG receipt.
    - tag: exact equality sau normalize giua receipt.tag va intent.tag.
      KHONG substring trong url/JSON dump.
    - KHONG text fallback.
    """
    if not isinstance(receipt, dict):
        return None
    # Fix S3: eye record dung key "author", khong phai "owner" — chap nhan ca hai.
    _owner_raw = receipt.get("owner") or receipt.get("author")
    if _normalize_account(_owner_raw).lower() != intent.owner.lower().lstrip("@") \
            and str(_owner_raw or "").lower().lstrip("@") != intent.owner.lower().lstrip("@"):
        return None
    url = str(receipt.get("url") or "").strip()
    if not url:
        return None
    kids = [str(x).strip() for x in (known_ids or []) if str(x).strip()]
    post_id = str(receipt.get("post_id") or "").strip()
    if post_id and kids and post_id in kids:
        return {"shortcode": intent.shortcode or intent.intent_id, "status": "published",
                "url": url, "post_id": post_id, "match": "post_id"}
    # Fix S2: bo passthrough receipt tu khai match=post_id; post_id trong url
    # chi chap nhan khi tag exact hoac post_id nam trong known_ids.
    if post_id and post_id in url:
        rtag = _norm_tag_exact(receipt.get("tag") or "")
        itag = _norm_tag_exact(intent.tag or "")
        if (itag and rtag == itag) or (kids and post_id in kids):
            return {"shortcode": intent.shortcode or intent.intent_id, "status": "published",
                    "url": url, "post_id": post_id, "match": "post_id"}
    rtag = _norm_tag_exact(receipt.get("tag") or "")
    itag = _norm_tag_exact(intent.tag or "")
    if itag and rtag == itag:
        return {"shortcode": intent.shortcode or intent.intent_id, "status": "published",
                "url": url, "post_id": post_id or None, "match": "tag"}
    return None


class Publisher:
    """Faithful Threads-model publisher. Browser injected (mock in tests)."""

    def __init__(self, base: str | Path, attempts_dir: str | Path | None = None,
                 integrity_baseline: str | Path | None = None,
                 require_approval: bool = False):
        self.base = Path(base)
        self.attempts = Path(attempts_dir) if attempts_dir else self.base / "social-attempts"
        self.attempts.mkdir(parents=True, exist_ok=True)
        self.integrity_baseline = Path(integrity_baseline) if integrity_baseline else None
        # M2 (JARVIS §10.5): True bat gate approval tai bien publish
        # (SAU guard_duplicate + verify actor, TRUOC post_once).
        self.require_approval = require_approval

    def _pre_post_checks(self, intent: Intent, browser, approval=None,
                           revision: int = 0) -> None:
        enforce_adapter_integrity(self.integrity_baseline)
        _media_gate(intent)
        verify_actor_contract(browser, intent)
        if self.require_approval:
            from miro.threads.flow import check_approval as _check_approval
            try:
                _check_approval(approval, intent, revision)
            except Exception as exc:
                code = getattr(exc, "code", type(exc).__name__)
                err = RuntimeError(f"{code}: {exc}")
                err.before_submit = True  # type: ignore[attr-defined]
                raise err from None

    def publish(self, intent: Intent, browser, approval=None,
                revision: int = 0) -> dict:
        """Single submit mirroring _post_live_chrome_on_page :670-700.

        Journal "submit" duoc giu khi loi sau click roi RE-RAISE de caller
        (run_batch) quyet dinh ghi unknown + dung submit. Chi tu ghi
        failed-before-post (before_submit) hoac unknown khi khong co receipt
        (khong exception). Disconnect luon re-raise.
        """
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
            self._pre_post_checks(intent, browser, approval=approval, revision=revision)
        except Exception as exc:
            if getattr(exc, "before_submit", False):
                atomic_save(journal_path, {"shortcode": intent.shortcode or intent.intent_id,
                                           "account": intent.owner,
                                           "status": FAILED_BEFORE_POST,
                                           "at": record["at"], "cause": type(exc).__name__})
                return {"error": "FAILED_BEFORE_POST",
                        "shortcode": intent.shortcode or intent.intent_id,
                        "cause": type(exc).__name__}
            raise
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
            raise  # loi sau click: journal giu "submit", caller ghi unknown
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
        if journal.get("status") in (VERIFIED, "published"):
            return {"reconciled": True, "shortcode": intent.shortcode or intent.intent_id,
                    "already": "verified"}
        known_ids = [str(x) for x in (journal.get("ack_post_codes") or []) if str(x).strip()]
        receipt = browser.read_receipt(intent)
        if isinstance(receipt, list):
            hit = match_eye_records(receipt, intent.owner, intent.tag, intent.text, known_ids)
            if hit:
                verified = {"shortcode": intent.shortcode or intent.intent_id,
                            "status": "published", "url": hit["url"],
                            "post_id": hit.get("post_id"), "match": hit.get("match")}
            else:
                verified = None
        else:
            verified = verify_receipt(receipt, intent, known_ids)
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
        """Two-phase batch dung legacy run_batch :744-901.

        Phase A: submit tung intent tren ack, journal
        submitted-awaiting-group-reconcile + milestones/timeline, CHUA merge
        publication, CHUA mark published. Dung submit ngay khi gap ambiguous
        (UNKNOWN sau click) hoac disconnect; loi before_submit/generic thi ghi
        error va TIEP TUC item sau (khop _run_batch_legacy :937-941).
        Phase B: group reconcile 1 lan (read-only), map post_id/tag sang URL,
        chi luc nay moi merge publication + journal verified + timeline
        (post_clicked/posting_seen/ack_seen/profile_match_seen, ack_to_match_s).
        Abort ca batch voi DUPLICATE_TAGS khi 2 item cung #dub (:779-786).
        """
        results: list[dict] = []
        # --- scheduler gate (P1 caller): paused/due truoc khi cham intent ---
        plan = getattr(self, "day_plan", None)
        if isinstance(plan, dict):
            from miro.scheduling.schedule import select_due_intents as _select_due
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            _now = _dt.now(_tz(_td(hours=7))).isoformat()
            _due, _deferred = _select_due(plan, intents, _now)
            _deferred_ids = {id(d["intent"]) for d in _deferred}
            for d in _deferred:
                results.append({"posted": False,
                                "receipt": "DEFERRED_TO_GROUP_RECONCILE",
                                "shortcode": d["shortcode"],
                                "defer_reason": d["reason"]})
            intents = [i for i in intents if id(i) not in _deferred_ids]
            if not intents:
                return results
        # --- prep + duplicate-tag guard (legacy :762-786) ---
        prepped: list[dict] = []
        for intent in intents:
            skip = guard_duplicate(self.base, intent.shortcode or intent.intent_id,
                                   f"{intent.intent_id}.json", self.attempts)
            if skip:
                results.append(skip)
                continue
            try:
                _media_gate(intent)
            except Exception as exc:
                results.append({"error": type(exc).__name__,
                                "shortcode": intent.shortcode or intent.intent_id})
                continue
            prepped.append({"intent": intent, "shortcode": intent.shortcode or intent.intent_id,
                            "tag": (intent.tag or "").lower()})
        tag_counts: dict[str, int] = {}
        for p in prepped:
            if p["tag"]:
                tag_counts[p["tag"]] = tag_counts.get(p["tag"], 0) + 1
        dupes = sorted(t for t, c in tag_counts.items() if c > 1)
        if dupes:
            return [{"batch": str(self.base), "error": "DUPLICATE_TAGS", "tags": dupes,
                     "hint": "tag #dub trung nhau; giu trang thai chua xac minh, khong dang"}]
        # --- Phase A: submit tren ack ---
        submitted: list[dict] = []
        ambiguous: list[str] = []
        stopped = False
        batch_started = time.time()
        for p in prepped:
            intent = p["intent"]
            sc = p["shortcode"]
            if stopped:
                # P0 fix (A run_batch :840-856 break): item chua attempt thi KHONG
                # journal — de batch sau guard_duplicate cho post lai binh thuong.
                # Chi journal submit/unknown SAU click; deferred tra ve ro rang.
                results.append({"posted": False, "receipt": "DEFERRED_TO_GROUP_RECONCILE",
                                "shortcode": sc})
                continue
            journal_path = journal_path_for(self.attempts, intent)
            started_at = time.time()
            atomic_save(journal_path, {
                "shortcode": sc, "account": intent.owner, "status": CLAIMED,
                "at": started_at,
                "text_sha256": hashlib.sha256(intent.text.encode("utf-8")).hexdigest()})
            try:
                self._pre_post_checks(intent, browser)
                ack = browser.post_once(intent)
            except Exception as exc:
                if _is_disconnect(exc):
                    atomic_save(journal_path, {
                        "shortcode": sc, "account": intent.owner, "status": UNKNOWN,
                        "at": started_at, "hint": "UNCONFIRMED_NO_REPLAY",
                        "cause": type(exc).__name__})
                    ambiguous.append(sc)
                    results.append({"shortcode": sc, "receipt": "UNKNOWN",
                                    "hint": "disconnect; reconcile read-only, never replay"})
                    stopped = True
                    continue
                if getattr(exc, "before_submit", False):
                    atomic_save(journal_path, {
                        "shortcode": sc, "account": intent.owner,
                        "status": FAILED_BEFORE_POST, "at": started_at,
                        "cause": type(exc).__name__})
                    results.append({"error": "FAILED_BEFORE_POST", "shortcode": sc,
                                    "cause": type(exc).__name__})
                    continue  # loi truoc click: tiep tuc item sau
                atomic_save(journal_path, {
                    "shortcode": sc, "account": intent.owner, "status": UNKNOWN,
                    "at": started_at, "hint": "UNCONFIRMED_NO_REPLAY",
                    "cause": type(exc).__name__})
                ambiguous.append(sc)
                results.append({"shortcode": sc, "receipt": "UNKNOWN",
                                "hint": f"{type(exc).__name__}; stopped submitting, group reconcile only"})
                stopped = True
                continue
            tl = {"post_clicked": started_at,
                  "posting_seen": None,
                  "ack_seen": time.time(),
                  "ready_next": time.time()}
            codes: list[str] = []
            ack_url = None
            if isinstance(ack, dict):
                raw_codes = ack.get("ack_post_codes") or []
                codes = [str(x) for x in raw_codes if str(x).strip()]
                if not codes and ack.get("post_id"):
                    codes = [str(ack.get("post_id"))]
                ack_url = ack.get("ack_response_url")
            atomic_save(journal_path, {
                "shortcode": sc, "account": intent.owner,
                "status": AWAITING_GROUP, "at": started_at,
                **{f"milestone_{k}": v for k, v in tl.items()},
                "ack_via": (ack.get("ack_via") if isinstance(ack, dict) else None),
                "ack_response_url": ack_url,
                "ack_post_codes": codes,
                "observed_toasts": (ack.get("observed_toasts") or [] if isinstance(ack, dict) else []),
                "observed_responses": (ack.get("observed_responses") or [] if isinstance(ack, dict) else []),
                "text_sha256": hashlib.sha256(intent.text.encode("utf-8")).hexdigest()})
            submitted.append({"intent": intent, "shortcode": sc, "timeline": tl,
                              "post_ids": codes})
        # --- Phase B: group reconcile 1 lan, read-only ---
        group_receipts: dict[str, dict] = {}
        if submitted:
            group_fn = getattr(browser, "read_group_receipts", None)
            if callable(group_fn):
                try:
                    grp = group_fn([p["intent"] for p in submitted]) or {}
                    if isinstance(grp, dict):
                        group_receipts = grp
                except Exception:
                    group_receipts = {}
            for p in submitted:
                sc = p["shortcode"]
                if sc in group_receipts:
                    continue
                try:
                    one = browser.read_receipt(p["intent"])
                except Exception:
                    one = None
                if isinstance(one, list):
                    hit = match_eye_records(one, p["intent"].owner, p["intent"].tag,
                                            p["intent"].text, p["post_ids"])
                    if hit:
                        group_receipts[sc] = {"owner": p["intent"].owner, "url": hit["url"],
                                             "post_id": hit.get("post_id"),
                                             "match": hit.get("match")}
                elif isinstance(one, dict) and one.get("url"):
                    group_receipts[sc] = one
            for p in submitted:
                sc = p["shortcode"]
                journal_path = journal_path_for(self.attempts, p["intent"])
                journal = load_json_if_exists(journal_path, {})
                rec = group_receipts.get(sc)
                verified = verify_receipt(rec, p["intent"], p["post_ids"]) if rec else None
                plan = getattr(self, "day_plan", None)
                if verified:
                    match_seen = time.time()
                    entry = {"shortcode": sc, "status": "published",
                             "url": verified["url"], "post_id": verified.get("post_id"),
                             "text_sha256": hashlib.sha256(p["intent"].text.encode("utf-8")).hexdigest(),
                             "timeline": {**p["timeline"], "profile_match_seen": match_seen}}
                    atomic_save(journal_path, {
                        "shortcode": sc, "account": p["intent"].owner, "status": VERIFIED,
                        "at": p["timeline"].get("post_clicked", batch_started),
                        **{k: v for k, v in entry.items() if k != "timeline"},
                        "timeline": entry["timeline"],
                        "ack_post_codes": p["post_ids"],
                        "ack_via": journal.get("ack_via"),
                        "ack_response_url": journal.get("ack_response_url")})
                    _merge_publication(self.base, {k: v for k, v in entry.items()
                                                   if k != "timeline"}, p["intent"].owner)
                    if isinstance(plan, dict):
                        from miro.scheduling.schedule import mark_slot_verified as _verified
                        _verified(plan, p["intent"].intent_id)
                    ack_seen = p["timeline"].get("ack_seen") or batch_started
                    results.append({"posted": True,
                                    **{k: v for k, v in entry.items() if k != "timeline"},
                                    "timeline": entry["timeline"],
                                    "ack_to_match_s": round(match_seen - ack_seen, 1)})
                else:
                    atomic_save(journal_path, {
                        "shortcode": sc, "account": p["intent"].owner, "status": UNKNOWN,
                        "at": p["timeline"].get("post_clicked", batch_started),
                        "hint": "UNCONFIRMED_NO_REPLAY",
                        "ack_post_codes": p["post_ids"]})
                    if isinstance(plan, dict):
                        from miro.scheduling.schedule import record_submit_unknown as _unknown
                        _unknown(plan, p["intent"].intent_id)
                    results.append({"posted": True, "receipt": "UNCONFIRMED_NO_REPLAY",
                                    "shortcode": sc})
        return results
