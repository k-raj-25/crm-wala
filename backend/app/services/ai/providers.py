"""LLM provider abstraction. Each workspace brings its own key (see settings.py); the CRM code never imports a vendor SDK.

`mock` is a deterministic, data-driven provider (no external calls): it routes questions to the same CRM tools a real
model would call and renders the answer. It keeps the product fully functional in dev, demos and tests.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

import httpx
from flask import current_app, g

from app.core.errors import ApiError

log = logging.getLogger("app.ai")
ToolRunner = Callable[[str, dict], dict]


@dataclass
class AIResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    sources: list[dict] = field(default_factory=list)
    model: str | None = None
    charts: list[dict] = field(default_factory=list)
    provider: str = ""


class AIProvider(Protocol):
    name: str

    def complete(self, kind: str, system: str, prompt: str, context: dict, images: list[dict] | None = None, max_tokens: int = 900) -> AIResult: ...
    def json(self, kind: str, system: str, prompt: str, context: dict, images: list[dict] | None = None, max_tokens: int = 1500) -> tuple[dict, AIResult]: ...
    def chat(self, system: str, history: list[dict], tools: list[dict], run_tool: ToolRunner, max_steps: int = 5) -> AIResult: ...


def _parse_json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or code fences; take the outermost object."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else {"items": v}
    except ValueError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a != -1 and b > a:
        try:
            return json.loads(t[a:b + 1])
        except ValueError:
            pass
    raise ApiError(502, "ai_bad_output", "The AI returned something we couldn't read. Please try again.")


def _provider_message(r: httpx.Response) -> str:
    """The provider's own explanation, e.g. "Your credit balance is too low…"."""
    try:
        body = r.json()
    except ValueError:
        return ""
    if isinstance(body, list) and body:  # Gemini wraps errors in a list
        body = body[0]
    err = body.get("error") if isinstance(body, dict) else None
    msg = err.get("message") if isinstance(err, dict) else err if isinstance(err, str) else None
    return str(msg or "").strip()[:240]


def _fail(provider: str, r: httpx.Response) -> None:
    log.error("%s error %s: %s", provider, r.status_code, r.text[:300])
    detail = _provider_message(r)
    low = detail.lower()
    if r.status_code in (401, 403):
        msg = "Your AI key was rejected by the provider. An admin can update it in Settings → AI assistant."
        _note_error(msg)
        raise ApiError(502, "ai_key_invalid", msg)
    if r.status_code in (402, 429) or any(w in low for w in ("credit balance", "billing", "quota", "insufficient")):
        msg = "Your AI provider says the key is out of credit or rate-limited. Check your plan with the provider, then try again."
        if detail:
            msg += f" (Provider said: {detail})"
        _note_error(msg)
        raise ApiError(502, "ai_quota", msg)
    if r.status_code == 404 or "model" in low and any(w in low for w in ("not found", "does not exist", "not available", "invalid model", "not a valid model")):
        raise ApiError(502, "ai_model_missing", "The AI model set in Settings → AI assistant isn't available on your key. Pick another model."
                       + (f" (Provider said: {detail})" if detail else ""))
    if 400 <= r.status_code < 500:
        msg = "Your AI provider refused the request" + (f": {detail}" if detail else ".")
        _note_error(msg)
        raise ApiError(502, "ai_request_rejected", msg)
    raise ApiError(502, "ai_provider_error", "The AI service is temporarily unavailable. Please try again.")


