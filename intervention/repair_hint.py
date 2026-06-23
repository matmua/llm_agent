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
    }


def format_hint_for_agent(repair_hint: dict[str, Any]) -> str:
    error_type = repair_hint.get("error_type")
    avoid_action = repair_hint.get("avoid_action")

    if error_type == "loop_or_repetition":
        if avoid_action:
            body = (
                "A repeated-behavior risk was verified.\n"
                f"Avoid repeating this action: {avoid_action}.\n"
                "Choose a different valid action based on the current observation.\n"
                "Output only the action in the required format."
            )
        else:
            body = (
                "A repeated-behavior risk was verified.\n"
                "Do not continue the same strategy. Choose a different valid action based on the current observation.\n"
                "Output only the action in the required format."
            )
    elif error_type == "format_error":
        body = (
            "The previous action format was invalid.\n"
            "Generate a valid action using the required action format.\n"
            "Output only the action in the required format."
        )
    elif error_type == "evidence_guessing":
        body = (
            "The previous action may rely on unsupported information.\n"
            "Use only entities, values, or options that appear in the task, current observation, or available actions.\n"
            "Output only the action in the required format."
        )
    elif error_type == "wrong_action_or_param":
        lines = [
            "The previous action or parameter may not match the task or current observation.",
            "Re-check the task requirement and choose a better valid action.",
        ]
        if avoid_action:
            lines.append(f"Avoid repeating this action if possible: {avoid_action}.")
        lines.append("Output only the action in the required format.")
        body = "\n".join(lines)
    else:
        body = (
            "A risk was verified.\n"
            "Choose a different valid action based on the current observation.\n"
            "Output only the action in the required format."
        )

    return f"Risk-control hint for this action:\n{body}"


def mark_hint_outcome(pending_hint: dict[str, Any], next_raw_action: str) -> dict[str, Any]:
    avoid_action = pending_hint.get("avoid_action") or pending_hint.get("action_under_check")
    followed = True if not avoid_action else str(next_raw_action) != str(avoid_action)
    return {
        "followed": followed,
        "avoid_action": pending_hint.get("avoid_action"),
        "matched_action": avoid_action,
    }
