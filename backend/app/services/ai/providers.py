"""LLM provider abstraction. Switch with AI_PROVIDER=mock|anthropic|openai — the CRM code never imports a vendor SDK.

`mock` is a deterministic, data-driven provider (no external calls): it routes questions to the same CRM tools a real
model would call and renders the answer. It keeps the product fully functional in dev, demos and tests.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol

import httpx
from flask import current_app

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


class AIProvider(Protocol):
    name: str

    def complete(self, kind: str, system: str, prompt: str, context: dict) -> AIResult: ...
    def chat(self, system: str, history: list[dict], tools: list[dict], run_tool: ToolRunner, max_steps: int = 5) -> AIResult: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self.key = current_app.config["ANTHROPIC_API_KEY"]
        self.model = current_app.config["AI_MODEL"] or "claude-sonnet-5-5"

    def _post(self, payload: dict) -> dict:
        r = httpx.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, json=payload, timeout=60)
        if r.status_code >= 400:
            log.error("anthropic error %s: %s", r.status_code, r.text[:300])
            raise ApiError(502, "ai_provider_error", "The AI service is temporarily unavailable. Please try again.")
        return r.json()

    def complete(self, kind, system, prompt, context):
        d = self._post({"model": self.model, "max_tokens": 900, "system": system, "messages": [{"role": "user", "content": prompt}]})
        return AIResult("".join(b.get("text", "") for b in d["content"]), d["usage"]["input_tokens"], d["usage"]["output_tokens"], model=self.model)

    def chat(self, system, history, tools, run_tool, max_steps=5):
        msgs = [{"role": m["role"], "content": m["content"]} for m in history]
        tin = tout = 0
        sources: list[dict] = []
        for _ in range(max_steps):
            d = self._post({"model": self.model, "max_tokens": 1200, "system": system, "tools": tools, "messages": msgs})
            tin, tout = tin + d["usage"]["input_tokens"], tout + d["usage"]["output_tokens"]
            blocks = d["content"]
            if d.get("stop_reason") != "tool_use":
                return AIResult("".join(b.get("text", "") for b in blocks), tin, tout, sources, self.model)
            msgs.append({"role": "assistant", "content": blocks})
            results = []
            for b in blocks:
                if b["type"] == "tool_use":
                    out = run_tool(b["name"], b["input"])
                    sources += _collect_sources(out)
                    results.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(out, default=str)[:12000]})
            msgs.append({"role": "user", "content": results})
        return AIResult("I couldn't finish that analysis. Try a more specific question.", tin, tout, sources, self.model)


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        self.key = current_app.config["OPENAI_API_KEY"]
        self.model = current_app.config["AI_MODEL"] or "gpt-4.1"

    def _post(self, payload: dict) -> dict:
        r = httpx.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {self.key}"}, json=payload, timeout=60)
        if r.status_code >= 400:
            log.error("openai error %s: %s", r.status_code, r.text[:300])
            raise ApiError(502, "ai_provider_error", "The AI service is temporarily unavailable. Please try again.")
        return r.json()

    def complete(self, kind, system, prompt, context):
        d = self._post({"model": self.model, "max_tokens": 900, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        u = d.get("usage", {})
        return AIResult(d["choices"][0]["message"]["content"] or "", u.get("prompt_tokens", 0), u.get("completion_tokens", 0), model=self.model)

    def chat(self, system, history, tools, run_tool, max_steps=5):
        msgs = [{"role": "system", "content": system}] + [{"role": m["role"], "content": m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])} for m in history]
        oa_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools]
        tin = tout = 0
        sources: list[dict] = []
        for _ in range(max_steps):
            d = self._post({"model": self.model, "messages": msgs, "tools": oa_tools})
            u = d.get("usage", {})
            tin, tout = tin + u.get("prompt_tokens", 0), tout + u.get("completion_tokens", 0)
            m = d["choices"][0]["message"]
            if not m.get("tool_calls"):
                return AIResult(m.get("content") or "", tin, tout, sources, self.model)
            msgs.append(m)
            for tc in m["tool_calls"]:
                out = run_tool(tc["function"]["name"], json.loads(tc["function"]["arguments"] or "{}"))
                sources += _collect_sources(out)
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(out, default=str)[:12000]})
        return AIResult("I couldn't finish that analysis. Try a more specific question.", tin, tout, sources, self.model)


def _collect_sources(out: dict) -> list[dict]:
    src = []
    for key in ("deals", "leads", "tasks", "contacts", "companies"):
        for r in out.get(key, [])[:5] if isinstance(out.get(key), list) else []:
            if r.get("url"):
                src.append({"label": r.get("name") or r.get("title"), "url": r["url"], "type": key.rstrip("s")})
    return src


def get_provider() -> AIProvider:
    from app.services.ai.mock import MockProvider

    name = current_app.config["AI_PROVIDER"]
    if name == "anthropic" and current_app.config["ANTHROPIC_API_KEY"]:
        return AnthropicProvider()
    if name == "openai" and current_app.config["OPENAI_API_KEY"]:
        return OpenAIProvider()
    return MockProvider()