def _note_error(msg: str) -> None:
    try:
        from app.services.ai import settings as ai_settings

        if getattr(g, "workspace", None) is not None:
            ai_settings.mark_error(g.workspace.id, msg)
    except Exception:  # never mask the real error
        pass


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, key: str | None = None, model: str | None = None, timeout: float = 60) -> None:
        self.key = key or current_app.config["ANTHROPIC_API_KEY"]
        self.model = model or current_app.config["AI_MODEL"] or "claude-sonnet-5-5"
        self.timeout = timeout

    def _post(self, payload: dict) -> dict:
        try:
            r = httpx.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                           json=payload, timeout=self.timeout)
        except httpx.HTTPError:
            raise ApiError(502, "ai_provider_error", "Couldn't reach the AI service. Please try again.")
        if r.status_code >= 400:
            _fail("anthropic", r)
        return r.json()

    def _content(self, prompt: str, images: list[dict] | None):
        if not images:
            return prompt
        return [*({"type": "image", "source": {"type": "base64", "media_type": i["media_type"], "data": i["data"]}} for i in images), {"type": "text", "text": prompt}]

    def complete(self, kind, system, prompt, context, images=None, max_tokens=900):
        d = self._post({"model": self.model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": self._content(prompt, images)}]})
        return AIResult("".join(b.get("text", "") for b in d["content"]), d["usage"]["input_tokens"], d["usage"]["output_tokens"], model=self.model)

    def json(self, kind, system, prompt, context, images=None, max_tokens=1500):
        res = self.complete(kind, system + " Reply with a single JSON object only, no prose.", prompt, context, images, max_tokens)
        return _parse_json(res.text), res

    def chat(self, system, history, tools, run_tool, max_steps=6):
        msgs = [{"role": m["role"], "content": m["content"]} for m in history]
        tin = tout = 0
        sources: list[dict] = []
        charts: list[dict] = []
        for _ in range(max_steps):
            d = self._post({"model": self.model, "max_tokens": 1500, "system": system, "tools": tools, "messages": msgs})
            tin, tout = tin + d["usage"]["input_tokens"], tout + d["usage"]["output_tokens"]
            blocks = d["content"]
            if d.get("stop_reason") != "tool_use":
                return AIResult("".join(b.get("text", "") for b in blocks), tin, tout, sources, self.model, charts)
            msgs.append({"role": "assistant", "content": blocks})
            results = []
            for b in blocks:
                if b["type"] == "tool_use":
                    out = run_tool(b["name"], b["input"])
                    sources += _collect_sources(out)
                    charts += _collect_charts(out)
                    results.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(_for_model(out), default=str)[:12000]})
            msgs.append({"role": "user", "content": results})
        return AIResult("I couldn't finish that. Try a more specific question.", tin, tout, sources, self.model, charts)


