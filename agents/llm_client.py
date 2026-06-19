"""LLM clients used by WebShop agents.

The OpenAI-compatible client explicitly disables urllib proxy handling so model
traffic launched from this project does not inherit a local SSH proxy.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Protocol


class LLMClient(Protocol):
    model: str

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> str:
        ...

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        ...


class OpenAIChatClient:
    def __init__(self, model: str, base_url: str, api_key: str, timeout: int = 120):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_env(cls, model: str | None = None) -> "OpenAIChatClient":
        resolved_model = model or os.getenv("LLM_MODEL") or os.getenv("QWEN_MODEL") or ""
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("QWEN_BASE_URL") or ""
        api_key = os.getenv("LLM_API_KEY") or os.getenv("QWEN_API_KEY") or ""
        if not resolved_model or not base_url or not api_key:
            raise ValueError(
                "Missing LLM configuration. Set LLM_MODEL/LLM_BASE_URL/LLM_API_KEY "
                "or pass --model mock."
            )
        return cls(model=resolved_model, base_url=base_url, api_key=api_key)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        raw = self._post_chat(payload)
        return str(raw.get("content") or raw.get("raw_response") or "")

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        raw = self._post_chat(payload)
        if raw.get("_request_error") and "response_format" in str(raw.get("raw_response")):
            payload.pop("response_format", None)
            raw = self._post_chat(payload)
        if raw.get("_request_error"):
            return raw
        parsed = extract_json(str(raw.get("content") or ""))
        if parsed is None:
            return {"_parse_error": True, "raw_response": raw.get("content", "")}
        parsed["raw_response"] = raw.get("content", "")
        return parsed

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.base_url + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            return {"_request_error": True, "raw_response": str(exc)}

        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return {"_request_error": True, "raw_response": body}
        return {"content": content}


class MockLLMClient:
    """Deterministic action generator for tests and smoke runs."""

    model = "mock"

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> str:
        prompt = messages[-1]["content"] if messages else ""
        observation = _section(prompt, "Observation", "Available actions")
        instruction = _section(prompt, "Task instruction", "Observation")
        clickables = _clickables_from_prompt(prompt)

        if "buy now" in clickables:
            return "Thought: I found a product page.\nAction: click[buy now]"
        product_clicks = [
            item
            for item in clickables
            if item
            not in {
                "search",
                "next",
                "next >",
                "previous",
                "< prev",
                "back to search",
                "description",
                "features",
                "reviews",
            }
        ]
        if product_clicks:
            return f"Thought: I will inspect the first visible product.\nAction: click[{product_clicks[0]}]"
        if "has_search_bar: true" in prompt.lower():
            query = _query_from_instruction(instruction or observation)
            return f"Thought: I should search for the requested product.\nAction: search[{query}]"
        return "Thought: No useful action is visible.\nAction: click[buy now]"

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        return {
            "risk_score": 0.0,
            "risk_level": "low",
            "should_block_hypothetical": False,
            "risk_categories": [],
            "missing_attributes": [],
            "unsupported_assumptions": [],
            "expected_delta": {},
            "reason": "Mock judge did not add risk.",
            "hypothetical_completion_action": "",
            "hypothetical_repair_plan": "",
            "raw_response": "{}",
        }


def extract_json(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _section(text: str, start: str, end: str) -> str:
    pattern = re.compile(rf"{re.escape(start)}:\n(.*?)(?:\n{re.escape(end)}:|\Z)", re.S)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _clickables_from_prompt(prompt: str) -> list[str]:
    match = re.search(r"clickables:\s*\[(.*?)\]", prompt, re.I | re.S)
    if not match:
        return []
    raw = match.group(1)
    parts = [part.strip().strip("'\"").lower() for part in raw.split(",")]
    return [part for part in parts if part]


def _query_from_instruction(text: str) -> str:
    lowered = text.lower()
    stop = {
        "find",
        "instruction",
        "me",
        "buy",
        "purchase",
        "a",
        "an",
        "the",
        "under",
        "below",
        "less",
        "than",
        "with",
        "for",
        "and",
        "please",
    }
    words = re.findall(r"[a-z][a-z0-9-]+", lowered)
    words = [word for word in words if word not in stop and not word.isdigit()]
    return " ".join(words[:4]) or "product"
