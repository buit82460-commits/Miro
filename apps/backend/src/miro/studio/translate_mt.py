# -*- coding: utf-8 -*-
"""Dich may that cho Studio pipeline C (port A: core/llm_translate.py + core/translate.py).

Hai backend, goi lazy de khong vo pipeline khi thieu key/model/lib:
- LLM API (OpenAI-compatible / Anthropic): doc tu env LLM_API_ENDPOINT /
  LLM_API_KEY / LLM_MODEL / LLM_PROVIDER. Loi -> RuntimeError.
- NLLB-600M ctranslate2 int8 local: model_dir tu env MIRO_NLLB_MODEL hoac
  C:/Miro/models/nllb-600m-ct2. Thieu lib/model -> RuntimeError.

Chi stdlib + requests/urllib + ctranslate2/transformers (lazy import).
Khong commit key/model vao code.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

LANG = {"vi": "vie_Latn", "en": "eng_Latn", "zh": "zho_Hans"}
_LANG_NAME = {"vi": "Vietnamese", "en": "English", "zh": "Chinese"}

_DEFAULT_NLLB_MODEL = "C:/Miro/models/nllb-600m-ct2"


def default_nllb_dirs() -> tuple[str, str]:
    """(model_dir, tokenizer_dir) tu env, fallback duong dan mac dinh."""
    model_dir = os.environ.get("MIRO_NLLB_MODEL", _DEFAULT_NLLB_MODEL)
    tokenizer_dir = os.environ.get("MIRO_NLLB_TOKENIZER", model_dir)
    return model_dir, tokenizer_dir


def translate_batch_llm(items: list[str], src: str, tgt: str,
                        endpoint: str | None = None,
                        api_key: str | None = None,
                        model: str | None = None,
                        provider: str | None = None) -> list[str]:
    """Dich 1 lo qua LLM chat completions, ep JSON array cung thu tu.

    Raises RuntimeError khi thieu cau hinh, loi mang, hoac parse that bai.
    """
    endpoint = endpoint or os.environ.get("LLM_API_ENDPOINT", "")
    api_key = api_key or os.environ.get("LLM_API_KEY", "")
    model = model or os.environ.get("LLM_MODEL", "")
    provider = (provider or os.environ.get("LLM_PROVIDER", "")
                or "openai").strip() or "openai"
    if not (api_key and model and (endpoint or provider == "anthropic")):
        raise RuntimeError(
            "LLM chua cau hinh: can LLM_API_KEY + LLM_MODEL + "
            "(LLM_API_ENDPOINT hoac LLM_PROVIDER=anthropic).")
    if tgt not in _LANG_NAME:
        raise RuntimeError(f"LLM chua ho tro dich sang '{tgt}'.")
    lang_name = _LANG_NAME[tgt]
    lines = [f"[{i}] {t}" for i, t in enumerate(items)]
    system = (
        f"You translate for timed dubbing into {lang_name}. "
        f"Keep the full meaning, keep each line short enough for dubbing. "
        f"Return ONLY a JSON array of translated strings, same order, no labels.")
    user = "\n".join(lines)
    raw = _chat(endpoint, api_key, model, provider, system, user)
    arr = _extract_json_array(raw, len(items))
    if arr is None:
        raise RuntimeError(f"LLM tra ve khong parse duoc: {raw[:200]}")
    return arr


def _chat(endpoint: str, api_key: str, model: str, provider: str,
          system: str, user: str, timeout: int = 120) -> str:
    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        payload: dict = {"model": model, "max_tokens": 2048,
                         "system": system,
                         "messages": [{"role": "user", "content": user}]}
        headers = {"content-type": "application/json",
                   "x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:
        url = endpoint.rstrip("/") + "/chat/completions"
        payload = {"model": model, "max_tokens": 2048,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        headers = {"content-type": "application/json",
                   "authorization": f"Bearer {api_key}"}
    body = json.dumps(payload).encode("utf-8")
    try:
        import requests  # type: ignore
    except ImportError:
        requests = None  # type: ignore
    try:
        if requests is not None:
            resp = requests.post(url, content=body, headers=headers,
                                 timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
        else:
            import urllib.request
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                data = json.loads(fh.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"LLM API loi: {exc}") from exc
    try:
        if provider == "anthropic":
            return "".join(b.get("text", "") for b in data.get("content", []))
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise RuntimeError(f"LLM tra ve sai dinh dang: {exc}") from exc


def _extract_json_array(raw: str, want: int) -> list[str] | None:
    try:
        arr = json.loads(raw)
        if isinstance(arr, list) and len(arr) == want:
            return [str(x).strip() for x in arr]
    except (ValueError, TypeError):
        pass
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            arr = json.loads(match.group())
            if isinstance(arr, list) and len(arr) == want:
                return [str(x).strip() for x in arr]
        except (ValueError, TypeError):
            return None
    return None


def translate_batch_nllb(items: list[str], src: str, tgt: str,
                         model_dir: str | None = None,
                         tokenizer_dir: str | None = None) -> list[str]:
    """Dich 1 lo qua NLLB ctranslate2 int8 local (port A core/translate.py).

    Raises RuntimeError khi thieu lib/model.
    """
    default_model, default_tok = default_nllb_dirs()
    model_dir = model_dir or default_model
    tokenizer_dir = tokenizer_dir or default_tok or model_dir
    if src not in LANG or tgt not in LANG:
        raise RuntimeError(f"NLLB chua ho tro cap '{src}'->'{tgt}'.")
    if not Path(str(model_dir)).is_dir():
        raise RuntimeError(
            f"NLLB model khong tim thay: {model_dir} "
            f"(dat MIRO_NLLB_MODEL hoac copy model vao day).")
    try:
        import ctranslate2  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Thieu ctranslate2 (pip install ctranslate2).") from exc
    try:
        from transformers import AutoTokenizer  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Thieu transformers (pip install transformers).") from exc
    try:
        translator = ctranslate2.Translator(str(model_dir), device="cpu",
                                            compute_type="int8")
    except Exception as exc:
        raise RuntimeError(f"Khong nap duoc model NLLB: {exc}") from exc
    try:
        tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_dir),
                                                  local_files_only=True)
    except Exception as exc:
        raise RuntimeError(
            f"Khong nap duoc tokenizer NLLB: {exc}") from exc
    src_lang, tgt_lang = LANG[src], LANG[tgt]
    results: list[str | None] = [None] * len(items)
    todo = [i for i, t in enumerate(items) if (t or "").strip()]
    batch = 16
    try:
        for lo in range(0, len(todo), batch):
            idxs = todo[lo:lo + batch]
            tokenizer.src_lang = src_lang
            tokens = [tokenizer.convert_ids_to_tokens(tokenizer.encode(items[i]))
                      for i in idxs]
            hyps = translator.translate_batch(
                tokens, target_prefix=[[tgt_lang]] * len(tokens),
                beam_size=4, max_decoding_length=128)
            for i, res in zip(idxs, hyps):
                hyp = res.hypotheses[0]
                if hyp and hyp[0] == tgt_lang:
                    hyp = hyp[1:]
                results[i] = tokenizer.decode(
                    tokenizer.convert_tokens_to_ids(hyp),
                    skip_special_tokens=True).strip()
    except Exception as exc:
        raise RuntimeError(f"NLLB dich loi: {exc}") from exc
    for i, t in enumerate(items):
        if results[i] is None:
            results[i] = "" if (t or "").strip() else ""
    return [str(x or "") for x in results]
