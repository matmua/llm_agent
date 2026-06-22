"""Format-only action parser for rule-based shadow v1."""

from __future__ import annotations

import re
from typing import Any


BRACKET_ACTIONS = {"search", "click", "think"}


def parse_action(raw_action: str) -> dict[str, Any]:
    text = raw_action or ""
    match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\[(.*)\]\s*", text, flags=re.S)
    if not match:
        return {
            "type": "invalid",
            "params": {},
            "format_valid": False,
            "error": "action must match name[...]",
        }

    action_type = match.group(1).lower()
    value = match.group(2).strip()
    if action_type not in BRACKET_ACTIONS:
        return {
            "type": action_type,
            "params": {"value": value} if value else {},
            "format_valid": False,
            "error": f"unsupported bracket action type: {action_type}",
        }
    if not value:
        return {
            "type": action_type,
            "params": {},
            "format_valid": False,
            "error": "action parameter is empty",
        }
    return {
        "type": action_type,
        "params": _params_for(action_type, value),
        "format_valid": True,
        "error": None,
    }


def action_signature(parsed_action: dict[str, Any]) -> str:
    action_type = str(parsed_action.get("type") or "invalid")
    params = parsed_action.get("params") or {}
    if not isinstance(params, dict) or not params:
        return action_type
    parts = [f"{key}={normalize_value(value)}" for key, value in sorted(params.items())]
    return action_type + "|" + "|".join(parts)


def normalize_value(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _params_for(action_type: str, value: str) -> dict[str, str]:
    if action_type == "search":
        return {"query": value}
    if action_type == "click":
        return {"target": value}
    if action_type == "think":
        return {"thought": value}
    return {"value": value}
