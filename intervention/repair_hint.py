"""Lightweight repair hints for verified risk events.

This module does not call LLMs and does not mutate rule-check outputs. It only
turns verifier results into short, one-shot prompts or pre-repair decisions.
"""

from __future__ import annotations

from typing import Any


PRE_REPAIR_PROMPT_STRENGTHS = {"standard", "strong", "completion", "late", "task", "task_late"}


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


def format_pre_repair_hint_for_agent(
    repair_hint: dict[str, Any],
    prompt_strength: str = "standard",
) -> str:
    if prompt_strength not in PRE_REPAIR_PROMPT_STRENGTHS:
        raise ValueError(
            f"prompt_strength must be one of {sorted(PRE_REPAIR_PROMPT_STRENGTHS)}, "
            f"got {prompt_strength!r}"
        )
    if prompt_strength == "standard":
        return format_hint_for_agent(repair_hint)
    if prompt_strength == "completion":
        return _completion_pre_repair_hint(repair_hint)
    if prompt_strength == "late":
        return _late_budget_pre_repair_hint(repair_hint)
    if prompt_strength in {"task", "task_late"}:
        return _task_aware_pre_repair_hint(
            repair_hint,
            late=prompt_strength == "task_late",
        )

    error_type = repair_hint.get("error_type")
    if error_type == "none":
        return ""

    avoid_action = action_to_avoid(repair_hint)
    lines = [
        "Risk-control hint for this action:",
        "The candidate action was verified as repeated navigation or repeated search before execution.",
    ]
    if avoid_action:
        lines.append(f"Do not output this same navigation/search action again: {avoid_action}.")
        lines.append(
            "Your next response must be exactly one valid action, and it must be "
            "different from that action."
        )
    else:
        lines.append(
            "Your next response must be exactly one valid action that avoids the verified repetition."
        )
    lines.extend(
        [
            "Use the current observation to choose a concrete action that moves toward task completion.",
            "If a relevant product, required option, or buy now is visible, prefer acting on it instead of continuing navigation.",
            "Do not explain.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def format_hint_for_agent(repair_hint: dict[str, Any]) -> str:
    error_type = repair_hint.get("error_type")
    avoid_action = repair_hint.get("avoid_action")
    post_check = repair_hint.get("post_check") or {}
    policy_decision = repair_hint.get("policy_decision") or {}
    hint_style = repair_hint.get("hint_style") or policy_decision.get("prompt_strength")

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
        body = _loop_hint_body(
            post_check,
            avoid_action,
            hint_style=hint_style,
            policy_decision=policy_decision,
        )
    elif error_type == "budget_pressure":
        body = _budget_finish_hint_body(policy_decision)
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


def _completion_pre_repair_hint(repair_hint: dict[str, Any]) -> str:
    error_type = repair_hint.get("error_type")
    if error_type == "none":
        return ""
    avoid_action = action_to_avoid(repair_hint)
    lines = [
        "Risk-control hint for this action:",
        "The candidate action was verified as a stalled product/option repeat with no visible progress.",
        "Buy Now is visible in the current observation.",
    ]
    if avoid_action:
        lines.append(f"Do not output this same stalled local action again: {avoid_action}.")
    lines.extend(
        [
            "Your next response must be exactly one valid action.",
            "If the required options are already selected, output click[buy now].",
            "Otherwise choose a visible required option instead of reopening the same product id.",
            "Do not explain.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def _late_budget_pre_repair_hint(repair_hint: dict[str, Any]) -> str:
    error_type = repair_hint.get("error_type")
    if error_type == "none":
        return ""
    avoid_action = action_to_avoid(repair_hint)
    lines = [
        "Risk-control hint for this action:",
        "The step budget is almost exhausted, so avoid low-value repetition.",
    ]
    if avoid_action:
        lines.append(f"Do not output this same risky action again: {avoid_action}.")
    lines.extend(
        [
            "Choose exactly one valid action that is most likely to finish or directly advance the task now.",
            "If a valid finalization, verification, or commit action is available and the requirements appear satisfied, use it.",
            "Do not explain.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def _task_aware_pre_repair_hint(repair_hint: dict[str, Any], late: bool = False) -> str:
    error_type = repair_hint.get("error_type")
    if error_type == "none":
        return ""
    avoid_action = action_to_avoid(repair_hint)
    policy_decision = repair_hint.get("policy_decision") or {}
    lines = [
        "Risk-control hint for this action:",
        "Task-local checklist before choosing the next action:",
        "1. Re-read the task goal and identify one still-unsatisfied requirement.",
        "2. Use only the current observation, available actions, and confirmed evidence.",
        "3. Choose a valid action that directly satisfies, verifies, or advances that requirement.",
    ]
    if late:
        remaining_steps = policy_decision.get("remaining_steps")
        if isinstance(remaining_steps, int) and remaining_steps > 0:
            lines.append(f"You have {remaining_steps} action(s) left, so prefer a finishing or directly advancing action.")
        else:
            lines.append("The step budget is tight, so prefer a finishing or directly advancing action.")
    completion_line = _completion_candidate_line(policy_decision)
    if completion_line:
        lines.append(completion_line)
    if avoid_action:
        lines.append(f"Do not repeat this risky action unless it is the only valid completing action: {avoid_action}.")
    lines.extend(
        [
            "Do not explain.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def _loop_hint_body(
    post_check: dict[str, Any],
    avoid_action: Any,
    hint_style: str | None = None,
    policy_decision: dict[str, Any] | None = None,
) -> str:
    if hint_style == "completion":
        return _completion_loop_hint_body(avoid_action)
    if hint_style == "finish_guarded":
        return _guarded_completion_loop_hint_body(avoid_action, policy_decision or {})
    if hint_style == "late":
        return _late_budget_loop_hint_body(avoid_action, policy_decision or {})
    if hint_style == "task_soft":
        return _task_soft_loop_hint_body(avoid_action, policy_decision or {})
    if hint_style in {"task", "task_late"}:
        return _task_aware_loop_hint_body(
            avoid_action,
            policy_decision or {},
            late=hint_style == "task_late",
        )
    if hint_style == "soft":
        return _soft_local_loop_hint_body(avoid_action)
    if post_check.get("repeated_behavior_risk") is True:
        lines = [
            "The previous behavior was verified as repeated exploration.",
            "Do not continue the same action or strategy.",
        ]
        if avoid_action:
            lines.append(f"Avoid repeating this action: {avoid_action}.")
        lines.extend(
            [
                "Use the current observation to choose one concrete action that changes state or tests a better-supported candidate.",
                "Do not choose a completion or commit action unless the observation clearly satisfies the task requirements.",
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


def _budget_finish_hint_body(policy_decision: dict[str, Any]) -> str:
    finalization_type = str(policy_decision.get("finalization_type") or "last_gap")
    lines = [
        "The step budget is almost exhausted.",
        "Do not start broad exploration.",
    ]
    completion_line = _completion_candidate_line(policy_decision)
    if completion_line:
        lines.append(completion_line)
    if finalization_type == "verify":
        lines.append("If a small validation, test, or check action can verify success, choose it now.")
    elif finalization_type == "deliverable":
        lines.append("If a required file, output, or deliverable is missing, create or save it now.")
    elif finalization_type == "commit":
        lines.append("If the task requirements appear satisfied and a valid finalization action is available, use it.")
    else:
        lines.append("Choose one valid action that closes the most specific remaining gap.")
    lines.extend(
        [
            "If the task requirements already appear satisfied, prefer finalizing or verifying over further exploration.",
            "Otherwise choose one valid action that directly satisfies, verifies, or commits the most specific missing requirement.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def _guarded_completion_loop_hint_body(avoid_action: Any, policy_decision: dict[str, Any]) -> str:
    lines = [
        "The previous action repeated without visible progress.",
    ]
    completion_line = _completion_candidate_line(policy_decision)
    if completion_line:
        lines.append(completion_line)
    if avoid_action:
        lines.append(f"Do not repeat this stalled action unless it is the only valid completing action: {avoid_action}.")
    lines.extend(
        [
            "If the current observation clearly satisfies the task requirements, choose the available finalization action.",
            "Otherwise choose one valid action that satisfies, verifies, or commits a missing requirement.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def _completion_loop_hint_body(avoid_action: Any) -> str:
    lines = [
        "The previous product or option action repeated without visible progress.",
        "Buy Now is visible in the current observation.",
    ]
    if avoid_action:
        lines.append(f"Do not keep reopening this same stalled action: {avoid_action}.")
    lines.extend(
        [
            "If the required options are already selected, choose click[buy now].",
            "Otherwise choose a visible required option that is still missing.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def _late_budget_loop_hint_body(avoid_action: Any, policy_decision: dict[str, Any]) -> str:
    remaining_steps = policy_decision.get("remaining_steps")
    lines = [
        "The previous action was verified as risky or repetitive, and the step budget is almost exhausted.",
    ]
    if isinstance(remaining_steps, int) and remaining_steps > 0:
        lines.append(f"You have {remaining_steps} action(s) left to recover or finish.")
    if avoid_action:
        lines.append(f"Do not repeat this action unless it is the only valid completing action: {avoid_action}.")
    lines.extend(
        [
            "Choose the single valid action most likely to finish the task now.",
            "If a valid finalization, verification, or commit action is available and the requirements appear satisfied, use it.",
            "Otherwise choose one visible non-repeated action that directly advances the task.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def _task_soft_loop_hint_body(avoid_action: Any, policy_decision: dict[str, Any]) -> str:
    lines = [
        "The previous behavior may be low-progress, but it may also be a necessary local repeat.",
        "Before changing strategy, re-check the task goal against the current observation.",
        "If the repeated action is still producing useful evidence or is required to confirm a choice, continue with the best-supported valid action.",
    ]
    if avoid_action:
        lines.append(f"If it no longer produces useful progress, avoid repeating this action: {avoid_action}.")
    task_progress = policy_decision.get("task_progress")
    if task_progress == "no_task_evidence_visible":
        lines.append("Prefer an action that exposes task-relevant evidence over another low-value repeat.")
    completion_line = _completion_candidate_line(policy_decision)
    if completion_line:
        lines.append(completion_line)
    lines.extend(
        [
            "Do not explain.",
            "Output only the action in the required format.",
        ]
    )
    return "\n".join(lines)


def _task_aware_loop_hint_body(
    avoid_action: Any,
    policy_decision: dict[str, Any],
    late: bool = False,
) -> str:
    lines = [
        "The previous behavior was verified as repetitive or low-progress.",
        "Task-local checklist for the next action:",
        "1. Re-check the task goal against the current observation.",
        "2. Pick one visible or valid action that advances an unsatisfied requirement.",
        "3. Avoid switching strategy blindly; only change to a better-supported action.",
    ]
    if late:
        remaining_steps = policy_decision.get("remaining_steps")
        if isinstance(remaining_steps, int) and remaining_steps > 0:
            lines.append(f"You have {remaining_steps} action(s) left, so prioritize finishing or committing if justified.")
        else:
            lines.append("The step budget is tight, so prioritize finishing or committing if justified.")
    completion_line = _completion_candidate_line(policy_decision)
    if completion_line:
        lines.append(completion_line)
    if avoid_action:
        lines.append(f"Do not repeat this action unless it is the only valid completing action: {avoid_action}.")
    lines.append("Output only the action in the required format.")
    return "\n".join(lines)


def _completion_candidate_line(policy_decision: dict[str, Any]) -> str:
    candidates = policy_decision.get("completion_candidates") or []
    if not candidates:
        return ""
    visible = ", ".join(str(item) for item in candidates[:3])
    return (
        "A visible finalization or verification action includes: "
        f"{visible}. Use it only if the task requirements appear satisfied."
    )


def _soft_local_loop_hint_body(avoid_action: Any) -> str:
    lines = [
        "The previous local product or option action may be repeating without useful progress.",
        "Do not force a strategy change if this repeat is still needed to select or confirm an option.",
    ]
    if avoid_action:
        lines.append(f"If this action is no longer changing the page, avoid repeating it: {avoid_action}.")
    lines.extend(
        [
            "Use the current observation to choose the next useful product, option, or completion action.",
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


def action_to_avoid(repair_hint: dict[str, Any]) -> str | None:
    return _action_text(repair_hint.get("avoid_action") or repair_hint.get("action_under_check"))


def _action_text(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("raw")
    if value is None:
        return None
    text = str(value).strip()
    return text or None
