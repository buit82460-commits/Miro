"""Timeline operations ported from dubtool (stdlib only, dict-based).

Nguon tham khao (chi doc, khong copy nguyen ham):
- ``C:\\dubtool\\core\\studio_model.py`` dong 440-560 (apply_operation va cac op)
- ``C:\\dubtool\\core\\studio_service.py`` dong 148-154 (undo/redo)
"""

import copy

__all__ = ["apply_operation", "History"]

_CLIP_COUNTER = 0
_TRACK_COUNTER = 0


def _round3(value):
    """Lam tron thoi gian ve 3 chu so thap phan.

    Nguon: C:\\dubtool\\core\\studio_model.py:610-618 (quantize).
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Thoi gian phai la so.")
    return round(number, 3)


def _time(value, name="start"):
    """Chuan hoa mot moc thoi gian (>= 0, tron 3 chu so).

    Nguon: C:\\dubtool\\core\\studio_model.py:543,631,640 (_time).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s phai la so." % name)
    result = _round3(value)
    if result < 0:
        raise ValueError("%s khong duoc am." % name)
    return result


def _duration(value):
    """Chuan hoa duration (> 0, tron 3 chu so)."""
    result = _time(value, "duration")
    if result <= 0:
        raise ValueError("duration phai > 0.")
    return result


def _next_clip_id(project):
    """Sinh id clip duy nhat dang ``clip-<n>``.

    Nguon: C:\\dubtool\\core\\studio_model.py:536 (_id("clip")).
    """
    global _CLIP_COUNTER
    existing = set()
    for track in project.get("tracks", []):
        for clip in track.get("clips", []):
            if isinstance(clip.get("id"), str):
                existing.add(clip["id"])
    while True:
        _CLIP_COUNTER += 1
        candidate = "clip-%d" % _CLIP_COUNTER
        if candidate not in existing:
            return candidate


def _next_track_id(project):
    """Sinh id track duy nhat dang ``track-<n>``.

    Nguon: C:\\dubtool\\core\\studio_model.py:498 (_id("track")).
    """
    global _TRACK_COUNTER
    existing = {t.get("id") for t in project.get("tracks", []) if isinstance(t.get("id"), str)}
    while True:
        _TRACK_COUNTER += 1
        candidate = "track-%d" % _TRACK_COUNTER
        if candidate not in existing:
            return candidate


def _tracks(project):
    tracks = project.get("tracks")
    if not isinstance(tracks, list):
        raise ValueError("project['tracks'] phai la list.")
    return tracks


def _find_track(project, track_id):
    """Tim track theo id.

    Nguon: C:\\dubtool\\core\\studio_model.py:520 (_track).
    """
    for track in _tracks(project):
        if track.get("id") == track_id:
            if not isinstance(track.get("clips"), list):
                track["clips"] = []
            return track
    raise ValueError("Khong tim thay track: %r." % (track_id,))


def _find_clip(project, clip_id):
    """Tim (track, clip) theo clip id.

    Nguon: C:\\dubtool\\core\\studio_model.py:548 (_clip).
    """
    for track in _tracks(project):
        for clip in track.get("clips", []):
            if clip.get("id") == clip_id:
                return track, clip
    raise ValueError("Khong tim thay clip: %r." % (clip_id,))


def _normalize_clip(project, raw, default_start=0.0):
    """Chuan hoa clip dict: dam bao id duy nhat, start/duration tron 3 chu so.

    Nguon: C:\\dubtool\\core\\studio_model.py:531-537 (add_clip).
    """
    if not isinstance(raw, dict):
        raise ValueError("Clip phai la dict.")
    clip = copy.deepcopy(raw)
    if not isinstance(clip.get("id"), str) or not clip["id"]:
        clip["id"] = _next_clip_id(project)
    clip["start"] = _time(clip.get("start", default_start), "start")
    if "duration" in clip:
        clip["duration"] = _duration(clip["duration"])
    else:
        clip["duration"] = 1.0
    return clip


