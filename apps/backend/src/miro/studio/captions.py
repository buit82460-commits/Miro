"""Caption helpers ported from dubtool (Phase D).

Nguồn (chỉ đọc, không copy nguyên khối):
- ``C:\\dubtool\\core\\studio_service.py``:186-214 (add_source_captions),
  596-600 (import/export_captions), 621-669 (transcribe_clip words/word_timestamps)
- ``C:\\dubtool\\web\\src\\app\\editor\\page.tsx``:160-200 (UI phụ đề: click cue
  nhảy playhead, clip text có {start, duration, text})
- ``C:\\dubtool\\core\\stt.py``:49-63 (_build_segments: gom text thành segments)

Thuần stdlib, không phụ thuộc ngoài.
"""

from __future__ import annotations

import re

__all__ = [
    "parse_srt",
    "export_srt",
    "cues_from_segments",
    "cues_to_text_track",
    "words_from_whisper",
    "merge_words_to_cues",
    "retime_cues",
]

_TS_RE = re.compile(
    r"(\d{1,2}):(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{1,2}):(\d{1,2})[,.](\d{1,3})"
)


def _to_secs(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def _fmt_ts(secs: float) -> str:
    if secs < 0:
        secs = 0.0
    total_ms = int(round(secs * 1000))
    h, rem = divmod(total_ms, 3600 * 1000)
    m, rem = divmod(rem, 60 * 1000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(text: str) -> list[dict]:
    """Parse SRT chuẩn thành [{id, start, end, text}]; lỗi format -> ValueError."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("SRT rỗng: cần nội dung SRT hợp lệ.")
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    cues: list[dict] = []
    for i, block in enumerate(blocks, 1):
        lines = [ln for ln in block.strip().splitlines() if ln.strip() != ""]
        if not lines:
            continue
        if len(lines) < 2:
            raise ValueError(f"SRT block {i}: thiếu dòng thời gian.")
        head, rest = lines[0], lines[1:]
        if "-->" in head:
            cue_no, stamp, body = i, head, rest
        else:
            if not head.strip().isdigit():
                raise ValueError(f"SRT block {i}: dòng đầu phải là số thứ tự hoặc mốc thời gian.")
            if len(rest) < 1:
                raise ValueError(f"SRT block {i}: thiếu dòng thời gian.")
            cue_no, stamp, body = int(head.strip()), rest[0], rest[1:]
        m = _TS_RE.fullmatch(stamp.strip())
        if not m:
            raise ValueError(f"SRT block {i}: mốc thời gian sai format (cần HH:MM:SS,mmm --> ...).")
        start = _to_secs(*m.groups()[:4])
        end = _to_secs(*m.groups()[4:])
        if end <= start:
            raise ValueError(f"SRT block {i}: end ({end}) phải lớn hơn start ({start}).")
        content = "\n".join(ln.rstrip() for ln in body).strip()
        if not content:
            raise ValueError(f"SRT block {i}: thiếu nội dung phụ đề.")
        cues.append({"id": cue_no, "start": start, "end": end, "text": content})
    if not cues:
        raise ValueError("SRT không chứa cue hợp lệ nào.")
    return cues


def export_srt(cues: list) -> str:
    """Xuất cues [{id?, start, end, text}] thành SRT chuẩn."""
    if not cues:
        return ""
    out: list[str] = []
    for i, cue in enumerate(cues, 1):
        try:
            start = float(cue["start"])
            end = float(cue["end"])
            content = str(cue.get("text", "")).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"cue {i}: thiếu start/end/text hợp lệ.") from exc
        if end <= start:
            raise ValueError(f"cue {i}: end phải lớn hơn start.")
        if not content:
            raise ValueError(f"cue {i}: text rỗng.")
        out.append(f"{cue.get('id', i)}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{content}")
    return "\n\n".join(out) + "\n"


def cues_from_segments(segments: list) -> list[dict]:
    """Từ pipeline segments ({src_text/tgt_text, start, end}) thành cues SRT."""
    cues: list[dict] = []
    for i, seg in enumerate(segments or [], 1):
        try:
            start = float(seg["start"])
            end = float(seg["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"segment {i}: thiếu start/end hợp lệ.") from exc
        content = str(seg.get("tgt_text") or seg.get("src_text") or seg.get("text") or "").strip()
        if end <= start:
            raise ValueError(f"segment {i}: end phải lớn hơn start.")
        if not content:
            continue
        cues.append({"id": seg.get("id", i), "start": start, "end": end, "text": content})
    return cues


def cues_to_text_track(cues: list, track_id: str = "subs") -> dict:
    """Đóng gói cues thành text track cho timeline.

    UI dubtool (editor/page.tsx:192-200) đọc track kind text với clip
    {start, duration, text}; bấm cue nhảy playhead tới start.
    """
    clips = []
    for i, cue in enumerate(cues or [], 1):
        start = float(cue["start"])
        duration = float(cue["end"]) - start
        if duration <= 0:
            raise ValueError(f"cue {i}: end phải lớn hơn start.")
        clips.append({
            "id": cue.get("id", f"{track_id}-cue-{i}"),
            "start": start,
            "duration": duration,
            "text": str(cue.get("text", "")).strip(),
        })
    return {"id": track_id, "kind": "subtitle", "clips": clips}


def words_from_whisper(words: list) -> list[dict]:
    """Chuẩn hoá word timestamps kiểu Whisper/faster-whisper thành [{w, start, end}].

    Chấp nhận dict {word/w/text, start, end} hoặc object có attrs tương ứng
    (như dubtool studio_service.py:649-656 dùng entry.word/entry.start/entry.end).
    """
    norm: list[dict] = []
    for i, entry in enumerate(words or [], 1):
        if isinstance(entry, dict):
            w = entry.get("word", entry.get("w", entry.get("text", "")))
            start, end = entry.get("start"), entry.get("end")
        else:
            w = getattr(entry, "word", None)
            if w is None:
                w = getattr(entry, "text", "")
            start, end = getattr(entry, "start", None), getattr(entry, "end", None)
        w = str(w or "").strip()
        try:
            start_f, end_f = float(start), float(end)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"word {i}: thiếu start/end số hợp lệ.") from exc
        if not w:
            raise ValueError(f"word {i}: text rỗng.")
        if end_f <= start_f:
            raise ValueError(f"word {i}: end phải lớn hơn start.")
        if start_f < 0:
            raise ValueError(f"word {i}: start âm.")
        norm.append({"w": w, "start": start_f, "end": end_f})
    return norm


def merge_words_to_cues(words: list, max_chars: int = 84, max_secs: float = 10) -> list[dict]:
    """Gom word stamps thành cue câu theo giới hạn ký tự + thời lượng.

    Giới hạn mặc định theo quy ước dubtool stt.py:49-63 (chia segment dài
    thành nhiều cue ngắn để TTS/phụ đề dễ đọc).
    """
    norm = words_from_whisper(words) if words and not (
        isinstance(words[0], dict) and set(words[0]) == {"w", "start", "end"}
    ) else [dict(w=w["w"], start=float(w["start"]), end=float(w["end"])) for w in (words or [])]
    cues: list[dict] = []
    buf: list[dict] = []

    def flush() -> None:
        if not buf:
            return
        cues.append({
            "id": len(cues) + 1,
            "start": buf[0]["start"],
            "end": buf[-1]["end"],
            "text": " ".join(b["w"] for b in buf).strip(),
        })
        buf.clear()

    for entry in norm:
        trial = " ".join([*(b["w"] for b in buf), entry["w"]])
        span = entry["end"] - (buf[0]["start"] if buf else entry["start"])
        if buf and (len(trial) > max_chars or span > max_secs):
            flush()
        buf.append(entry)
    flush()
    return cues


def retime_cues(cues: list, offset: float, scale: float = 1.0) -> list:
    """Dời (+offset giây) và co giãn (*scale) thời gian cues, giữ id/text."""
    if scale <= 0:
        raise ValueError("scale phải > 0.")
    out = []
    for i, cue in enumerate(cues or [], 1):
        try:
            start = float(cue["start"]) * scale + float(offset)
            end = float(cue["end"]) * scale + float(offset)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"cue {i}: start/end/offset không phải số.") from exc
        if end <= start:
            raise ValueError(f"cue {i}: end phải lớn hơn start sau retime.")
        if start < 0:
            raise ValueError(f"cue {i}: start âm sau retime.")
        item = dict(cue)
        item["start"] = start
        item["end"] = end
        out.append(item)
    return out
