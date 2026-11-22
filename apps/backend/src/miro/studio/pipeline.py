# -*- coding: utf-8 -*-
"""Studio pipeline that C that (port of A: C:\\dubtool\\core\\pipeline.py + core/cache.py).

Architecture C does NOT import module cu. Every method runs cu that or
delegates to a cu service: download/transcribe/translate/tts/mix/render +
cache/invalidation.

Sources (traceability for Checker):
- A pipeline:  C:\\dubtool\\core\\pipeline.py:28 (STEPS), :105-120 (_mark_step),
  :123-133 (_find_video_id), :136-389 (8 steps), :392-412 (_hydrate),
  :415-448 (run), :451-482 (revoice_segment)
- A cache:     C:\\dubtool\\core\\cache.py:1-57 (markers, hash_file/hash_text)
- A app.py:    :42-62 do_download, :65-82 do_run_to_translate, :106-123
  save_segments (invalidate from tts), :126-142 do_tts_mix_render,
  :154-167 revoice, :195-209 add_overlay (invalidate render only),
  :213-229 do_final_render, :257-266 submit_studio (queue only),
  :343-352 open_multitrack (create_from_dubtool)
- B gaps:      D:\\JARVIS-Assistant\\backend\\app\\integrations\\dubtool_tasks.py:163-176
  (atomic persist: tmp+fsync+replace), :196-209 (fingerprint),
  backend/app/jobs/manager.py:215-244 (single slot + contamination),
  backend/app/jobs/runner.py:218-229 + core/execution_policy.py:15-26,45-56
  (retry TRANSIENT with budget), :155-166 (workerOwner liveness — deferred,
  in-process worker, documented in handlers.py)

Heavy ML engines (whisper/NLLB/neural TTS) are pluggable via LocalEngine
method overrides. The default engine uses only stdlib + ffmpeg, so every step
produces cu files on disk (no 100% mocks): cu audio/video/artifacts,
cu hashes and signatures, cu downstream invalidation.
"""
from __future__ import annotations

import array
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import threading
import time
import wave
from pathlib import Path

STEPS = ["download", "audio", "stt", "translate", "tts", "sync", "mix", "render"]

# Steps that are pure functions of (inputs + cache): safe to retry on
# transient OS/timeout errors. download (network side effects) and render
# (expensive, timestamped output) fail fast — B: no replay of uncertain work.
IDEMPOTENT_RETRY_STEPS = frozenset({"audio", "stt", "translate", "tts", "sync", "mix"})
TRANSIENT_ERRORS = (OSError, TimeoutError, ConnectionError)

# Ma TRANSIENT duoc retry (port A shared/execution_policy.py TRANSIENT +
# TRANSIENT_CODES ben tasks/service.py). Dung de phan loai PipelineError
# trong _guarded — truoc day nhanh retry khong bao gio kich hoat vi engine
# chi nem PipelineError (T3).
PIPELINE_TRANSIENT_CODES = frozenset({
    "REMOTE_TIMEOUT", "CONNECTION_ERROR", "TAB_LEASE_BUSY",
    "DEPENDENCY_UNAVAILABLE", "REMOTE_RATE_LIMITED",
    "REMOTE_502", "REMOTE_503", "REMOTE_504", "HTTP_429", "HTTP_502",
    "HTTP_503", "HTTP_504", "ECONNRESET", "ECONNREFUSED", "ETIMEDOUT",
    "EAI_AGAIN", "EPIPE", "ENETUNREACH", "TEMPORARY_FAILURE",
    "DOWNLOAD_FAILED",
})

_PIPELINE_CODE_RE = re.compile(r"^([A-Z0-9_]+)[:\s]")


