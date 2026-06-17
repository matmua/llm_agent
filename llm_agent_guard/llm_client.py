"""Small OpenAI-compatible JSON client used by the guard modules."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Optional


class OpenAICompatibleClient:
    def __init__(self, model: str, base_url: str, api_key: str, timeout: int = 120):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def chat_json(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> dict:
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

        content = raw.get("content") or ""
        parsed = self._extract_json(content)
        if parsed is None:
            return {
                "_parse_error": True,
                "raw_response": content,
            }
        parsed["raw_response"] = content
        return parsed

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        raw = self._post_chat(payload)
        return str(raw.get("content") or raw.get("raw_response") or "")

    def _post_chat(self, payload: dict[str, Any]) -> dict:
        url = self.base_url + "/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            return {"_request_error": True, "raw_response": str(exc)}

        try:
            data_obj = json.loads(body)
        except json.JSONDecodeError:
            return {"_request_error": True, "raw_response": body}

        try:
            content = data_obj["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return {"_request_error": True, "raw_response": body}
        return {"content": content}

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
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