def apply_operation(project, op):
    """Ap dung mot operation len project dict, tra ve project moi (deep copy).

    Ho tro 14 op: add_track, update_track, delete_track, add_clip, update_clip,
    delete_clip, split_clip, move_clip, duplicate_clip, replace_clip, copy,
    paste, crossfade, batch.

    Nguon: C:\\dubtool\\core\\studio_model.py:445-473 (apply_operation, batch).
    """
    if not isinstance(project, dict):
        raise ValueError("project phai la dict.")
    if not isinstance(op, dict) or not isinstance(op.get("type"), str):
        raise ValueError("Thieu loai thao tac (op['type']).")
    kind = op["type"]
    params = {k: v for k, v in op.items() if k != "type"}

    handlers = {
        "add_track": _op_add_track,
        "update_track": _op_update_track,
        "delete_track": _op_delete_track,
        "remove_track": _op_delete_track,
        "add_clip": _op_add_clip,
        "update_clip": _op_update_clip,
        "delete_clip": _op_delete_clip,
        "split_clip": _op_split_clip,
        "move_clip": _op_move_clip,
        "duplicate_clip": _op_duplicate_clip,
        "replace_clip": _op_replace_clip,
        "copy": _op_copy,
        "copy_clip": _op_copy,
        "paste": _op_paste,
        "paste_clip": _op_paste,
        "crossfade": _op_crossfade,
        "batch": _op_batch,
    }
    handler = handlers.get(kind)
    if handler is None:
        raise ValueError("Thao tac chua duoc ho tro: %r." % (kind,))

    result = copy.deepcopy(project)
    if "tracks" not in result or not isinstance(result["tracks"], list):
        result["tracks"] = []
    if "_clipboard" not in result:
        result["_clipboard"] = None
    handler(result, params)
    return result


def _op_add_track(project, params):
    """Them track moi.

    Nguon: C:\\dubtool\\core\\studio_model.py:496-498 (add_track).
    """
    track = {
        "id": params.get("id") if isinstance(params.get("id"), str) else _next_track_id(project),
        "kind": params.get("kind", "video"),
        "clips": [],
    }
    if "name" in params:
        track["name"] = params["name"]
    project["tracks"].append(track)


def _op_update_track(project, params):
    """Cap nhat truong cua track.

    Nguon: C:\\dubtool\\core\\studio_model.py:519-522 (update_track).
    """
    track = _find_track(project, params.get("track_id"))
    changes = params.get("changes", params.get("fields", {}))
    if not isinstance(changes, dict):
        raise ValueError("update_track can 'changes' la dict.")
    changes = {k: v for k, v in changes.items() if k not in ("id", "clips")}
    track.update(copy.deepcopy(changes))


def _op_delete_track(project, params):
    """Xoa track khoi project.

    Nguon: C:\\dubtool\\core\\studio_model.py:523-525 (remove_track).
    """
    track = _find_track(project, params.get("track_id"))
    project["tracks"].remove(track)


def _op_add_clip(project, params):
    """Them clip vao track.

    Nguon: C:\\dubtool\\core\\studio_model.py:531-537 (add_clip).
    """
    track = _find_track(project, params.get("track_id"))
    clip = _normalize_clip(project, params.get("clip"))
    track["clips"].append(clip)


def _op_update_clip(project, params):
    """Cap nhat truong cua clip (tru id).

    Nguon: C:\\dubtool\\core\\studio_model.py:551-563 (update_clip).
    """
    _, clip = _find_clip(project, params.get("clip_id"))
    changes = params.get("changes", params.get("fields", {}))
    if not isinstance(changes, dict):
        raise ValueError("update_clip can 'changes' la dict.")
    for key, value in copy.deepcopy(changes).items():
        if key == "id":
            raise ValueError("Khong duoc doi id clip truc tiep.")
        if key == "start":
            clip["start"] = _time(value, "start")
        elif key == "duration":
            clip["duration"] = _duration(value)
        else:
            clip[key] = value


