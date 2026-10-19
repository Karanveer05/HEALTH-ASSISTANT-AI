"""LLM access through plain HTTPS (Gemini first, Groq as backup).

Every call asks for JSON and validates it against a Pydantic model. If no key is set, the call fails,
or the JSON stays invalid after one retry, it returns None and the caller uses its rule-based fallback.
"""
import base64
import json
import logging
import time

import httpx
from pydantic import BaseModel, ValidationError

from .config import get_settings

log = logging.getLogger("llm")

SAFETY_RULES = (
    "You are a medical information assistant inside a decision-support app for patients in India. "
    "You never give a definitive diagnosis and never prescribe. You state uncertainty clearly. "
    "Use only the patient data and reference passages given to you; do not invent lab values, findings or sources. "
    "Reply with a single JSON object only, no markdown."
)


def providers() -> list[str]:
    s = get_settings()
    if s.llm_provider == "offline":
        return []
    order = {"gemini": ["gemini", "groq"], "groq": ["groq", "gemini"]}.get(s.llm_provider, ["gemini", "groq"])
    keys = {"gemini": s.gemini_api_key, "groq": s.groq_api_key}
    return [p for p in order if keys[p]]


def active_provider() -> str:
    p = providers()
    return p[0] if p else "offline"


def _gemini(system: str, prompt: str, images: list[tuple[bytes, str]] | None) -> str:
    s = get_settings()
    parts = [{"text": prompt}]
    for data, mime in images or []:
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    # Busy (503/429) or retired (404) models are common on the free tier: retry once, then try the next model.
    models = [s.gemini_model] + [m.strip() for m in s.gemini_fallback_models.split(",") if m.strip() and m.strip() != s.gemini_model]
    last = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            r = httpx.post(url, json=body, headers={"x-goog-api-key": s.gemini_api_key}, timeout=s.llm_timeout)
            if r.status_code == 200:
                parts = r.json()["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts if not p.get("thought"))
            last = r
            if r.status_code in (429, 500, 503) and attempt == 0:
                time.sleep(1.5)
                continue
            break
        log.info("gemini model %s unavailable (%s), trying next", model, last.status_code)
    last.raise_for_status()
    raise RuntimeError("no Gemini model answered")


def _groq(system: str, prompt: str, images) -> str:
    if images:
        raise RuntimeError("Groq text model cannot read images")
    s = get_settings()
    body = {
        "model": s.groq_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                   headers={"Authorization": f"Bearer {s.groq_api_key}"}, timeout=s.llm_timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


_CALLERS = {"gemini": _gemini, "groq": _groq}


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t


def generate(model: type[BaseModel], task: str, data: dict | str, images=None, system: str = SAFETY_RULES):
    """Ask the LLM for `model`-shaped JSON. Returns a validated model instance or None."""
    schema = json.dumps(model.model_json_schema())
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
    prompt = f"{task}\n\nReturn JSON matching this JSON Schema:\n{schema}\n\nDATA:\n{payload}"
    for provider in providers():
        attempt_prompt = prompt
        for attempt in range(2):
            try:
                raw = _CALLERS[provider](system, attempt_prompt, images)
                return model.model_validate_json(_strip_fences(raw))
            except ValidationError as e:
                log.warning("%s returned invalid JSON (attempt %d): %s", provider, attempt + 1, e.errors()[:3])
                attempt_prompt = f"{prompt}\n\nYour previous reply was invalid: {str(e)[:800]}\nFix it and return only valid JSON."
            except Exception as e:  # network, quota, bad key: try the next provider
                log.warning("%s call failed: %s", provider, e)
                break
    return None
