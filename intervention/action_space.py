"""Generic helpers for environment action spaces.

The WebShop runner exposes actions as ``clickables``. Other environments may
expose shell commands, tool names, choices, or structured action objects. These
helpers normalize those shapes into short candidate action strings so policy and
verifier code can stay environment-agnostic.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


ACTION_COLLECTION_KEYS = (
    "clickables",
    "actions",
    "available_actions",
    "valid_actions",
    "commands",
    "command_candidates",
    "tools",
    "tool_calls",
    "choices",
    "options",
    "candidates",
)
ACTION_TEXT_KEYS = (
    "raw",
    "action",
    "command",
    "cmd",
    "tool",
    "tool_name",
    "function_name",
    "name",
    "label",
    "text",
    "title",
    "id",
)
MAPPING_ACTION_KEY_DENYLIST = {
    "args",
    "arguments",
    "description",
    "input",
    "inputs",
    "metadata",
    "parameters",
    "properties",
    "schema",
    "type",
}


def normalize_text(value: Any) -> str:
    return " ".join(str(value).strip().lower().split())


def has_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    return any(has_keyword(text, keyword) for keyword in keywords)


def has_keyword(text: str, keyword: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(normalize_text(keyword)) + r"(?![a-z0-9])"
    return re.search(pattern, normalize_text(text or "")) is not None


def candidate_action_texts(available_actions: Any, limit: int = 50) -> tuple[str, ...]:
    """Return action-like strings from common environment schemas.

    Accepted examples:
    - {"clickables": ["Submit"]}
    - {"commands": ["pytest tests/test_app.py"]}
    - {"actions": [{"command": "python solve.py"}, {"name": "submit"}]}
    - [{"tool": "read_file"}, "final_answer"]
    - {"tools": {"read_file": {...}, "final_answer": {...}}}
    """

    results: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        text = str(value).strip()
        if not text:
            return
        key = normalize_text(text)
        if key in seen:
            return
        seen.add(key)
        results.append(text)

    def item_text(item: Any) -> str | None:
        if item is None or isinstance(item, bool):
            return None
        if isinstance(item, (str, int, float)):
            return str(item)
        if isinstance(item, Mapping):
            for key in ACTION_TEXT_KEYS:
                value = item.get(key)
                if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                    return str(value)
            function = item.get("function")
            if isinstance(function, Mapping):
                for key in ("name", "description"):
                    value = function.get(key)
                    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                        return str(value)
        return None

    def collect(value: Any, *, from_action_collection: bool = False) -> None:
        if len(results) >= limit:
            return
        text = item_text(value)
        if text is not None:
            add(text)
            return
        if isinstance(value, Mapping):
            collected_collection = False
            for key in ACTION_COLLECTION_KEYS:
                if key in value:
                    collected_collection = True
                    collect(value.get(key), from_action_collection=True)
                    if len(results) >= limit:
                        return
            if collected_collection:
                return
            if from_action_collection:
                for key, item in value.items():
                    if str(key).strip().lower() not in MAPPING_ACTION_KEY_DENYLIST:
                        add(key)
                    collect(item)
                    if len(results) >= limit:
                        return
            return
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            for item in value:
                collect(item, from_action_collection=from_action_collection)
                if len(results) >= limit:
                    return

    collect(available_actions)
    return tuple(results[:limit])
