"""LLM risk verifier for rule-triggered shadow events.

This module only records verification results. It never changes actions,
prompts, environment state, or repair behavior.
"""

from __future__ import annotations

import json
from typing import Any

from intervention.prompts import RISK_VERIFIER_SYSTEM_PROMPT

ERROR_TYPES = {
    "evidence_guessing",
    "format_error",
    "loop_or_repetition",
    "wrong_action_or_param",
    "none",
}
ACTIVE_ERROR_TYPES = ERROR_TYPES - {"none"}
OUTPUT_KEYS = {"is_error", "error_type", "confidence", "repair_hint", "avoid_action"}


def verify_risk_if_triggered(
    action_record: dict[str, Any],
    shadow_state: dict[str, Any],
    task: str,
    current_observation: str,
    available_actions: dict[str, Any],
    enabled: bool,
    client: Any,
    max_recent_steps: int = 6,
    temperature: float = 0.0,
) -> dict[str, Any]:
    if not enabled:
        return default_verification(enabled=False, triggered=False, called=False)

    trigger = find_risk_trigger(action_record)
    if trigger is None:
        return default_verification(enabled=True, triggered=False, called=False)

    if client is None:
        return default_verification(
            enabled=True,
            triggered=True,
            called=False,
            parse_error="llm_client_unavailable",
        )

    risk_package = build_risk_package(
        action_record=action_record,
        shadow_state=shadow_state,
        task=task,
        current_observation=current_observation,
        available_actions=available_actions,
        max_recent_steps=max_recent_steps,
    )
    try:
        raw_response = client.chat(
            [
                {"role": "system", "content": RISK_VERIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(risk_package, ensure_ascii=False)},
            ],
            temperature=temperature,
            max_tokens=256,
        )
    except Exception as exc:  # pragma: no cover - defensive around external clients
        return default_verification(
            enabled=True,
            triggered=True,
            called=True,
            raw_response=None,
            parse_error=f"llm_exception:{exc.__class__.__name__}",
        )

    return parse_verifier_response(str(raw_response))


def build_risk_package(
    action_record: dict[str, Any],
    shadow_state: dict[str, Any],
    task: str,
    current_observation: str,
    available_actions: dict[str, Any],
    max_recent_steps: int,
) -> dict[str, Any]:
    trigger = find_risk_trigger(action_record) or {
        "stage": "post",
        "step": action_record.get("step"),
        "signal": "none",
        "candidate_error_type": "none",
    }
    parsed = action_record.get("parsed_action") or {}
    post = action_record.get("post_check") or {}
    return {
        "task": task,
        "risk_trigger": trigger,
        "action_under_check": {
            "raw": action_record.get("raw_action", action_record.get("raw")),
            "type": action_record.get("type", parsed.get("type")),
            "params": action_record.get("params", parsed.get("params") or {}),
        },
        "current_observation": str(current_observation or ""),
        "available_actions": format_available_actions(available_actions),
        "recent_trace": recent_trace(
            action_record=action_record,
            shadow_state=shadow_state,
            max_recent_steps=max_recent_steps,
        ),
        "shadow_evidence": {
            "param_checks": action_record.get("param_checks") or {},
            "visible_delta": post.get("visible_delta"),
            "same_action_signature_streak": post.get("same_action_signature_streak"),
            "same_action_no_visible_delta_count": post.get("same_action_no_visible_delta_count"),
            "context_cycle_detected": post.get("context_cycle_detected"),
            "context_before": post.get("context_before", action_record.get("context_before")),
            "context_after": post.get("context_after"),
        },
    }


def find_risk_trigger(action_record: dict[str, Any]) -> dict[str, Any] | None:
    pre = action_record.get("pre_check") or {}
    post = action_record.get("post_check") or {}
    step = action_record.get("step")
    if pre.get("format_valid") is False:
        return {
            "stage": "pre",
            "step": step,
            "signal": "format_invalid",
            "candidate_error_type": "format_error",
        }
    if pre.get("repeat_known_no_info") is True:
        return {
            "stage": "pre",
            "step": step,
            "signal": "repeat_known_no_info",
            "candidate_error_type": "loop_or_repetition",
        }
    if post.get("no_progress") is True:
        return {
            "stage": "post",
            "step": step,
            "signal": "no_progress",
            "candidate_error_type": "loop_or_repetition",
        }
    if post.get("context_cycle_detected") is True:
        return {
            "stage": "post",
            "step": step,
            "signal": "context_cycle",
            "candidate_error_type": "loop_or_repetition",
        }
    if post.get("repeated_behavior_risk") is True:
        return {
            "stage": "trajectory",
            "step": step,
            "signal": "repeated_behavior_risk",
            "candidate_error_type": "loop_or_repetition",
        }
    return None


