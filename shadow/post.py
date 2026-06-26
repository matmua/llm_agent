"""Post-action visible-delta and conservative no-progress checks."""

from __future__ import annotations

from typing import Any

from shadow.parser import normalize_value


REPEATED_BEHAVIOR_RISK_STREAK = 3


def run_post_check(
    attributes_before: dict[str, Any],
    observed_attrs_after: dict[str, dict[str, Any]],
    action_record: dict[str, Any],
    shadow_state: dict[str, Any],
    context_after: str,
) -> dict[str, Any]:
    new_attrs = new_attribute_values(attributes_before, observed_attrs_after)
    visible_delta = bool(new_attrs)
    context_before = str(action_record.get("context_before") or "")
    signature_streak = same_action_signature_streak(
        action_record=action_record,
        shadow_state=shadow_state,
    )
    repeated_behavior_risk = signature_streak >= REPEATED_BEHAVIOR_RISK_STREAK
    same_action_count = same_action_no_visible_delta_count(
        action_record=action_record,
        shadow_state=shadow_state,
        visible_delta=visible_delta,
    )
    context_cycle_detected = detect_context_cycle(
        shadow_state=shadow_state,
        context_after=context_after,
        visible_delta=visible_delta,
    )
    no_progress = False
    no_progress_reason = None
    if not visible_delta and same_action_count >= 3:
        no_progress = True
        no_progress_reason = "same_action_repeated_without_visible_delta"
    elif not visible_delta and context_cycle_detected:
        no_progress = True
        no_progress_reason = "context_cycle_without_visible_delta"

    return {
        "visible_delta": visible_delta,
        "info_gain": visible_delta,
        "new_attrs": new_attrs,
        "same_action_no_visible_delta_count": same_action_count,
        "context_cycle_detected": context_cycle_detected,
        "same_action_signature_streak": signature_streak,
        "repeated_behavior_risk": repeated_behavior_risk,
        "repeated_behavior_reason": (
            "same_action_signature_streak" if repeated_behavior_risk else None
        ),
        "no_progress": no_progress,
        "no_progress_reason": no_progress_reason,
        "context_before": context_before,
        "context_after": context_after,
        "context_changed": bool(context_before and context_before != context_after),
        "new_context": _new_context(attributes_before, context_after),
    }


def new_attribute_values(
    attributes_before: dict[str, Any],
    observed_attrs_after: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    new_attrs: list[dict[str, str]] = []
    for key, record in observed_attrs_after.items():
        before_values = set((attributes_before.get(key, {}).get("values") or {}).keys())
        for value in (record.get("values") or {}).keys():
            norm = normalize_value(value)
            if key not in attributes_before or norm not in before_values:
                new_attrs.append({"key": key, "value": str(record.get("current_value") or value)})
    return new_attrs


def same_action_no_visible_delta_count(
    action_record: dict[str, Any],
    shadow_state: dict[str, Any],
    visible_delta: bool,
) -> int:
    if visible_delta:
        return 0
    context = action_record.get("context_before")
    signature = action_record.get("action_signature")
    if not context or not signature:
        return 1
    previous_count = 0
    for previous in shadow_state.get("actions", []):
        if previous.get("context_before") != context:
            continue
        if previous.get("action_signature") != signature:
            continue
        post_check = previous.get("post_check", {})
        previous_visible_delta = post_check.get("visible_delta", post_check.get("info_gain"))
        if previous_visible_delta is False:
            previous_count += 1
    return previous_count + 1


def same_action_signature_streak(
    action_record: dict[str, Any],
    shadow_state: dict[str, Any],
) -> int:
    signature = action_record.get("action_signature")
    if not signature:
        return 1
    streak = 1
    for previous in reversed(shadow_state.get("actions", [])):
        if previous.get("action_signature") != signature:
            break
        streak += 1
    return streak


def detect_context_cycle(
    shadow_state: dict[str, Any],
    context_after: str,
    visible_delta: bool,
) -> bool:
    previous_actions = shadow_state.get("actions", [])
    context_values = [
        str(action.get("post_check", {}).get("context_after") or "")
        for action in previous_actions
    ]
    context_values.append(str(context_after or ""))
    recent_contexts = [item for item in context_values if item][-4:]
    if len(recent_contexts) < 4:
        return False
    a, b, c, d = recent_contexts
    if not (a == c and b == d and a != b):
        return False
    recent_visible_delta = [
        action.get("post_check", {}).get(
            "visible_delta",
            action.get("post_check", {}).get("info_gain"),
        )
        for action in previous_actions[-2:]
    ]
    recent_visible_delta.append(visible_delta)
    return len(recent_visible_delta) == 3 and all(item is False for item in recent_visible_delta)


def _new_context(attributes_before: dict[str, Any], context_after: str) -> bool:
    context_values = (
        attributes_before.get("context.current", {}).get("values") or {}
    )
    return normalize_value(context_after) not in context_values