class OpenAIProvider:
    """OpenAI's Chat Completions API, and the providers that speak it (Gemini's compatible endpoint, OpenRouter)."""
    name = "openai"

    def __init__(self, key: str | None = None, model: str | None = None, base_url: str = "https://api.openai.com/v1", name: str = "openai", timeout: float = 60) -> None:
        self.key = key or current_app.config["OPENAI_API_KEY"]
        self.model = model or current_app.config["AI_MODEL"] or "gpt-4.1"
        self.base_url, self.name, self.timeout = base_url.rstrip("/"), name, timeout

    def _post(self, payload: dict, path: str = "/chat/completions") -> dict:
        headers = {"Authorization": f"Bearer {self.key}"}
        if self.name == "openrouter":
            headers |= {"HTTP-Referer": "https://crmwala.com", "X-Title": "CRM Wala"}
        try:
            r = httpx.post(self.base_url + path, headers=headers, json=payload, timeout=self.timeout)
        except httpx.HTTPError:
            raise ApiError(502, "ai_provider_error", "Couldn't reach the AI service. Please try again.")
        if r.status_code >= 400:
            _fail(self.name, r)
        return r.json()

    def _limit(self, n: int) -> dict:
        # OpenAI's newer models reject max_tokens; the compatible providers don't all know max_completion_tokens.
        return {"max_completion_tokens": n} if self.name == "openai" else {"max_tokens": n}

    def _content(self, prompt: str, images: list[dict] | None):
        if not images:
            return prompt
        return [{"type": "text", "text": prompt}, *({"type": "image_url", "image_url": {"url": f"data:{i['media_type']};base64,{i['data']}"}} for i in images)]

    def complete(self, kind, system, prompt, context, images=None, max_tokens=900, json_mode=False):
        payload = {"model": self.model, **self._limit(max_tokens), "messages": [{"role": "system", "content": system}, {"role": "user", "content": self._content(prompt, images)}]}
        if json_mode and self.name == "openai":
            payload["response_format"] = {"type": "json_object"}
        d = self._post(payload)
        u = d.get("usage", {})
        return AIResult(d["choices"][0]["message"]["content"] or "", u.get("prompt_tokens", 0), u.get("completion_tokens", 0), model=self.model)

    def json(self, kind, system, prompt, context, images=None, max_tokens=1500):
        res = self.complete(kind, system + " Reply with a single JSON object only, no prose.", prompt, context, images, max_tokens, json_mode=True)
        return _parse_json(res.text), res

    def transcribe(self, audio: bytes, filename: str, mime: str) -> AIResult:
        try:
            r = httpx.post(self.base_url + "/audio/transcriptions", headers={"Authorization": f"Bearer {self.key}"}, data={"model": "whisper-1"},
                           files={"file": (filename, audio, mime)}, timeout=120)
        except httpx.HTTPError:
            raise ApiError(502, "ai_provider_error", "Couldn't reach the AI service. Please try again.")
        if r.status_code >= 400:
            _fail(self.name, r)
        return AIResult(r.json().get("text", ""), model="whisper-1")

    def chat(self, system, history, tools, run_tool, max_steps=6):
        msgs = [{"role": "system", "content": system}] + [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])} for m in history]
        oa_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools]
        tin = tout = 0
        sources: list[dict] = []
        charts: list[dict] = []
        for _ in range(max_steps):
            d = self._post({"model": self.model, "messages": msgs, "tools": oa_tools})
            u = d.get("usage", {})
            tin, tout = tin + u.get("prompt_tokens", 0), tout + u.get("completion_tokens", 0)
            m = d["choices"][0]["message"]
            if not m.get("tool_calls"):
                return AIResult(m.get("content") or "", tin, tout, sources, self.model, charts)
            msgs.append(m)
            for tc in m["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except ValueError:
                    args = {}
                out = run_tool(tc["function"]["name"], args)
                sources += _collect_sources(out)
                charts += _collect_charts(out)
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(_for_model(out), default=str)[:12000]})
        return AIResult("I couldn't finish that. Try a more specific question.", tin, tout, sources, self.model, charts)


def _collect_sources(out: dict) -> list[dict]:
    src = []
    if not isinstance(out, dict):
        return src
    for key in ("deals", "leads", "tasks", "contacts", "companies", "units", "projects", "visits"):
        for r in out.get(key, [])[:5] if isinstance(out.get(key), list) else []:
            if r.get("url"):
                src.append({"label": r.get("name") or r.get("title") or r.get("label"), "url": r["url"], "type": key.rstrip("s")})
    return src


def _collect_charts(out: dict) -> list[dict]:
    c = out.get("chart") if isinstance(out, dict) else None
    return [c] if isinstance(c, dict) and c.get("data") else []


def _for_model(out: dict) -> dict:
    """What the model sees of a tool result: charts are for the screen, so only their numbers go back."""
    if isinstance(out, dict) and "chart" in out:
        out = {k: v for k, v in out.items() if k != "chart"}
    from app.services.ai import privacy

    return privacy.mask(out)


def get_provider(tier: str = "smart", workspace_id=None, timeout: float = 60) -> AIProvider:
    """The workspace's own key first, then the platform key, then the rule-based basic mode."""
    from app.services.ai import settings as ai_settings
    from app.services.ai.mock import MockProvider

    cfg = ai_settings.resolve(workspace_id)
    model = cfg.model(tier)
    if cfg.provider == "anthropic":
        return AnthropicProvider(cfg.key, model, timeout)
    if cfg.provider in ("openai", "gemini", "openrouter"):
        return OpenAIProvider(cfg.key, model, ai_settings.PROVIDERS[cfg.provider]["base_url"], cfg.provider, timeout)
    return MockProvider()
