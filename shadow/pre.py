"""Pre-action checks for rule-based shadow v1."""

from __future__ import annotations

from typing import Any


def run_pre_check(action_record: dict[str, Any], shadow_state: dict[str, Any]) -> dict[str, bool]:
    return {
        "format_valid": bool(action_record.get("parsed_action", {}).get("format_valid")),
        "repeat_known_no_info": _repeat_known_no_info(action_record, shadow_state),
    }


def _repeat_known_no_info(action_record: dict[str, Any], shadow_state: dict[str, Any]) -> bool:
    return _previous_same_action_no_visible_delta_count(action_record, shadow_state) >= 2


def _previous_same_action_no_visible_delta_count(
    action_record: dict[str, Any],
    shadow_state: dict[str, Any],
) -> int:
    context = action_record.get("context_before")
    signature = action_record.get("action_signature")
    if not context or not signature:
        return 0
    count = 0
    for previous in shadow_state.get("actions", []):
        if previous.get("context_before") != context:
            continue
        if previous.get("action_signature") != signature:
            continue
        post_check = previous.get("post_check", {})
        visible_delta = post_check.get("visible_delta", post_check.get("info_gain"))
        if visible_delta is False:
            count += 1
    return count
