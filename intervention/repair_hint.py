"""Lightweight repair hints for verified risk events.

This module does not call LLMs and does not mutate rule-check outputs. It only
turns verifier results into short, one-shot prompts or pre-repair decisions.
"""

from __future__ import annotations

from typing import Any


def should_apply_pre_repair(pre_verification: dict[str, Any], repair_enabled: bool) -> bool:
    return bool(repair_enabled and pre_verification.get("is_error") is True)


def should_create_post_hint(post_verification: dict[str, Any], repair_enabled: bool) -> bool:
    return bool(repair_enabled and post_verification.get("is_error") is True)


def build_repair_hint(
    verification: dict[str, Any],
    stage: str,
    action_record: dict[str, Any],
) -> dict[str, Any]:
    if stage not in {"pre", "post"}:
        raise ValueError(f"stage must be 'pre' or 'post', got {stage!r}")
    action_under_check = (
        action_record.get("raw_action", action_record.get("raw"))
        if stage == "pre"
        else action_record.get("executed_action", action_record.get("raw_action", action_record.get("raw")))
    )
    return {
        "stage": stage,
        "source_step": action_record.get("step"),
        "error_type": verification.get("error_type", "none"),
        "repair_hint": verification.get("repair_hint", ""),
        "avoid_action": verification.get("avoid_action"),
        "action_under_check": action_under_check,
        "post_check": action_record.get("post_check", {}),
    }


def format_hint_for_agent(repair_hint: dict[str, Any]) -> str:
    error_type = repair_hint.get("error_type")
    avoid_action = repair_hint.get("avoid_action")
    post_check = repair_hint.get("post_check") or {}

    if error_type == "none":
        return ""
    if error_type == "format_error":
        body = (
            "The previous action format was invalid.\n"
            "Generate a valid action using exactly one of the required formats.\n"
            "Do not explain.\n"
            "Output only the action in the required format."
        )
    elif error_type == "evidence_guessing":
        body = (
            "The previous action may rely on unsupported information.\n"
            "Use only entities, values, or options that appear in the task, current observation, available actions, or recent confirmed evidence.\n"
            "Do not invent unseen parameters.\n"
            "Output only the action in the required format."
        )
    elif error_type == "loop_or_repetition":
        body = _loop_hint_body(post_check, avoid_action)
    elif error_type == "wrong_action_or_param":
        lines = [
            "The previous action or parameter may not match the task requirement or current observation.",
            "Re-check the task goal and choose a valid action with a better matching parameter.",
            "Do not repeat the same unsuitable action.",
        ]
        if avoid_action:
            lines.append(f"Avoid repeating this action: {avoid_action}.")
        lines.append("Output only the action in the required format.")
        body = "\n".join(lines)
    else:
        return ""

    return f"Risk-control hint for this action:\n{body}"


def _loop_hint_body(post_check: dict[str, Any], avoid_action: Any) -> str:
    if post_check.get("repeated_behavior_risk") is True:
        lines = [
            "The previous behavior was verified as repeated exploration.",
            "Do not continue the same action or strategy.",
        ]
        if avoid_action:
            lines.append(f"Avoid repeating this action: {avoid_action}.")
        lines.extend(
            [
                "Use the current observation to choose a concrete useful action that moves toward completing the task.",
                "If a suitable candidate or completion action is available, act on it instead of continuing navigation.",
                "Output only the action in the required format.",
            ]
        )
        return "\n".join(lines)
    if post_check.get("context_cycle_detected") is True:
        return (
            "A context cycle was verified.\n"
            "Do not return to the same repeated context again.\n"
            "Choose a different valid action that changes the strategy or moves toward task completion.\n"
            "Output only the action in the required format."
        )
    if post_check.get("no_progress") is True:
        return (
            "A local repeated action was verified.\n"
            "Do not blindly repeat the same action.\n"
            "If the current observation already provides a valid action that can complete or commit the task, consider using it.\n"
            "Otherwise choose a useful different action based on the current observation.\n"
            "Output only the action in the required format."
        )
    lines = [
        "The previous behavior was verified as repeated exploration.",
        "Do not continue the same action or strategy.",
    ]
    if avoid_action:
        lines.append(f"Avoid repeating this action: {avoid_action}.")
    lines.extend(
        [
            "Use the current observation to choose a concrete useful action that moves toward completing the task.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def mark_hint_outcome(pending_hint: dict[str, Any], next_raw_action: str) -> dict[str, Any]:
    avoid_action = pending_hint.get("avoid_action") or pending_hint.get("action_under_check")
    followed = True if not avoid_action else str(next_raw_action) != str(avoid_action)
    return {
        "followed": followed,
        "avoid_action": pending_hint.get("avoid_action"),
        "matched_action": avoid_action,
    }
