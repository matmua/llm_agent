"""Pre-action checks for rule-based shadow v1."""

from __future__ import annotations

from typing import Any


def run_pre_check(action_record: dict[str, Any], shadow_state: dict[str, Any]) -> dict[str, bool]:
    return {
        "format_valid": bool(action_record.get("parsed_action", {}).get("format_valid")),
        "repeat_known_no_info": _repeat_known_no_info(action_record, shadow_state),
    }


def _repeat_known_no_info(action_record: dict[str, Any], shadow_state: dict[str, Any]) -> bool:
    context = action_record.get("context_before")
    signature = action_record.get("action_signature")
    if not context or not signature:
        return False
    for previous in shadow_state.get("actions", []):
        if previous.get("context_before") != context:
            continue
        if previous.get("action_signature") != signature:
            continue
        if previous.get("post_check", {}).get("info_gain") is False:
            return True
    return False