def _op_delete_clip(project, params):
    """Xoa clip; ripple=True keo cac clip sau ve truoc.

    Nguon: C:\\dubtool\\core\\studio_model.py:621-628 (delete_clip + ripple).
    """
    track, clip = _find_clip(project, params.get("clip_id"))
    ripple = params.get("ripple", False)
    if not isinstance(ripple, bool):
        raise ValueError("ripple phai la True/False.")
    end = _round3(clip.get("start", 0.0) + clip.get("duration", 0.0))
    gap = _round3(clip.get("duration", 0.0))
    track["clips"].remove(clip)
    if ripple:
        for later in track["clips"]:
            if later.get("start", 0.0) >= end - 1e-9:
                later["start"] = _round3(later["start"] - gap)


def _op_split_clip(project, params):
    """Chia clip thanh 2 tai thoi diem t (params 'at' hoac 't').

    Nguon: C:\\dubtool\\core\\studio_model.py:639-648 (split_clip).
    """
    raw_at = params.get("at", params.get("t"))
    track, clip = _find_clip(project, params.get("clip_id"))
    at = _time(raw_at, "at")
    start = clip.get("start", 0.0)
    duration = clip.get("duration", 0.0)
    delta = _round3(at - start)
    if delta <= 0 or delta >= duration:
        raise ValueError("Diem chia 'at' phai nam ben trong clip.")
    left = copy.deepcopy(clip)
    right = copy.deepcopy(clip)
    left["duration"] = delta
    right["id"] = _next_clip_id(project)
    right["start"] = at
    right["duration"] = _round3(duration - delta)
    index = track["clips"].index(clip)
    track["clips"][index] = left
    track["clips"].insert(index + 1, right)


def _op_move_clip(project, params):
    """Doi start (va chuyen track neu co track_id).

    Nguon: C:\\dubtool\\core\\studio_model.py:633-638 (move_clip).
    """
    track, clip = _find_clip(project, params.get("clip_id"))
    if "start" in params:
        clip["start"] = _time(params["start"], "start")
    target_id = params.get("track_id", params.get("to_track"))
    if target_id is not None and target_id != track.get("id"):
        target = _find_track(project, target_id)
        track["clips"].remove(clip)
        target["clips"].append(clip)


def _op_duplicate_clip(project, params):
    """Nhan ban clip (id moi), co the doi start.

    Nguon: C:\\dubtool\\core\\studio_model.py:629-632 (duplicate_clip).
    """
    track, clip = _find_clip(project, params.get("clip_id"))
    dup = copy.deepcopy(clip)
    dup["id"] = _next_clip_id(project)
    if "start" in params:
        dup["start"] = _time(params["start"], "start")
    else:
        dup["start"] = _round3(clip.get("start", 0.0) + clip.get("duration", 0.0))
    track["clips"].append(dup)


def _op_replace_clip(project, params):
    """Thay noi dung clip nhung giu id/start/duration cu (neu khong ghi de).

    Nguon: C:\\dubtool\\core\\studio_model.py:564-571 (replace_clip).
    """
    _, clip = _find_clip(project, params.get("clip_id"))
    replacement = params.get("clip", params.get("with"))
    if not isinstance(replacement, dict):
        raise ValueError("replace_clip can 'clip' la dict.")
    keep = {"id": clip.get("id"), "start": clip.get("start"), "duration": clip.get("duration")}
    clip.clear()
    clip.update(copy.deepcopy(replacement))
    clip["id"] = keep["id"]
    if "start" not in params.get("clip", {}) and "start" not in params:
        clip["start"] = keep["start"]
    else:
        clip["start"] = _time(clip.get("start", keep["start"]), "start")
    if "duration" not in (params.get("clip") or {}):
        clip["duration"] = keep["duration"]
    else:
        clip["duration"] = _duration(clip.get("duration", keep["duration"]))
    if not isinstance(clip.get("id"), str) or not clip["id"]:
        raise ValueError("replace_clip giu id khong hop le.")


