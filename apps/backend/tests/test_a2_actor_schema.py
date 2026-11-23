"""A2 proposal: tiktok_actor_record eye collector (TikTok actor schema).

Ownership: eye/ + TikTok actor schema. KHONG sua gateway.py security.
File nay la PROPOSAL + TEST doc lap — khong sua eye/__init__.py tren main.
Neu duyet, copy ham pure `evaluate_actor_signals` + `tiktok_actor_record`
(native Page) vao apps/backend/src/miro/eye/__init__.py tren branch rieng.

Schema (structured DOM observation, dung chung native Page + Bridge):
    TikTokActorObservation = {
        "title": str,              # chi context, KHONG la bang chung
        "url": str,                # chi context, KHONG la bang chung
        "has_login_button": str,   # "" = khong con nut Log in; "1" = con
        "profile_href": str,       # "/@handle..." link profile that
        "has_upload_link": str,    # "1" = co loi Upload (chi hien khi login)
    }

Quy tac:
- KHONG tin title hoac profile_href don le — yeu cau DU 3 tin hieu
  tren CUNG 1 DOM observation.
- Hai quan sat cung Extension KHONG phai hai nguon doc lap — chi la
  consistency check (chong DOM rac nhat thoi, khong nang cap muc tin cay).
- ACTOR_CLAIMED = observation dat 3 tin hieu (ung vien handle).
  VERIFIED = chi Gateway gan sau khi doi chieu kenh doc lap
  (REA/Eye tren page that). Bridge observation mot minh KHONG bao gio VERIFIED.
"""


def evaluate_actor_signals(data):
    """Pure evaluator dung chung cho native Page + Bridge observation.

    Tra {"ok": True, "actor": "@handle", "status": "ACTOR_CLAIMED"}
    hoac {"ok": False, "error": "ACTOR_UNVERIFIED", "missing": [...]}.
    """
    data = data or {}
    missing = []
    if str(data.get("has_login_button") or "") != "":
        missing.append("has_login_button")
    href = str(data.get("profile_href") or "")
    tail = href[2:].split("/")[0].split("?")[0] if href.startswith("/@") else ""
    import re
    if not href.startswith("/@") or len(href) < 3 or not re.match(
            r"^[\w.\-]{2,24}$", tail or ""):
        missing.append("profile_href")
    if str(data.get("has_upload_link") or "") != "1":
        missing.append("has_upload_link")
    if missing:
        return {"ok": False, "error": "ACTOR_UNVERIFIED",
                "missing": missing, "status": "ACTOR_CLAIMED_FAILED"}
    return {"ok": True, "actor": "@" + tail, "status": "ACTOR_CLAIMED"}


def check_consistency(obs1, obs2):
    """Hai quan sat cung Extension: chi consistency check, khong doc lap.

    Tra {"ok": True, "actor"} neu cung verdict + cung handle,
    nguoc lai {"ok": False, "error": "ACTOR_INCONSISTENT"}.
    """
    r1, r2 = evaluate_actor_signals((obs1 or {}).get("data", obs1)), \
        evaluate_actor_signals((obs2 or {}).get("data", obs2))
    if bool(r1.get("ok")) != bool(r2.get("ok")):
        return {"ok": False, "error": "ACTOR_INCONSISTENT"}
    if r1.get("ok") and r1.get("actor") != r2.get("actor"):
        return {"ok": False, "error": "ACTOR_INCONSISTENT"}
    return {"ok": r1.get("ok", False), "actor": r1.get("actor"),
            "note": "same-extension-consistency-only"}


# ---- Proposal collector cho native Page (copy vao eye/__init__.py khi duyet)
PROPOSAL_NATIVE_COLLECTOR = '''
async def tiktok_actor_record(page) -> dict:
    """Eye actor TikTok (native Page): thu thap TikTokActorObservation
    roi goi evaluate_actor_signals. KHONG tin title/profile_href don le."""
    from contextlib import suppress
    obs = {"title": "", "url": "", "has_login_button": "1",
           "profile_href": "", "has_upload_link": ""}
    with suppress(Exception):
        obs["url"] = str(page.url or "")
    with suppress(Exception):
        obs["title"] = str(await page.title() or "")
    with suppress(Exception):
        loc = page.locator(
            '[data-e2e="top-login-button"], [data-e2e="nav-login-button"]')
        first = getattr(loc, "first", loc)
        obs["has_login_button"] = "" if await first.count() == 0 else "1"
    with suppress(Exception):
        import re
        links = await page.locator('a[href^="/@"]').all()
        for a in links or []:
            with suppress(Exception):
                href = await a.get_attribute("href") or ""
                tail = href[2:].split("/")[0].split("?")[0]
                if href.startswith("/@") and re.match(
                        r"^[\\w.\\-]{2,24}$", tail):
                    obs["profile_href"] = href
                    break
    with suppress(Exception):
        loc = page.locator(
            '[data-e2e="upload-icon"], a[href^="/upload"]')
        first = getattr(loc, "first", loc)
        obs["has_upload_link"] = "1" if await first.count() > 0 else ""
    res = evaluate_actor_signals(obs)
    res["observation"] = obs
    return res
'''.strip()


def test_happy_path_claimed():
    r = evaluate_actor_signals({
        "title": "TikTok", "url": "https://www.tiktok.com/",
        "has_login_button": "", "profile_href": "/@kemkhongta",
        "has_upload_link": "1"})
    assert r == {"ok": True, "actor": "@kemkhongta",
                 "status": "ACTOR_CLAIMED"}


def test_title_alone_not_trusted():
    r = evaluate_actor_signals({
        "title": "@kemkhongta", "url": "https://www.tiktok.com/@kemkhongta",
        "has_login_button": "1", "profile_href": "", "has_upload_link": ""})
    assert r["ok"] is False and r["error"] == "ACTOR_UNVERIFIED"
    assert "profile_href" in r["missing"]


def test_profile_href_alone_not_trusted():
    r = evaluate_actor_signals({
        "title": "", "url": "",
        "has_login_button": "1", "profile_href": "/@kemkhongta",
        "has_upload_link": ""})
    assert r["ok"] is False
    assert "has_login_button" in r["missing"]
    assert "has_upload_link" in r["missing"]


def test_each_signal_required():
    base = {"title": "t", "url": "u", "has_login_button": "",
            "profile_href": "/@abc", "has_upload_link": "1"}
    bad_values = {"has_login_button": "1", "profile_href": "",
                  "has_upload_link": ""}
    for drop in ("has_login_button", "profile_href", "has_upload_link"):
        bad = dict(base)
        bad[drop] = bad_values[drop]
        r = evaluate_actor_signals(bad)
        assert r["ok"] is False and drop in r["missing"]


def test_bad_href_rejected():
    for href in ("", "@abc", "/@x", "/video/123", "/@a/b?c"):
        r = evaluate_actor_signals({
            "has_login_button": "", "profile_href": href,
            "has_upload_link": "1"})
        assert r["ok"] is False, href


def test_same_extension_is_consistency_only():
    o1 = {"data": {"has_login_button": "", "profile_href": "/@a1b2",
                   "has_upload_link": "1"}}
    o2 = {"data": {"has_login_button": "", "profile_href": "/@a1b2",
                   "has_upload_link": "1"}}
    c = check_consistency(o1, o2)
    assert c["ok"] is True
    assert c["note"] == "same-extension-consistency-only"
    o3 = {"data": {"has_login_button": "", "profile_href": "/@other",
                   "has_upload_link": "1"}}
    assert check_consistency(o1, o3)["error"] == "ACTOR_INCONSISTENT"