# ---------------------------------------------------------------- cache ----
def hash_file(path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def signature_of(value) -> str:
    return hash_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def atomic_write_json(path, data) -> None:
    """tmp + fsync + replace (B: dubtool_tasks.py:139-156)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def done_path(work_dir: Path, step: str, input_hash: str | None = None) -> Path:
    name = f"{step}.{input_hash}.done" if input_hash else f"{step}.done"
    return work_dir / name


# ------------------------------------------------------------- exceptions ----
class PipelineError(RuntimeError):
    """Step failure. Carries a machine-readable code for terminal persist."""


class PipelineCancelled(RuntimeError):
    """User cancel giua chung: khong retry, khong contamination, tha slot."""


class PipelineConflict(ValueError):
    status_code = 409
    status = 409


def _conflict(message: str) -> PipelineConflict:
    error = PipelineConflict(message)
    error.status_code = error.status = 409
    return error


# ------------------------------------------------------------- local engine --
class LocalEngine:
    """cu step implementations using stdlib + ffmpeg only.

    Subclass and override any method to plug heavy backends
    (faster-whisper, NLLB/LLM translate, neural TTS) without touching
    the orchestration below.
    """

    SAMPLE_RATE = 16000

    def __init__(self, voices_dir: Path | None = None):
        self.voices_dir = Path(voices_dir) if voices_dir else None
        self._ffmpeg = shutil.which("ffmpeg")
        self._ffprobe = shutil.which("ffprobe")

    def _require_ffmpeg(self) -> str:
        if not self._ffmpeg:
            raise PipelineError("FFMPEG_MISSING: khong tim thay ffmpeg trong PATH.")
        return self._ffmpeg

    # -- download (A: pipeline.py:136-152) --
    def download(self, source: str, work_dir: Path, progress_cb=None) -> dict:
        self._require_ffmpeg()
        work_dir.mkdir(parents=True, exist_ok=True)
        local = Path(source)
        if local.is_file():
            video_id = "local-" + hash_file(local)
            target = work_dir.parent / video_id
            target.mkdir(parents=True, exist_ok=True)
            dest = target / (local.name if local.suffix else "video.mp4")
            if not dest.is_file() or hash_file(dest) != hash_file(local):
                shutil.copy2(local, dest)
            return {"video_id": video_id, "path": str(dest),
                    "title": local.stem, "duration": self.probe_duration(dest)}
        if re.match(r"^https?://", source.strip(), re.IGNORECASE):
            try:
                import yt_dlp  # type: ignore
            except ImportError:
                raise PipelineError(
                    "DOWNLOAD_UNAVAILABLE: URL can yt-dlp nhung chua cai dat "
                    "(pip install yt-dlp). Dung file video local.")
            out = work_dir / "%(id)s.%(ext)s"
            cmd = ["yt-dlp", "--no-playlist", "-f", "bv*+ba/b",
                   "-o", str(out), source.strip()]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode:
                raise PipelineError(f"DOWNLOAD_FAILED: {result.stderr[-500:]}")
            files = sorted(work_dir.glob("*.*"))
            videos = [f for f in files if f.suffix.lower() in
                      (".mp4", ".mkv", ".webm", ".mov", ".m4v")]
            if not videos:
                raise PipelineError("DOWNLOAD_FAILED: khong tim thay file video sau tai.")
            video = max(videos, key=lambda f: f.stat().st_size)
            return {"video_id": "url-" + hash_text(source.strip()), "path": str(video),
                    "title": video.stem, "duration": self.probe_duration(video)}
        raise PipelineError(f"SOURCE_NOT_FOUND: khong tim thay file '{source}'.")

    def probe_duration(self, path) -> float:
        if not self._ffprobe:
            return 0.0
        try:
            result = subprocess.run(
                [self._ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "json", str(path)],
                capture_output=True, text=True, timeout=30)
            return float(json.loads(result.stdout)["format"]["duration"])
        except (OSError, ValueError, KeyError):
            return 0.0

    # -- audio (A: pipeline.py:182-193) --
    def extract_audio(self, video_path: str, work_dir: Path) -> dict:
        ffmpeg = self._require_ffmpeg()
        work_dir.mkdir(parents=True, exist_ok=True)
        stt_wav = work_dir / "stt.wav"
        orig_wav = work_dir / "orig.wav"
        for out, rate, ch in ((stt_wav, 16000, 1), (orig_wav, 44100, 2)):
            result = subprocess.run(
                [ffmpeg, "-y", "-v", "error", "-i", str(video_path),
                 "-vn", "-ar", str(rate), "-ac", str(ch), "-c:a", "pcm_s16le", str(out)],
                capture_output=True, text=True, timeout=300)
            if result.returncode or not out.is_file():
                raise PipelineError(f"AUDIO_FAILED: {result.stderr[-300:]}")
        return {"stt_wav": str(stt_wav), "orig_wav": str(orig_wav)}

    # -- stt: faster-whisper khi co model, fallback VAD cu --
    def transcribe(self, video_id: str, stt_wav: str, work_dir: Path,
                   language: str = "auto", progress_cb=None,
                   words: bool = False) -> list[dict]:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError:
            WhisperModel = None
        if WhisperModel is not None:
            try:
                return self._whisper_segments(WhisperModel, stt_wav, language,
                                              words=words)
            except PipelineError:
                raise
            except Exception as exc:
                raise PipelineError(f"STT_FAILED: faster-whisper loi: {exc}") from exc
        return self._vad_segments(stt_wav, words=words)

    def _whisper_segments(self, WhisperModel, stt_wav: str,
                          language: str, words: bool = False) -> list[dict]:
        try:
            model = WhisperModel("small", device="cpu", compute_type="int8")
            lang = None if (language or "auto") == "auto" else language
            segments_iter, info = model.transcribe(stt_wav, language=lang,
                                                   vad_filter=True,
                                                   word_timestamps=True)
            out = []
            for i, seg in enumerate(segments_iter):
                entry = {
                    "id": i + 1,
                    "start": round(float(seg.start), 3),
                    "end": round(float(seg.end), 3),
                    "src_text": (seg.text or "").strip(), "tgt_text": "",
                    "flags": [],
                }
                word_list = []
                for w in (getattr(seg, "words", None) or []):
                    text = (getattr(w, "word", None) or "").strip()
                    try:
                        ws, we = float(w.start), float(w.end)
                    except (TypeError, ValueError):
                        continue
                    if text and we > ws:
                        word_list.append({"w": text, "start": round(ws, 3),
                                          "end": round(we, 3)})
                if word_list:
                    entry["words"] = word_list
                    entry["flags"] = ["word_timestamp_asr"]
                elif words:
                    entry["flags"] = ["words_unavailable"]
                out.append(entry)
            detected = getattr(info, "language", None) or "unknown"
            prob = round(float(getattr(info, "language_probability", 0.0) or 0.0), 3)
            atomic_write_json(Path(stt_wav).parent / "stt_info.json",
                              {"detected_language": detected,
                               "language_probability": prob, "backend": "faster-whisper-small"})
            if out:
                return out
        except Exception:
            pass
        segs = self._vad_segments(stt_wav, words=words)
        for s in segs:
            s["flags"] = sorted(set(s.get("flags", [])) | {"whisper_empty"})
        return segs

    def _vad_segments(self, stt_wav: str, words: bool = False) -> list[dict]:
        with wave.open(stt_wav, "rb") as wav:
            if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
                raise PipelineError("STT_FAILED: stt.wav phai la mono 16-bit.")
            rate = wav.getframerate()
            raw = wav.readframes(wav.getnframes())
        samples = array.array("h", raw)
        frame_n = max(1, int(rate * 0.02))
        energies = []
        for i in range(0, len(samples), frame_n):
            frame = samples[i:i + frame_n]
            if not frame:
                break
            energies.append(sum(s * s for s in frame) / len(frame))
        if not energies:
            raise PipelineError("STT_FAILED: audio rong.")
        peak = max(energies)
        thresh = max(peak * 0.02, 200.0 ** 2)
        min_sil_frames = int(0.30 / 0.02)
        min_seg_frames = int(0.40 / 0.02)
        segments, start, silence = [], None, 0
        for idx, energy in enumerate(energies):
            voiced = energy >= thresh
            if voiced:
                if start is None:
                    start = idx
                silence = 0
            elif start is not None:
                silence += 1
                if silence >= min_sil_frames:
                    if idx - silence - start >= min_seg_frames:
                        segments.append((start, idx - silence))
                    start, silence = None, 0
        if start is not None and len(energies) - start >= min_seg_frames:
            segments.append((start, len(energies)))
        if not segments:
            total = len(samples) / rate
            segments = [(0, len(energies))] if total > 0.2 else []
        want_words = bool(words)
        out = []
        for i, (a, b) in enumerate(segments):
            flags = ["vad", "needs_review"]
            if want_words:
                flags.append("words_unavailable")
            out.append({
                "id": i + 1,
                "start": round(max(0.0, a * 0.02 - 0.05), 3),
                "end": round(min(len(samples) / rate, b * 0.02 + 0.05), 3),
                "src_text": "", "tgt_text": "",
                "flags": flags,
            })
        info = {"detected_language": "unknown", "backend": "vad"}
        atomic_write_json(Path(stt_wav).parent / "stt_info.json", info)
        return out

    # -- translate: local dictionary fallback (A: pipeline.py:213-261 shape) --
    VI_DICT = {
        "hello": "xin chao", "world": "the gioi", "welcome": "chao mung",
        "back": "tro lai", "thank": "cam on", "you": "ban", "good": "tot",
        "morning": "buoi sang", "video": "video", "today": "hom nay",
    }

    def translate(self, segments: list[dict], src: str, tgt: str) -> list[dict]:
        if src not in ("vi", "en", "zh", "auto"):
            raise PipelineError(f"TRANSLATE_FAILED: chua ho tro dich tu '{src}'.")
        if src == "auto":
            src = "en"
        texts = [(seg.get("src_text") or "").strip() for seg in segments]
        if src != tgt and any(texts) and src in ("vi", "en", "zh") \
                and tgt in ("vi", "en", "zh"):
            try:
                from miro.studio import translate_mt as _mt
                outs = _mt.translate_batch_llm(
                    texts, src, tgt,
                    endpoint=os.environ.get("LLM_API_ENDPOINT", "") or None,
                    api_key=os.environ.get("LLM_API_KEY", "") or None,
                    model=os.environ.get("LLM_MODEL", "") or None,
                    provider=os.environ.get("LLM_PROVIDER", "") or None)
                return [self._with_tgt(seg, o, "llm")
                        for seg, o in zip(segments, outs)]
            except RuntimeError:
                pass
            try:
                from miro.studio import translate_mt as _mt2
                outs = _mt2.translate_batch_nllb(texts, src, tgt)
                return [self._with_tgt(seg, o, "nllb")
                        for seg, o in zip(segments, outs)]
            except RuntimeError:
                pass
        out = []
        for seg in segments:
            text = (seg.get("src_text") or "").strip()
            if not text:
                out.append({**seg, "tgt_text": seg.get("tgt_text") or "",
                            "flags": sorted(set(seg.get("flags", [])) | {"untranslated"})})
                continue
            if src == "en" and tgt == "vi":
                words = [self.VI_DICT.get(w.lower(), w) for w in text.split()]
                tgt_text = " ".join(words)
                flags = set(seg.get("flags", [])) | {"local_dict"}
            elif src == tgt:
                tgt_text, flags = text, set(seg.get("flags", []))
            else:
                tgt_text, flags = text, set(seg.get("flags", [])) | {"needs_review"}
            if tgt_text != text or src == tgt:
                pass
            out.append({**seg, "tgt_text": tgt_text, "flags": sorted(flags)})
        return out

    @staticmethod
    def _with_tgt(seg: dict, tgt_text: str, backend: str) -> dict:
        """Gan ban dich MT + flag backend; cau rong giu nguyen + untranslated."""
        if not (seg.get("src_text") or "").strip():
            flags = sorted(set(seg.get("flags", [])) | {"untranslated"})
            return {**seg, "tgt_text": seg.get("tgt_text") or "",
                    "flags": flags}
        flags = sorted(set(seg.get("flags", [])) | {backend})
        return {**seg, "tgt_text": (tgt_text or "").strip(), "flags": flags}

    # -- tts: engine that (vieneu/piper) truoc, tone mau fallback --
    def synthesize(self, text: str, voice: str, out_path: Path, duration: float) -> Path:
        engine_name = (os.environ.get("MIRO_TTS_ENGINE", "") or "").strip().lower()
        if engine_name in ("vieneu", "piper"):
            try:
                return self._synthesize_real(text, voice, out_path)
            except Exception:
                pass
        duration = max(0.3, float(duration))
        rate = self.SAMPLE_RATE
        freq = 220.0 + (int(hash_text(text + voice)[:4], 16) % 220)
        n = int(rate * duration)
        frames = array.array("h")
        for i in range(n):
            t = i / rate
            env = min(1.0, i / (rate * 0.02), (n - i) / (rate * 0.05))
            frames.append(int(12000 * env * math.sin(2 * math.pi * freq * t)))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(frames.tobytes())
        return out_path

    def _synthesize_real(self, text: str, voice: str, out_path: Path) -> Path:
        """Goi engine TTS that tu C:/dubtool/core/tts (lazy, khong copy code).

        Raises Exception de caller fallback ve tone mau.
        """
        import sys
        engine_name = (os.environ.get("MIRO_TTS_ENGINE", "") or "").strip().lower()
        lang = "vi" if engine_name == "vieneu" else "en"
        dubtool_root = os.environ.get("MIRO_DUBTOOL_ROOT", "C:/dubtool")
        added = False
        if dubtool_root not in sys.path:
            sys.path.insert(0, dubtool_root)
            added = True
        try:
            from core.tts import get_engine as _get_engine
            try:
                from core.textnorm import normalize_for_tts as _norm
                text = _norm(text, lang)
            except Exception:
                pass
            engine = _get_engine(lang)
            return Path(engine.synthesize(text, voice, out_path))
        finally:
            if added:
                try:
                    sys.path.remove(dubtool_root)
                except ValueError:
                    pass

    def wav_duration(self, path) -> float:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate() or 1)

    # -- mix: stdlib PCM placement + gain + normalize + atempo (A mix.py:31-61) --
    @staticmethod
    def atempo_chain(speed: float) -> str:
        """Port A ffmpeg_utils.atempo_chain :16-27 (atempo chi 0.5-2.0)."""
        parts: list[str] = []
        s = float(speed)
        while s > 2.0:
            parts.append("atempo=2.0")
            s /= 2.0
        while s < 0.5:
            parts.append("atempo=0.5")
            s /= 0.5
        parts.append(f"atempo={s:.6g}")
        return ",".join(parts)

    def _sped_clip(self, seg_wav: Path, speed: float, rate: int) -> "array.array":
        """Doc wav + ap atempo khi speed != 1 bang ffmpeg file tam.

        Ghi chu Phase B: KHONG thay atempo_chain bang fx.speed_filter hoan
        toan. fx.speed_filter chi chap nhan speed 0.25-4 (studio_model gioi
        han), con timeline sync co the cho speed < 0.25 (do ngan/slot dai).
        Nen thu fx.speed_filter truoc, ValueError -> fallback atempo_chain cu
        de giu hanh vi cu.
        """
        import shutil
        import subprocess
        import tempfile

        if abs(float(speed or 1.0) - 1.0) < 1e-6:
            with wave.open(str(seg_wav), "rb") as wav:
                return array.array("h", wav.readframes(wav.getnframes()))
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise PipelineError("FFMPEG_MISSING: khong ap atempo duoc.")
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "sped.wav"
            try:
                from miro.studio import fx as _fx
                chain = _fx.speed_filter(float(speed))
            except (ImportError, ValueError):
                chain = self.atempo_chain(float(speed))
            cmd = [ffmpeg, "-y", "-v", "error", "-i", str(seg_wav), "-af",
                   chain, "-ar", str(rate), "-ac", "1",
                   "-c:a", "pcm_s16le", str(tmp)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode or not tmp.is_file():
                raise PipelineError(f"ATEMPO_FAILED: {result.stderr[-300:]}")
            with wave.open(str(tmp), "rb") as wav:
                return array.array("h", wav.readframes(wav.getnframes()))

    def mix(self, timeline: list[dict], tts_dir: Path, orig_wav: str,
            total: float, orig_gain_db: float = -18.0) -> array.array:
        rate = self.SAMPLE_RATE
        n = max(1, int(total * rate))
        bed = array.array("h", [0]) * n
        gain = 10.0 ** (orig_gain_db / 20.0)
        try:
            with wave.open(orig_wav, "rb") as wav:
                ch, sw, fr = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
                raw = wav.readframes(wav.getnframes())
            if sw == 2:
                src = array.array("h", raw)
                if ch == 2:
                    src = array.array("h", (src[i] for i in range(0, len(src), 2)))
                if fr != rate:  # nearest-neighbor resample to the mix rate
                    src = array.array("h", (src[int(i * fr / rate)]
                                            for i in range(int(len(src) * rate / fr))))
                m = min(len(src), n)
                for i in range(m):
                    bed[i] = int(max(-32768, min(32767, bed[i] + src[i] * gain)))
        except (OSError, wave.Error, EOFError):
            pass
        for entry in timeline:
            seg_wav = Path(entry.get("tts_path") or "")
            if not seg_wav.is_file():
                continue
            speed = float(entry.get("speed") or 1.0)
            seg = self._sped_clip(seg_wav, speed, rate)
            off = int(entry["start"] * rate)
            m = min(len(seg), n - off)
            for i in range(max(0, m)):
                j = off + i
                bed[j] = int(max(-32768, min(32767, bed[j] + seg[i])))
            # A build_dub_track:57-60 cat im lang phan tran — C ghi co de UI bao.
            # P1 ghi nhan 2: them timing_exact (tran tu giay nao, dai bao nhieu)
            # de UI bao chinh xac thay vi boolean.
            if off + len(seg) > n:
                placed = max(0, n - off)
                entry["overflow"] = True
                entry["overflow_from"] = round(float(entry.get("start", 0.0))
                                               + placed / rate, 3)
                entry["overflow_secs"] = round((off + len(seg) - n) / rate, 3)
        peak = max([abs(s) for s in bed] + [1])
        if peak > 30000:
            scale = 30000.0 / peak
            bed = array.array("h", (int(s * scale) for s in bed))
        return bed

    # -- render via ffmpeg (A: pipeline.py:357-389 shape + studio preview boolean) --
    # Logo overlay: moi logo 1 input -i rieng theo dung thu tu [{n}:v] (A overlay.py
    # :92-107 — thieu la loi caller). preview boolean (A start_render: out temp/,
    # kep 20s, scale 640). audio_map tinh dong theo so logo input (P1 ghi nhan 4:
    # logo chen input vao giua -> "1:a" cung tro nham sang anh logo).
    # Blend (port dubtool _composite:280-296): overlay co "blend" != normal thi
    # dung blend=all_mode=... tren canvas full-size roi tra alpha goc, thay vi
    # overlay thuong. 6 mode: normal/multiply/screen/overlay/addition/difference.
    # Reverse: reverse=True -> `-vf reverse -af areverse` (khong overlay thi -vf
    # truc tiep; co overlay thi chen reverse vao dau chain + areverse cho audio).
    BLEND_MODES = frozenset(
        {"normal", "multiply", "screen", "overlay", "addition", "difference"})

    def render_video(self, video_path: str, mix_wav: str, out_path: Path,
                     overlays: list | None = None, subtitles: str | None = None,
                     preview: bool = False, reverse: bool = False) -> str:
        ffmpeg = self._require_ffmpeg()
        overlays = list(overlays or [])
        # Logo input rieng (A overlay.py): overlay type logo co "path" -> -i theo thu tu.
        logo_paths = [ov.get("path") for ov in overlays
                      if isinstance(ov, dict) and ov.get("type") == "logo" and ov.get("path")]
        logo_paths = [lp for lp in logo_paths if Path(lp).is_file()]
        use_mix = bool(mix_wav) and Path(mix_wav).is_file()
        # Thu tu input: 0=video, 1..k=logo, cuoi=mix -> audio_map phai nhay theo.
        mix_idx = 1 + len(logo_paths)
        audio_map = f"{mix_idx}:a" if use_mix else "0:a"
        cmd = [ffmpeg, "-y", "-v", "error", "-i", str(video_path)]
        for lp in logo_paths:
            cmd += ["-i", str(lp)]
        if use_mix:
            cmd += ["-i", str(mix_wav)]
        filt = ""
        if overlays and not preview:
            width, height = self._probe_dims(video_path)
            if reverse:
                filt = self._overlay_filter(overlays, width, height, logo_start=1,
                                            reverse=True)
            else:
                filt = self._overlay_filter(overlays, width, height, logo_start=1)
        vlabel = "vout"
        if subtitles and not preview:
            filt += (";" if filt else "") + f"[vout]subtitles='{_escape_sub(subtitles)}'[vsub]"
            vlabel = "vsub"
        audio_args = ["-map", audio_map]
        if reverse:
            audio_args = ["-af", "areverse", "-map", audio_map]
        if preview:
            vf = "reverse,scale=640:-1" if reverse else "scale=640:-1"
            cmd += ["-t", "20", "-vf", vf, "-map", "0:v"] + audio_args
        elif filt:
            cmd += ["-filter_complex", filt, "-map", f"[{vlabel}]"] + audio_args
        elif reverse:
            cmd += ["-vf", "reverse", "-map", "0:v"] + audio_args
        else:
            cmd += ["-map", "0:v", "-map", audio_map]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
                "-shortest", str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode or not Path(out_path).is_file():
            raise PipelineError(f"RENDER_FAILED: {result.stderr[-500:]}")
        return str(out_path)

    def _probe_dims(self, video_path: str) -> tuple[int, int]:
        """Kich thuoc video cho overlay toa do tuong doi (A overlay build_filter)."""
        if not self._ffprobe:
            return (1280, 720)
        try:
            import json as _json
            import subprocess as _sp
            r = _sp.run([self._ffprobe, "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height", "-of", "json",
                         str(video_path)], capture_output=True, text=True, timeout=60)
            st = (_json.loads(r.stdout or "{}").get("streams") or [{}])[0]
            return (int(st.get("width") or 1280), int(st.get("height") or 720))
        except Exception:
            return (1280, 720)

    def _overlay_filter(self, overlays: list, width: int = 1280,
                        height: int = 720, logo_start: int = 1,
                        reverse: bool = False, **_) -> str:
        """Filter_complex kieu A overlay.py build_filter (dau ra [vout]).

        - box: drawbox toa do tuong doi (giong A _px chan).
        - logo: [{cur}][{n}:v]overlay + scale truoc, input bat dau tu logo_start
          (input 0 la video). text: drawtext (can font Arial tren Windows).
          blur: crop + boxblur + overlay.
          Neu overlay co "blend" != normal trong 6 mode (port dubtool _composite
          :280-296): dung blend=all_mode=... tren canvas full-size roi tra
          alpha goc, thay vi overlay thuong. blend la/unknown -> overlay thuong
          (backward compat).
        - effect: fx.effect_filter(name, params) rap noi tiep [cur]->[v{step}].
        - color: fx.color_filter(adj) rap noi tiep [cur]->[v{step}].
        - transform: fx.transform_filter(t, w, h) rap noi tiep [cur]->[v{step}]
          (x/y trong t la toa do overlay, khong tieu thu o day — giu hanh vi
          dubtool: transform_filter khong dung x/y; neu can dich overlay thi
          dung them type khac).
        - transition: chi ho tro khi danh dau noi 2 doan; trong chain hien
          tai (1 video dau vao) raise PipelineError ro rang, khong bia.
        - mask: fx.mask_alpha qua filter noi tiep [cur]->[v{step}] (format=rgba
          truoc khi ap alpha). Neu mask rong (khong shape/chroma nao kich hoat)
          thi la no-op giu nguyen [cur]->[v{step}].
        - reverse=True: chen `reverse` vao dau chain (nguon video dao truoc
          khi overlay; audio dao bang `-af areverse` trong render_video).
        """
        from miro.studio import fx as _fx  # lazy import de tranh vong lap
        if not overlays and not reverse:
            return "null[vout]"
        parts: list[str] = []
        cur = "0:v"
        step = 0
        if reverse:
            parts.append(f"[0:v]reverse[v{step}]")
            cur = f"v{step}"
            step += 1
        if not overlays:
            parts.append(f"[{cur}]null[vout]")
            return ";".join(parts)
        li = logo_start  # input index cua logo ke tiep (0=video, sau la logo...)
        for ov in overlays:
            kind = ov.get("type")
            if kind == "box":
                x = self._px_even(float(ov.get("x", 0)), width)
                y = self._px_even(float(ov.get("y", 0)), height)
                w = self._px_even(float(ov.get("w", 0)), width)
                h = self._px_even(float(ov.get("h", 0)), height)
                if w <= 0:
                    w = self._px_even(0.5, width)
                if h <= 0:
                    h = self._px_even(0.5, height)
                parts.append(f"[{cur}]drawbox=x={x}:y={y}:w={w}:h={h}:"
                             f"color=black@0.6:t=fill[v{step}]")
                cur = f"v{step}"
            elif kind == "logo":
                scale_pct = float(ov.get("scale", 0.15))
                opacity = float(ov.get("opacity", 1.0))
                margin = int(ov.get("margin", 20))
                logo_w = max(2, int(width * scale_pct) // 2 * 2)
                anchor = str(ov.get("anchor", "tr"))
                if anchor == "tl":
                    pos = f"x={margin}:y={margin}"
                elif anchor == "bl":
                    pos = f"x={margin}:y='main_h-overlay_h-{margin}'"
                elif anchor == "br":
                    pos = (f"x='main_w-overlay_w-{margin}'"
                           f":y='main_h-overlay_h-{margin}'")
                else:
                    pos = f"x='main_w-overlay_w-{margin}':y={margin}"
                parts.append(f"[{li}:v]scale={logo_w}:-1,format=rgba,"
                             f"colorchannelmixer=aa={opacity}[lg{step}]")
                blend = str(ov.get("blend", "normal") or "normal").lower()
                if blend != "normal" and blend in self.BLEND_MODES:
                    # Port dubtool _composite:280-296 — blend RGB tren canvas
                    # full-size roi tra alpha goc truoc khi overlay cuoi.
                    parts.append(
                        f"[{cur}]split[keep{step}][blendbase{step}];"
                        f"color=c=black@0:s={width}x{height}:r=30,"
                        f"format=rgba[blank{step}];"
                        f"[blank{step}][lg{step}]overlay={pos}:format=auto,"
                        f"format=gbrap,split[blendrgb{step}][blenda{step}];"
                        f"[blenda{step}]alphaextract[originalalpha{step}];"
                        f"[blendbase{step}]format=gbrap[blendbg{step}];"
                        f"[blendbg{step}][blendrgb{step}]blend=all_mode={blend}"
                        f"[blended{step}];"
                        f"[blended{step}][originalalpha{step}]alphamerge"
                        f"[alphablend{step}];"
                        f"[keep{step}][alphablend{step}]overlay=0:0:format=auto"
                        f"[v{step}]")
                else:
                    parts.append(f"[{cur}][lg{step}]overlay={pos}[v{step}]")
                cur = f"v{step}"
                li += 1
            elif kind == "text":
                text = str(ov.get("text") or ov.get("content") or "")
                if not text:
                    raise PipelineError("OVERLAY_TEXT_EMPTY: text overlay can noi dung.")
                x = self._px_even(float(ov.get("x", 0.1)), width)
                y = self._px_even(float(ov.get("y", 0.85)), height)
                size = max(16, int(float(ov.get("size", 48))))
                color = str(ov.get("color", "white"))
                t_start = float(ov.get("t_start", 0))
                t_end = float(ov.get("t_end", 0))
                font = str(ov.get("font") or "C:/Windows/Fonts/arial.ttf")
                safe = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
                expr = f"drawtext=fontfile='{font}':text='{safe}':fontsize={size}:fontcolor={color}:x={x}:y={y}"
                if t_end > t_start:
                    expr += f":enable='between(t\\,{t_start}\\,{t_end})'"
                parts.append(f"[{cur}]{expr}[v{step}]")
                cur = f"v{step}"
            elif kind == "blur":
                x = self._px_even(float(ov.get("x", 0)), width)
                y = self._px_even(float(ov.get("y", 0)), height)
                w = self._px_even(float(ov.get("w", 0) or 0.3), width)
                h = self._px_even(float(ov.get("h", 0) or 0.2), height)
                t_start = float(ov.get("t_start", 0))
                t_end = float(ov.get("t_end", 0))
                en = f":enable='between(t\\,{t_start}\\,{t_end})'" if t_end > t_start else ""
                parts.append(
                    f"[{cur}]split=2[base{step}][tmp{step}];"
                    f"[tmp{step}]crop={w}:{h}:{x}:{y},boxblur=10[bl{step}];"
                    f"[base{step}][bl{step}]overlay={x}:{y}{en}[v{step}]")
                cur = f"v{step}"
            elif kind == "effect":
                try:
                    flt = _fx.effect_filter(str(ov.get("name", "")),
                                            ov.get("params") or ov)
                except ValueError as exc:
                    raise PipelineError(f"EFFECT_UNSUPPORTED: {exc}") from exc
                if "[IN]" in flt and "[OUT]" in flt:
                    # Effect da-statement (glow split/blend): thay placeholder.
                    parts.append(flt.replace("[IN]", f"[{cur}]")
                                    .replace("[OUT]", f"[v{step}]"))
                else:
                    parts.append(f"[{cur}]{flt}[v{step}]")
                cur = f"v{step}"
            elif kind == "color":
                flt = _fx.color_filter(ov.get("adj") or ov)
                if flt:
                    parts.append(f"[{cur}]{flt}[v{step}]")
                    cur = f"v{step}"
            elif kind == "transform":
                flt = _fx.transform_filter(ov.get("t") or ov, width, height)
                if flt:
                    parts.append(f"[{cur}]{flt}[v{step}]")
                    cur = f"v{step}"
            elif kind == "transition":
                dur = float(ov.get("duration", ov.get("d", 1.0)) or 1.0)
                try:
                    tflt = _fx.transition_filter(str(ov.get("name", "fade")),
                                                 max(0.05, dur))
                except ValueError as exc:
                    raise PipelineError(f"TRANSITION_UNSUPPORTED: {exc}") from exc
                if "[IN]" in tflt and "[OUT]" in tflt:
                    parts.append(tflt.replace("[IN]", f"[{cur}]")
                                     .replace("[OUT]", f"[v{step}]"))
                else:
                    parts.append(f"[{cur}]{tflt}[v{step}]")
                cur = f"v{step}"
            elif kind == "mask":
                flt = _fx.mask_alpha(ov.get("mask") or ov)
                if flt:
                    parts.append(f"[{cur}]format=rgba,{flt}[v{step}]")
                    cur = f"v{step}"
            else:
                raise PipelineError(
                    f"OVERLAY_UNSUPPORTED: loai '{kind}' khong duoc ho tro; "
                    "local engine ho tro 'box' + 'logo' + 'text' + 'blur' + "
                    "'effect' (gồm glow/chroma_key) + 'color' + 'transform' + "
                    "'transition' (fade/wipe/circle/slide mo dau clip) + 'mask' "
                    "(chroma = bg-remove bang chroma key that).")
            step += 1
        parts.append(f"[{cur}]null[vout]")
        return ";".join(parts)

    @staticmethod
    def _px_even(v: float, size: int) -> int:
        return max(0, int(round(v * size)) // 2 * 2)


def freeze_frame(video_path: str, at: float, duration: float, out: Path) -> str:
    """Dung 1 frame tai `at` (giay) thanh clip tinh dai `duration` giay.

    Helper cho freeze_clip sau nay: grab 1 frame PNG roi loop thanh video.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PipelineError("FFMPEG_MISSING: khong dung duoc freeze_frame.")
    at, duration = max(0.0, float(at)), max(0.1, float(duration))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame = out.parent / f".{out.stem}.frame.png"
    try:
        grab = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", str(video_path),
             "-frames:v", "1", str(frame)],
            capture_output=True, text=True, timeout=300)
        if grab.returncode or not frame.is_file():
            raise PipelineError(f"FREEZE_FAILED: {grab.stderr[-300:]}")
        loop = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-loop", "1", "-framerate", "30",
             "-i", str(frame), "-t", f"{duration:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
             str(out)],
            capture_output=True, text=True, timeout=300)
        if loop.returncode or not out.is_file():
            raise PipelineError(f"FREEZE_FAILED: {loop.stderr[-300:]}")
        return str(out)
    finally:
        try:
            if frame.is_file():
                frame.unlink()
        except OSError:
            pass


