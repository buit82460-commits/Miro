"""Local rule engine — runs without LLM or GPU.

Port of core/editor.py::_local_plan so handlers work when LLM is off.
"""
from __future__ import annotations

import copy
import re

NOTES_LOCAL = "Quy tac local"


def clock(text: str) -> float:
    parts = text.replace(",", ".").split(":")
    return sum(float(v) * 60 ** i for i, v in enumerate(reversed(parts)))


def empty_plan(source_id: str, duration: float) -> dict:
    return {
        "version": 1, "source_id": source_id, "duration": duration,
        "cuts": [], "zooms": [], "texts": [], "sfx": [], "music": [],
        "fades": {"in": 0, "out": 0}, "burn_subtitles": False, "notes": [],
    }


def duration_after(keep_ranges: list) -> float:
    return round(sum(b - a for a, b in keep_ranges), 3)


def keep_ranges(plan: dict) -> list:
    duration = float(plan.get("duration", 0))
    cuts = sorted(
        (float(c["start"]), float(c["end"])) for c in plan.get("cuts", [])
    )
    ranges, cursor = [], 0.0
    for start, end in cuts:
        start, end = max(0, start), min(duration, end)
        if end > max(cursor, start):
            if start > cursor:
                ranges.append((cursor, start))
            cursor = max(cursor, end)
    if cursor < duration:
        ranges.append((cursor, duration))
    return ranges


def local_plan(plan: dict, request: str, segments: list | None = None,
               silences: list | None = None) -> tuple[dict, str]:
    """Rule-based planner. Raises ValueError when the request is unsupported."""
    plan = copy.deepcopy(plan)
    lower = request.lower()
    notes: list[str] = []
    matched = False
    segments = segments or []
    silences = silences or []

    duration = float(plan.get("duration", 0))
    if any(t in lower for t in ("khoang lang", "im lang", "silence")) \
            and not re.search(r"(?:khong|dung)\s+(?:bo|cat)", lower):
        for start, end in silences:
            plan["cuts"].append({"start": start, "end": end})
        matched = True
        notes.append("Bo phan giua khoang lang; giu padding.")

    time = r"(\d+(?::\d{1,2}){0,2}(?:[.,]\d+)?)"
    for m in re.finditer(
            r"cat(?:\s+doan)?(?:\s+tu)?\s+" + time + r"\s*(?:giay\s*)?(?:den|toi|-)\s*" + time, lower):
        plan["cuts"].append({"start": clock(m[1]), "end": clock(m[2])})
        matched = True

    if "zoom" in lower:
        matched = True
        if re.search(r"(?:bo|tat|khong)\s+zoom", lower):
            plan["zooms"] = []
        else:
            cands = (segments or [{"start": 0, "end": min(2.5, duration)}])[:3]
            plan["zooms"] = [
                {"start": s["start"], "end": min(duration, s["end"], s["start"] + 3),
                 "factor": 1.12, "x": 0.5, "y": 0.5} for s in cands
            ]
            notes.append("Zoom nhe tai cac cau ung vien.")

    if "chu" in lower or "text" in lower:
        matched = True
        if re.search(r"(?:bo|tat)\s+(?:chu|text)", lower):
            plan["texts"] = []
        else:
            quoted = re.findall(r'["\u201c]([^"\u201d]+)["\u201d]', request)
            cands = (segments or [{"start": 0, "end": min(2.5, duration),
                                   "tgt_text": "Diem nhan"}])[:3]
            color = "red" if "do" in lower else "white" if "trang" in lower else "yellow"
            plan["texts"] = [
                {"start": s["start"], "end": min(duration, s["end"], s["start"] + 3),
                 "text": (quoted[min(i, len(quoted) - 1)] if quoted
                          else (s.get("tgt_text") or s.get("src_text") or "Diem nhan")[:70]),
                 "color": color, "size": 0.065, "x": 0.5, "y": 0.8}
                for i, s in enumerate(cands)
            ]

    if "phu de" in lower or "subtitle" in lower:
        plan["burn_subtitles"] = not bool(re.search(r"(?:bo|tat)\s+phu de", lower))
        matched = True

    if "fade" in lower:
        plan["fades"] = {"in": 0.2, "out": 0.2}
        matched = True

    if any(w in lower for w in ("sfx", "tieng pop", "tieng ding", "whoosh")):
        matched = True
        if re.search(r"(?:bo|tat)\s+(?:sfx|tieng pop|tieng ding|whoosh)", lower):
            plan["sfx"] = []
        else:
            asset = "ding" if "ding" in lower else "whoosh" if "whoosh" in lower else "pop"
            events = plan["texts"] or segments[:3] or [{"start": 0}]
            plan["sfx"] = [{"at": s["start"], "asset": asset, "gain_db": -18}
                           for s in events if s["start"] < duration - 1 / 30]

    if "nhac" in lower or "music" in lower:
        matched = True
        if re.search(r"(?:bo|tat)\s+(?:nhac|music)", lower):
            plan["music"] = []
        else:
            plan["music"] = [{"start": 0, "end": duration, "asset": "user-music",
                              "gain_db": -25}]
            notes.append("Nhac nen o muc -25 dB; thay asset user-music bang ID thu vien.")

    if not matched:
        raise ValueError(
            "Lenh local chua ho tro yeu cau nay. Bat AI voi cau hinh LLM, "
            "hoac dung lenh: cat tu 2 den 4 giay, bo khoang lang, zoom, "
            "them chu, tieng pop/ding/whoosh, fade."
        )
    plan["notes"] = notes
    return plan, NOTES_LOCAL