def _op_copy(project, params):
    """Luu ban sao clip vao clipboard noi bo project['_clipboard'].

    Nguon: C:\\dubtool\\core\\studio_model.py:549-550 (copy_clip + clipboard).
    """
    _, clip = _find_clip(project, params.get("clip_id"))
    project["_clipboard"] = copy.deepcopy(clip)


def _op_paste(project, params):
    """Dan clip tu clipboard (hoac clip kem theo) vao track.

    Nguon: C:\\dubtool\\core\\studio_model.py:538-544 (paste_clip).
    """
    track = _find_track(project, params.get("track_id"))
    source = params.get("clip")
    if source is None:
        source = project.get("_clipboard")
    if source is None:
        raise ValueError("Clipboard trong, khong co gi de paste.")
    pasted = _normalize_clip(project, copy.deepcopy(source))
    pasted["id"] = _next_clip_id(project)
    if "start" in params:
        pasted["start"] = _time(params["start"], "start")
    track["clips"].append(pasted)


def _op_crossfade(project, params):
    """Danh dau metadata crossfade giua 2 clip (khong cat audio that).

    Nguon: C:\\dubtool\\core\\studio_model.py:649-658 (crossfade).
    """
    _, clip = _find_clip(project, params.get("clip_id"))
    duration = _duration(params.get("duration", 0.5))
    if duration >= clip.get("duration", 0.0):
        raise ValueError("crossfade duration phai ngan hon clip.")
    meta = clip.get("crossfade")
    if not isinstance(meta, dict):
        meta = {}
        clip["crossfade"] = meta
    meta.update({
        "duration": duration,
        "style": params.get("style", meta.get("style", "linear")),
    })
    if "with_clip" in params:
        meta["with_clip"] = params["with_clip"]


def _op_batch(project, params):
    """Ap dung list ops tuan tu tren cung project.

    Nguon: C:\\dubtool\\core\\studio_model.py:465-473 (batch, khong long nhau).
    """
    operations = params.get("operations", params.get("ops"))
    if not isinstance(operations, list) or not operations:
        raise ValueError("batch can 'operations' la list khong rong.")
    if any(not isinstance(item, dict) or item.get("type") == "batch" for item in operations):
        raise ValueError("Khong ho tro batch long nhau hoac op khong hop le.")
    for item in operations:
        project.clear()
        project.update(apply_operation(project, item))


class History:
    """Undo/redo 2 chieu bang stack snapshots (gioi han 50).

    Nguon: C:\\dubtool\\core\\studio_service.py:148-154 (undo/redo).
    """

    LIMIT = 50

    def __init__(self, initial=None):
        """Khoi tao lich su voi snapshot ban dau (deep copy)."""
        self._undo = []
        self._redo = []
        self._present = copy.deepcopy(initial) if initial is not None else None

    def push(self, state):
        """Day state hien tai vao undo stack, xoa redo stack."""
        if self._present is not None:
            self._undo.append(copy.deepcopy(self._present))
            if len(self._undo) > self.LIMIT:
                del self._undo[0]
        self._present = copy.deepcopy(state)
        self._redo.clear()

    def undo(self):
        """Lui 1 buoc; het lich su thi ValueError."""
        if not self._undo:
            raise ValueError("Khong con gi de undo.")
        self._redo.append(copy.deepcopy(self._present))
        self._present = self._undo.pop()
        return copy.deepcopy(self._present)

    def redo(self):
        """Tien 1 buoc; het lich su thi ValueError."""
        if not self._redo:
            raise ValueError("Khong con gi de redo.")
        self._undo.append(copy.deepcopy(self._present))
        self._present = self._redo.pop()
        return copy.deepcopy(self._present)

    def current(self):
        """Tra ve snapshot hien tai (deep copy)."""
        return copy.deepcopy(self._present)