def parse_verifier_response(raw_response: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_response.strip())
    except json.JSONDecodeError as exc:
        return default_verification(
            enabled=True,
            triggered=True,
            called=True,
            raw_response=raw_response,
            parse_error=f"json_decode_error:{exc.msg}",
        )
    error = validate_verifier_output(parsed)
    if error is not None:
        return default_verification(
            enabled=True,
            triggered=True,
            called=True,
            raw_response=raw_response,
            parse_error=error,
        )
    return {
        "enabled": True,
        "triggered": True,
        "called": True,
        "is_error": parsed["is_error"],
        "error_type": parsed["error_type"],
        "confidence": float(parsed["confidence"]),
        "repair_hint": parsed["repair_hint"],
        "avoid_action": parsed["avoid_action"],
        "raw_response": raw_response,
        "parse_error": None,
    }


def validate_verifier_output(parsed: Any) -> str | None:
    if not isinstance(parsed, dict):
        return "output_not_object"
    keys = set(parsed)
    if keys != OUTPUT_KEYS:
        missing = sorted(OUTPUT_KEYS - keys)
        extra = sorted(keys - OUTPUT_KEYS)
        return f"invalid_fields:missing={missing}:extra={extra}"
    if not isinstance(parsed.get("is_error"), bool):
        return "invalid_is_error_type"
    error_type = parsed.get("error_type")
    if error_type not in ERROR_TYPES:
        return "invalid_error_type"
    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return "invalid_confidence_type"
    if float(confidence) < 0.0 or float(confidence) > 1.0:
        return "invalid_confidence_range"
    if not isinstance(parsed.get("repair_hint"), str):
        return "invalid_repair_hint_type"
    avoid_action = parsed.get("avoid_action")
    if avoid_action is not None and not isinstance(avoid_action, str):
        return "invalid_avoid_action_type"

    if parsed["is_error"] is False:
        if error_type != "none":
            return "invalid_non_error_type"
        if float(confidence) != 0.0:
            return "invalid_non_error_confidence"
        if parsed["repair_hint"] != "":
            return "invalid_non_error_repair_hint"
        if avoid_action is not None:
            return "invalid_non_error_avoid_action"
    elif error_type not in ACTIVE_ERROR_TYPES:
        return "invalid_error_type_for_error"
    return None


def default_verification(
    enabled: bool,
    triggered: bool,
    called: bool,
    parse_error: str | None = None,
    raw_response: str | None = None,
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "triggered": triggered,
        "called": called,
        "is_error": False,
        "error_type": "none",
        "confidence": 0.0,
        "repair_hint": "",
        "avoid_action": None,
        "raw_response": raw_response,
        "parse_error": parse_error,
    }


def format_available_actions(available_actions: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if available_actions.get("has_search_bar"):
        actions.append("search[...]")
    for item in available_actions.get("clickables") or []:
        actions.append(f"click[{item}]")
    return actions


def recent_trace(
    action_record: dict[str, Any],
    shadow_state: dict[str, Any],
    max_recent_steps: int,
) -> list[dict[str, Any]]:
    records = list(shadow_state.get("actions") or [])
    if not records or not _same_action_identity(records[-1], action_record):
        records.append(action_record)
    records = records[-max(1, int(max_recent_steps)) :]
    trace = []
    for record in records:
        post = record.get("post_check") or {}
        trace.append(
            {
                "step": record.get("step"),
                "action": record.get("raw_action", record.get("raw")),
                "action_signature": record.get("action_signature"),
                "visible_delta": post.get("visible_delta"),
                "no_progress": post.get("no_progress"),
                "no_progress_reason": post.get("no_progress_reason"),
                "repeated_behavior_risk": post.get("repeated_behavior_risk"),
                "same_action_signature_streak": post.get("same_action_signature_streak"),
            }
        )
    return trace


def _same_action_identity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("step") == right.get("step")
        and left.get("raw_action", left.get("raw")) == right.get("raw_action", right.get("raw"))
    )