def _escape_sub(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


# ----------------------------------------------------------------- pipeline --
class Pipeline:
    """8-step dub pipeline with cache/invalidation (A: pipeline.py:415-448)."""

    def __init__(self, root: str | Path, engine: LocalEngine | None = None,
                 retry_delays: tuple = (0.1, 0.2, 0.4), max_attempts: int = 3):
        self.root = Path(root)
        self.cache_dir = self.root / "cache"
        self.output_dir = self.root / "output"
        self.temp_dir = self.root / "temp"
        for directory in (self.cache_dir, self.output_dir, self.temp_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.engine = engine or LocalEngine()
        self.retry_delays = retry_delays
        self.max_attempts = max_attempts
        self._cancel_ids: set[str] = set()
        self._cancel_guard = threading.Lock()

    def request_cancel(self, video_id: str) -> None:
        with self._cancel_guard:
            self._cancel_ids.add(video_id)

    def clear_cancel(self, video_id: str) -> None:
        with self._cancel_guard:
            self._cancel_ids.discard(video_id)

    def _check_cancel(self, video_id: str) -> None:
        with self._cancel_guard:
            if video_id in self._cancel_ids:
                raise PipelineCancelled(f"Pipeline {video_id} bi huy bo.")

    # ---- project.json (A: pipeline.py:83-103) ----
    def _project_path(self, video_id: str) -> Path:
        self._check_video_id(video_id)
        return self.cache_dir / video_id / "project.json"

    @staticmethod
    def _check_video_id(video_id: str) -> None:
        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", video_id):
            raise _conflict("Ma video khong hop le.")

    def _work_dir(self, video_id: str) -> Path:
        self._check_video_id(video_id)
        work = self.cache_dir / video_id
        if not work.resolve().parent == self.cache_dir.resolve():
            raise _conflict("Duong dan du an khong hop le.")
        work.mkdir(parents=True, exist_ok=True)
        return work

    def load_project(self, video_id: str) -> dict:
        path = self._project_path(video_id)
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
        return {}

    def save_project(self, video_id: str, expected_signature: str | None = None,
                       **fields) -> dict:
        # T4: tu choi publish output khi timeline doi giua render (port A
        # _run_render stale-check). _step_render truyen expected_signature
        # chup truoc render; neu timeline hien tai khac -> 409, khong ghi.
        if ("output" in fields and fields["output"] is not None
                and expected_signature is not None
                and expected_signature != self.timeline_signature(video_id)):
            raise PipelineConflict(
                "CHECKPOINT_STALE: timeline doi trong luc render; "
                "output cu bi tu choi, hay render lai ban hien tai.")
        proj = self.load_project(video_id)
        proj.setdefault("video_id", video_id)
        proj.setdefault("steps_done", [])
        proj.setdefault("overlays", [])
        proj.setdefault("output_settings", {})
        for key, value in fields.items():
            if value is not None:
                proj[key] = value
        atomic_write_json(self._project_path(video_id), proj)
        return proj

    # ---- _mark_step: rebuild upstream ALWAYS invalidates downstream
    #      (A: pipeline.py:105-120) ----
    def _mark_step(self, video_id: str, step: str, input_hash=None, data=None) -> None:
        work = self._work_dir(video_id)
        downstream = STEPS[STEPS.index(step) + 1:]
        for later in downstream:
            for marker in work.glob(f"{later}*.done"):
                marker.unlink()
        for marker in work.glob(f"{step}.*.done"):
            if marker != done_path(work, step, input_hash):
                marker.unlink()
        marker = done_path(work, step, input_hash)
        if data is None:
            marker.touch()
        else:
            atomic_write_json(marker, data)
        proj = self.load_project(video_id)
        done = [s for s in proj.get("steps_done", []) if s not in downstream]
        if step not in done:
            done.append(step)
        self.save_project(video_id, steps_done=done)

    def _current(self, video_id: str, step: str, sig: str, files=()) -> bool:
        marker = done_path(self._work_dir(video_id), step)
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            return data.get("signature") == sig and all(Path(f).is_file() for f in files)
        except (OSError, ValueError, AttributeError):
            return False

    # ---- find video_id (A: pipeline.py:123-133) ----
    def resolve_video_id(self, source: str) -> str:
        """Stable id for a source before download: local-<hash> if file exists,
        else existing project id, else pending-<hash> (A: _find_video_id)."""
        found = self._find_video_id(source)
        if found is not None:
            return found
        return "pending-" + hash_text(source)

    @staticmethod
    def hash_file_static(path) -> str:
        return hash_file(path)

    def _find_video_id(self, source: str) -> str | None:
        local = Path(source)
        if local.is_file():
            return "local-" + hash_file(local)
        for proj in sorted(self.cache_dir.glob("*/project.json")):
            try:
                if json.loads(proj.read_text(encoding="utf-8")).get("source") == source:
                    return proj.parent.name
            except (OSError, ValueError):
                continue
        return None

    def _find_video_file(self, video_id: str) -> Path | None:
        vids = [f for f in (self._work_dir(video_id)).glob("*.*")
                if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".m4v")]
        return max(vids, key=lambda f: f.stat().st_size) if vids else None

    def _load_segments(self, video_id: str) -> list[dict]:
        return json.loads((self._work_dir(video_id) / "segments.json").read_text(encoding="utf-8"))

    def _save_segments(self, video_id: str, segments: list[dict]) -> None:
        work = self._work_dir(video_id)
        atomic_write_json(work / "segments.json", segments)
        if any(s.get("tgt_text") for s in segments):
            work.joinpath("dub.srt").write_text(
                srt_from_segments(segments), encoding="utf-8")

    @staticmethod
    def _pipeline_error_transient(exc: "PipelineError") -> bool:
        """T3: PipelineError mang ma TRANSIENT thi duoc retry (port A
        failure(..., transient=...)). Truoc day _guarded chi bat
        (OSError, TimeoutError, ConnectionError) nen moi loi pipeline
        chuan khong bao gio retry du thuoc nhom TRANSIENT."""
        message = str(exc)
        match = _PIPELINE_CODE_RE.match(message.strip())
        if match and match.group(1) in PIPELINE_TRANSIENT_CODES:
            return True
        cause = exc.__cause__
        return isinstance(cause, TRANSIENT_ERRORS)

    # ---- retry wrapper (B: execution_policy failure/recover) ----
    def _guarded(self, step: str, func, *args, **kwargs):
        attempts = self.max_attempts if step in IDEMPOTENT_RETRY_STEPS else 1
        last: Exception | None = None
        for trial in range(attempts):
            try:
                return func(*args, **kwargs)
            except TRANSIENT_ERRORS as exc:
                last = exc
                if trial < attempts - 1:
                    time.sleep(self.retry_delays[min(trial, len(self.retry_delays) - 1)])
            except PipelineError as exc:
                last = exc
                if step in IDEMPOTENT_RETRY_STEPS and self._pipeline_error_transient(exc) \
                        and trial < attempts - 1:
                    time.sleep(self.retry_delays[min(trial, len(self.retry_delays) - 1)])
                    continue
                raise
        raise PipelineError(f"Buoc {step} loi: {last}") from last

    def timeline_signature(self, video_id: str) -> str:
        """Chu ky timeline hien tai (segments + overlays + output-settings).
        T4: chup truoc render, so lai sau render de phat hien timeline doi
        giua chung (port A _run_render stale-check)."""
        try:
            segments = self._load_segments(video_id)
        except (OSError, ValueError):
            segments = []
        proj = self.load_project(video_id)
        return signature_of({
            "segments": segments,
            "overlays": proj.get("overlays", []),
            "output_settings": proj.get("output_settings", {}),
        })

    # ---- 8 steps (A: pipeline.py:136-389) ----
    def _step_download(self, ctx, source, progress_cb=None, src_lang=None,
                       tgt_lang=None, default_voice=None, **_):
        vid = ctx["video_id"]
        ih = hash_text(source)
        if ctx["force"] or not done_path(self._work_dir(vid), "download", ih).is_file():
            info = self._guarded("download", self.engine.download, source,
                                 self._work_dir(vid), progress_cb)
            ctx["video_id"] = vid = info["video_id"]
            ctx["video_path"] = info["path"]
            ctx["duration"] = info.get("duration") or 0
            self.save_project(vid, source=source, title=info.get("title", ""),
                              src_lang=src_lang, tgt_lang=tgt_lang,
                              default_voice=default_voice)
            self._mark_step(vid, "download", ih)
            ctx["ran"].append("download")
        else:
            ctx["video_path"] = str(self._find_video_file(vid) or source)
        self.save_project(vid, src_lang=src_lang, tgt_lang=tgt_lang,
                          default_voice=default_voice)

    def _step_audio(self, ctx, **_):
        vid = ctx["video_id"]
        ih = hash_file(ctx["video_path"])
        work = self._work_dir(vid)
        if ctx["force"] or not done_path(work, "audio", ih).is_file() or not all(
                (work / name).is_file() for name in ("stt.wav", "orig.wav")):
            out = self._guarded("audio", self.engine.extract_audio,
                                ctx["video_path"], work)
            ctx["stt_wav"], ctx["orig_wav"] = out["stt_wav"], out["orig_wav"]
            self._mark_step(vid, "audio", ih)
            ctx["ran"].append("audio")
        else:
            ctx["stt_wav"] = str(work / "stt.wav")
            ctx["orig_wav"] = str(work / "orig.wav")

    def _step_stt(self, ctx, src_lang=None, words=None, **_):
        vid = ctx["video_id"]
        want_words = bool(words if words is not None else ctx.get("words", False))
        ih = signature_of([hash_file(ctx["stt_wav"]), src_lang, want_words])
        work = self._work_dir(vid)
        if ctx["force"] or not done_path(work, "stt", ih).is_file() or not (
                work / "segments.json").is_file():
            segments = self._guarded("stt", self.engine.transcribe, vid,
                                     ctx["stt_wav"], work, src_lang or "auto",
                                     ctx.get("progress_cb"), want_words)
            ctx["segments"] = segments
            self._save_segments(vid, segments)
            self._mark_step(vid, "stt", ih)
            ctx["ran"].append("stt")
        else:
            ctx["segments"] = self._load_segments(vid)

    def _step_translate(self, ctx, src_lang="auto", tgt_lang="vi", **_):
        vid = ctx["video_id"]
        segments = ctx["segments"]
        src = src_lang or "auto"
        cfg = {"src": src, "tgt": tgt_lang}
        ih = signature_of([[s.get("src_text") for s in segments], src, tgt_lang, cfg])
        if ctx["force"] or not done_path(self._work_dir(vid), "translate", ih).is_file():
            segments = self._guarded("translate", self.engine.translate,
                                     segments, src, tgt_lang)
            ctx["segments"] = segments
            self._save_segments(vid, segments)
            self._mark_step(vid, "translate", ih)
            ctx["ran"].append("translate")
        else:
            ctx["segments"] = self._load_segments(vid)

    def _step_tts(self, ctx, tgt_lang="vi", default_voice=None, **_):
        vid = ctx["video_id"]
        sig = signature_of([tgt_lang, default_voice,
                            [(s["id"], s.get("tgt_text")) for s in ctx["segments"]]])
        files = [s.get("tts_path") or "" for s in ctx["segments"]
                 if (s.get("tgt_text") or "").strip()]
        if ctx["force"] or not self._current(vid, "tts", sig, files):
            tts_dir = self._work_dir(vid) / "tts"
            tts_dir.mkdir(parents=True, exist_ok=True)
            for seg in ctx["segments"]:
                text = (seg.get("tgt_text") or "").strip()
                if not text:
                    continue
                voice = seg.get("voice_id") or default_voice
                if not voice:
                    raise PipelineError(
                        f"Cau {seg['id']} chua co giong doc. Chon giong mac dinh.")
                slot = max(0.3, seg["end"] - seg["start"])
                natural = max(0.3, len(text) / 12.0)
                out = tts_dir / f"{seg['id']}_{hash_text(text + voice)}.wav"
                if not out.is_file():
                    self._guarded("tts", self.engine.synthesize, text, voice, out, natural)
                seg["tts_path"] = str(out)
                seg["tts_duration"] = self.engine.wav_duration(out)
                seg["tts_slot"] = slot
            self._save_segments(vid, ctx["segments"])
            self._mark_step(vid, "tts", data={"signature": sig})
            ctx["ran"].append("tts")

    def _step_sync(self, ctx, **_):
        vid = ctx["video_id"]
        max_speed = 1.25
        sig = signature_of([ctx["segments"], max_speed])
        work = self._work_dir(vid)
        if ctx["force"] or not self._current(vid, "sync", sig, [work / "timeline.json"]):
            timeline = []
            for seg in ctx["segments"]:
                dur = float(seg.get("tts_duration") or 0.0)
                slot = max(0.3, seg["end"] - seg["start"])
                speed = min(dur / slot, max_speed) if slot > 0 else 1.0
                if dur > slot * max_speed:
                    seg["flags"] = sorted(set(seg.get("flags", [])) | {"too_long"})
                timeline.append({"seg_id": seg["id"], "start": seg["start"],
                                 "duration": dur, "speed": round(speed, 3),
                                 "tts_path": seg.get("tts_path")})
            self._save_segments(vid, ctx["segments"])
            atomic_write_json(work / "timeline.json",
                              {"timeline": timeline, "signature": sig})
            ctx["timeline"] = timeline
            self._mark_step(vid, "sync", data={"signature": sig})
            ctx["ran"].append("sync")
        else:
            ctx["timeline"] = json.loads(
                (work / "timeline.json").read_text(encoding="utf-8"))["timeline"]

    def _step_mix(self, ctx, **_):
        vid = ctx["video_id"]
        sig = signature_of([ctx["timeline"], hash_file(ctx["orig_wav"])])
        work = self._work_dir(vid)
        if ctx["force"] or not self._current(vid, "mix", sig, [work / "mix.wav"]):
            total = max([e["start"] + e["duration"] for e in ctx["timeline"]] + [1.0])
            try:
                total = max(total, self.engine.probe_duration(ctx["orig_wav"]))
            except PipelineError:
                pass
            bed = self._guarded("mix", self.engine.mix, ctx["timeline"],
                                work / "tts", ctx["orig_wav"], total)
            with wave.open(str(work / "mix.wav"), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(LocalEngine.SAMPLE_RATE)
                wav.writeframes(bed.tobytes())
            ctx["mix_wav"] = str(work / "mix.wav")
            self._mark_step(vid, "mix", data={"signature": sig})
            ctx["ran"].append("mix")
        else:
            ctx["mix_wav"] = str(work / "mix.wav")

    def _step_render(self, ctx, overlays=None, burn_subtitles=False, **_):
        vid = ctx["video_id"]
        # T4: chup signature timeline truoc render (port A _run_render). Sau
        # ffmpeg, neu timeline doi -> khong publish output cu, danh stale.
        pre_signature = self.timeline_signature(vid)
        old_output = self.load_project(vid).get("output")
        srt = self._work_dir(vid) / "dub.srt"
        sig = signature_of([hash_file(ctx["video_path"]),
                            hash_file(ctx["mix_wav"]) if ctx.get("mix_wav") else None,
                            overlays or [], burn_subtitles,
                            hash_file(srt) if burn_subtitles and srt.is_file() else None])
        if ctx["force"] or not self._current(vid, "render", sig, [old_output or ""]):
            import datetime
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = self.output_dir / f"{vid}_dubbed_{stamp}.mp4"
            result = self._guarded(
                "render", self.engine.render_video, ctx["video_path"],
                ctx.get("mix_wav"), out_path, overlays or [],
                str(srt) if (burn_subtitles and srt.is_file()) else None)
            ctx["output"] = result
            self._mark_step(vid, "render", data={"signature": sig})
            try:
                self.save_project(vid, output=result, overlays=overlays or [],
                                  output_settings={"burn_subtitles": burn_subtitles},
                                  editor_export={}, editor_pending=False,
                                  expected_signature=pre_signature)
            except PipelineConflict as exc:
                ctx["output"] = None
                ctx["stale"] = True
                ctx["stale_error"] = str(exc)
                return
            ctx["ran"].append("render")
        else:
            ctx["output"] = self.load_project(vid).get("output")

    # ---- hydrate (A: pipeline.py:392-412) ----
    def _hydrate(self, ctx: dict) -> None:
        vid = ctx["video_id"]
        work = self._work_dir(vid)
        found = self._find_video_file(vid)
        if found is None:
            src = self.load_project(vid).get("source") or ctx.get("source")
            if src and Path(src).is_file():
                found = Path(src)
        if found:
            ctx.setdefault("video_path", str(found))
        for key, name in (("stt_wav", "stt.wav"), ("orig_wav", "orig.wav"),
                          ("mix_wav", "mix.wav")):
            candidate = work / name
            if candidate.exists():
                ctx.setdefault(key, str(candidate))
        if (work / "segments.json").exists():
            ctx.setdefault("segments", self._load_segments(vid))
        if (work / "timeline.json").exists():
            data = json.loads((work / "timeline.json").read_text(encoding="utf-8"))
            ctx.setdefault("timeline", data["timeline"])

    # ---- run (A: pipeline.py:415-448) ----
    def run(self, source, src_lang="auto", tgt_lang="vi", default_voice=None,
            steps=None, progress_cb=None, overlays=None,
            burn_subtitles=False, words: bool = False) -> dict:
        vid = self._find_video_id(source)
        if vid is None:
            vid = "pending-" + hash_text(source)
        ctx = {"video_id": vid, "ran": [], "force": False,
                "progress_cb": progress_cb, "output": None, "source": source,
                "words": bool(words)}
        requested = set(steps) if steps else None
        if requested:
            self._hydrate(ctx)
        total = len(STEPS)
        try:
            for i, step in enumerate(STEPS):
                if requested is not None and step not in requested:
                    continue
                self._check_cancel(ctx["video_id"])
                if progress_cb:
                    progress_cb(i / total * 100)
                try:
                    getattr(self, f"_step_{step}")(
                        ctx, source=source, src_lang=src_lang, tgt_lang=tgt_lang,
                        default_voice=default_voice, overlays=overlays,
                        burn_subtitles=burn_subtitles, words=words)
                except KeyboardInterrupt:
                    raise
                except PipelineError:
                    raise
                except Exception as exc:
                    raise PipelineError(f"Buoc {step} loi: {exc}") from exc
                vid = ctx["video_id"]
            if progress_cb:
                progress_cb(100)
        except KeyboardInterrupt:
            raise
        if ctx.get("output") is None and not ctx.get("stale"):
            proj = self.load_project(ctx["video_id"])
            if proj.get("output"):
                ctx["output"] = proj["output"]
        result: dict = {"video_id": ctx["video_id"], "steps_run": ctx["ran"],
                "output": ctx.get("output"), "segments": ctx.get("segments")}
        if ctx.get("stale"):
            result["status"] = "stale"
            result["error"] = {"code": "CHECKPOINT_STALE",
                               "message": ctx.get("stale_error") or
                               "Timeline doi trong luc render."}
        return result

    # ---- revoice one sentence (A: pipeline.py:451-482) ----
    def revoice_segment(self, video_id, seg_id, new_text=None, new_voice=None,
                        progress_cb=None):
        proj = self.load_project(video_id)
        if not proj:
            raise PipelineError(f"Khong tim thay project cho video '{video_id}'.")
        segments = self._load_segments(video_id)
        seg = next((s for s in segments if s["id"] == seg_id), None)
        if seg is None:
            raise PipelineError(f"Khong co cau so {seg_id} trong video nay.")
        if new_text is not None:
            seg["tgt_text"] = new_text
            seg["flags"] = [f for f in seg.get("flags", []) if f != "too_long"]
        if new_voice is not None:
            seg["voice_id"] = new_voice
        self._save_segments(video_id, segments)
        work = self._work_dir(video_id)
        for step in ("tts", "sync", "mix", "render"):
            marker = done_path(work, step)
            if marker.exists():
                marker.unlink()
        for old in (work / "tts").glob(f"{seg_id}_*.wav"):
            old.unlink()
        proj["steps_done"] = [s for s in proj.get("steps_done", [])
                              if s not in ("tts", "sync", "mix", "render")]
        self.save_project(video_id, steps_done=proj["steps_done"])
        return self.run(proj["source"], src_lang=proj.get("src_lang", "auto"),
                        tgt_lang=proj.get("tgt_lang", "vi"),
                        default_voice=proj.get("default_voice"),
                        steps=["tts", "sync", "mix", "render"],
                        progress_cb=progress_cb,
                        overlays=proj.get("overlays"),
                        burn_subtitles=proj.get("output_settings", {}).get(
                            "burn_subtitles", False))

    # ---- subtitle edit: invalidate from tts (A app.py:106-123) ----
    def edit_subtitles(self, video_id: str, rows: list) -> list[dict]:
        segments = self._load_segments(video_id)
        for row, seg in zip(rows, segments):
            seg["tgt_text"] = str(row[4] if len(row) > 4 else "").strip()
        self._save_segments(video_id, segments)
        work = self._work_dir(video_id)
        for step in ("tts", "sync", "mix", "render"):
            marker = done_path(work, step)
            if marker.exists():
                marker.unlink()
        proj = self.load_project(video_id)
        proj["steps_done"] = [s for s in proj.get("steps_done", [])
                              if s not in ("tts", "sync", "mix", "render")]
        self.save_project(video_id, steps_done=proj["steps_done"])
        return segments

    # ---- overlay edit: invalidate render ONLY (A app.py:195-209) ----
    def add_overlay(self, video_id: str, overlay: dict) -> int:
        proj = self.load_project(video_id)
        overlays = proj.get("overlays", [])
        overlays.append(overlay)
        self.save_project(video_id, overlays=overlays)
        marker = done_path(self._work_dir(video_id), "render")
        if marker.exists():
            marker.unlink()
        return len(overlays)


def srt_from_segments(segments: list[dict]) -> str:
    def stamp(value: float) -> str:
        ms = int(round(value * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(segments, 1):
        text = (seg.get("tgt_text") or seg.get("src_text") or "").strip()
        lines.append(f"{i}\n{stamp(seg['start'])} --> {stamp(seg['end'])}\n{text}\n")
    return "\n".join(lines).strip() + "\n" if lines else ""
