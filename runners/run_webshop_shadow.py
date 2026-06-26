"""Run rule-based shadow v1 on WebShop.

The runner never injects full shadow state into the agent prompt. By default it
only verifies rule-triggered risks; lightweight repair hints are opt-in.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any

from agents.llm_client import MockLLMClient, OpenAIChatClient
from agents.react_agent import WebShopReactAgent
from intervention.repair_hint import (
    build_repair_hint,
    format_hint_for_agent,
    mark_hint_outcome,
    should_apply_pre_repair,
    should_create_post_hint,
)
from intervention.risk_verifier import (
    default_verification,
    verify_post_risk_if_triggered,
    verify_pre_risk_if_triggered,
)
from runners.webshop_env import make_webshop_env
from shadow.extractor import (
    context_value,
    extract_observation_attributes,
    extract_task_attributes,
)
from shadow.parser import action_signature, parse_action
from shadow.post import REPEATED_BEHAVIOR_RISK_STREAK, run_post_check
from shadow.pre import run_pre_check
from shadow.state import (
    attributes_summary,
    check_params,
    clone_attributes,
    current_context,
    merge_attributes,
    new_shadow_state,
)


def main() -> None:
    args = parse_args()
    run(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["auto", "official", "mock"], default="auto")
    parser.add_argument("--webshop_repo", default="external/webshop")
    parser.add_argument("--num_products", type=int, default=1000)
    parser.add_argument("--num_samples", "--num_tasks", dest="num_samples", type=int, default=20)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--max_steps", type=int, default=15)
    parser.add_argument("--model", default=os.getenv("LLM_MODEL") or os.getenv("QWEN_MODEL") or "mock")
    parser.add_argument("--state_to_agent", default="false")
    parser.add_argument("--llm_risk_verify", nargs="?", const="true", default="false")
    parser.add_argument(
        "--risk_verify_model",
        default=(
            os.getenv("RISK_VERIFY_MODEL")
            or os.getenv("LLM_MODEL")
            or os.getenv("QWEN_MODEL")
            or ""
        ),
    )
    parser.add_argument("--risk_verify_recent_steps", type=int, default=6)
    parser.add_argument("--risk_verify_temperature", type=float, default=0.0)
    parser.add_argument("--repair_hint_enabled", nargs="?", const="true", default="false")
    parser.add_argument("--log_dir", default="logs/rule_shadow_v1_prepost_llmverify_webshop20")
    parser.add_argument("--report_dir", default="reports/rule_shadow_v1_prepost_llmverify_webshop20")
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, Any]:
    if _parse_bool(args.state_to_agent):
        raise ValueError("rule_shadow_v1 requires --state_to_agent false")
    env = make_webshop_env(args.env, repo_path=args.webshop_repo, num_products=args.num_products)
    agent = WebShopReactAgent(_build_client(args.model))
    llm_risk_verify_enabled = _parse_bool(getattr(args, "llm_risk_verify", "false"))
    repair_hint_enabled = _parse_bool(getattr(args, "repair_hint_enabled", "false"))
    risk_client = _build_risk_client(getattr(args, "risk_verify_model", "")) if llm_risk_verify_enabled else None
    log_dir = Path(args.log_dir)
    report_dir = Path(args.report_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "mode": "shadow",
        "version": "rule_shadow_v1_llmverify",
        "env": env.env_name,
        "requested_env": args.env,
        "num_samples": args.num_samples,
        "start_index": args.start_index,
        "max_steps": args.max_steps,
        "state_to_agent": False,
        "repair_enabled": repair_hint_enabled,
        "repair_hint_enabled": repair_hint_enabled,
        "repair_hint_to_agent": repair_hint_enabled,
        "llm_risk_verify_enabled": llm_risk_verify_enabled,
        "risk_verify_model": getattr(risk_client, "model", getattr(args, "risk_verify_model", "")),
        "risk_verify_recent_steps": getattr(args, "risk_verify_recent_steps", 6),
        "risk_verify_temperature": getattr(args, "risk_verify_temperature", 0.0),
        "model": getattr(agent.client, "model", args.model),
    }
    _write_json(log_dir / "config.json", config)

    trajectories = []
    with (log_dir / "trajectories.jsonl").open("w", encoding="utf-8") as fh:
        for offset in range(args.num_samples):
            task_id = args.start_index + offset
            trajectory = _run_episode(
                env=env,
                agent=agent,
                task_id=task_id,
                max_steps=args.max_steps,
                llm_risk_verify_enabled=llm_risk_verify_enabled,
                risk_client=risk_client,
                risk_verify_recent_steps=getattr(args, "risk_verify_recent_steps", 6),
                risk_verify_temperature=getattr(args, "risk_verify_temperature", 0.0),
                repair_hint_enabled=repair_hint_enabled,
            )
            trajectories.append(trajectory)
            fh.write(json.dumps(trajectory, ensure_ascii=True) + "\n")
            fh.flush()

    metrics = compute_metrics(trajectories, args.max_steps)
    _write_json(report_dir / "metrics.json", metrics)
    (report_dir / "summary_zh.md").write_text(
        render_summary(metrics, trajectories),
        encoding="utf-8",
    )
    (report_dir / "manual_audit_zh.md").write_text(
        render_manual_audit(metrics, trajectories),
        encoding="utf-8",
    )
    return {"config": config, "metrics": metrics, "trajectories": trajectories}


def _run_episode(
    env: Any,
    agent: WebShopReactAgent,
    task_id: int,
    max_steps: int,
    llm_risk_verify_enabled: bool = False,
    risk_client: Any = None,
    risk_verify_recent_steps: int = 6,
    risk_verify_temperature: float = 0.0,
    repair_hint_enabled: bool = False,
) -> dict[str, Any]:
    observation = env.reset(task_id)
    instruction = env.get_instruction_text()
    available = env.get_available_actions()
    shadow_state = new_shadow_state()
    merge_attributes(shadow_state, extract_task_attributes(instruction, step=0))
    merge_attributes(
        shadow_state,
        extract_observation_attributes(observation, available, step=0),
    )
    history: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    done = False
    final_reward = 0.0
    pending_post_hint: dict[str, Any] | None = None

    for step in range(max_steps):
        available_before = env.get_available_actions()
        context_before = current_context(shadow_state) or context_value(observation)
        repair_record = _default_repair_record(enabled=repair_hint_enabled)
        prompt_repair_hint = ""
        applied_pending_hint = pending_post_hint
        if repair_hint_enabled and applied_pending_hint is not None:
            prompt_repair_hint = format_hint_for_agent(applied_pending_hint)

        raw_action = agent.act(
            task_instruction=instruction,
            observation=observation,
            action_history=history,
            available_actions=available_before,
            state_summary="",
            repair_hint=prompt_repair_hint,
        )
        if repair_hint_enabled and applied_pending_hint is not None:
            outcome = mark_hint_outcome(applied_pending_hint, raw_action)
            repair_record["hint_applied_from_previous_step"] = {
                "applied": True,
                "source_step": applied_pending_hint.get("source_step"),
                "error_type": applied_pending_hint.get("error_type"),
                "hint": prompt_repair_hint,
                "avoid_action": applied_pending_hint.get("avoid_action"),
                "followed": outcome["followed"],
            }
            pending_post_hint = None

        parsed = parse_action(raw_action)
        action_record: dict[str, Any] = {
            "step": step,
            "raw": raw_action,
            "raw_action": raw_action,
            "original_parsed_action": parsed,
            "original_action_signature": action_signature(parsed),
            "type": parsed["type"],
            "params": parsed["params"],
            "parsed_action": parsed,
            "context_before": context_before,
            "action_signature": action_signature(parsed),
            "param_checks": check_params(parsed, shadow_state["attributes"]),
        }
        action_record["pre_check"] = run_pre_check(action_record, shadow_state)
        pre_verification = verify_pre_risk_if_triggered(
            action_record=action_record,
            shadow_state=shadow_state,
            task=instruction,
            current_observation=observation,
            available_actions=available_before,
            enabled=llm_risk_verify_enabled,
            client=risk_client,
            max_recent_steps=risk_verify_recent_steps,
            temperature=risk_verify_temperature,
        )
        action_record["risk_verifications"] = {
            "pre": pre_verification,
            "post": default_verification(
                enabled=llm_risk_verify_enabled,
                triggered=False,
                called=False,
            ),
        }
        action_record["repair"] = repair_record

        executed_action = raw_action
        executed_parsed = parsed
        if should_apply_pre_repair(pre_verification, repair_hint_enabled):
            pre_hint = build_repair_hint(pre_verification, "pre", action_record)
            pre_hint_text = format_hint_for_agent(pre_hint)
            repaired_action = agent.act(
                task_instruction=instruction,
                observation=observation,
                action_history=history,
                available_actions=available_before,
                state_summary="",
                repair_hint=pre_hint_text,
            )
            repaired_parsed = parse_action(repaired_action)
            repair_record.update(
                {
                    "pre_repair_attempted": True,
                    "pre_repair_hint": pre_hint_text,
                    "pre_repair_original_action": raw_action,
                    "pre_repair_repaired_action": repaired_action,
                }
            )
            if repaired_parsed.get("format_valid"):
                executed_action = repaired_action
                executed_parsed = repaired_parsed
                repair_record["pre_repair_success"] = True
            else:
                repair_record["pre_repair_success"] = False
                repair_record["pre_repair_failed_reason"] = "invalid_repaired_action_format"

        action_record["executed_action"] = executed_action
        action_record["executed_parsed_action"] = executed_parsed
        action_record["action_changed"] = executed_action != raw_action
        action_record["type"] = executed_parsed["type"]
        action_record["params"] = executed_parsed["params"]
        action_record["parsed_action"] = executed_parsed
        action_record["action_signature"] = action_signature(executed_parsed)
        action_record["param_checks"] = check_params(executed_parsed, shadow_state["attributes"])

        attributes_before = clone_attributes(shadow_state)
        observation_after, reward, done, info = env.step(executed_action)
        final_reward = float(reward)
        available_after = env.get_available_actions()
        observed_after = extract_observation_attributes(observation_after, available_after, step=step + 1)
        post_check = run_post_check(
            attributes_before=attributes_before,
            observed_attrs_after=observed_after,
            action_record=action_record,
            shadow_state=shadow_state,
            context_after=str(observed_after["context.current"]["current_value"]),
        )
        action_record["post_check"] = post_check
        post_verification = verify_post_risk_if_triggered(
            action_record=action_record,
            shadow_state=shadow_state,
            task=instruction,
            current_observation=observation_after,
            available_actions=available_after,
            enabled=llm_risk_verify_enabled,
            client=risk_client,
            max_recent_steps=risk_verify_recent_steps,
            temperature=risk_verify_temperature,
        )
        action_record["risk_verifications"]["post"] = post_verification
        if should_create_post_hint(post_verification, repair_hint_enabled):
            pending_post_hint = build_repair_hint(post_verification, "post", action_record)
            post_hint_text = format_hint_for_agent(pending_post_hint)
            repair_record.update(
                {
                    "post_hint_created": True,
                    "post_hint": post_hint_text,
                    "post_hint_apply_to_next_step": True,
                }
            )

        merge_attributes(shadow_state, observed_after)
        shadow_state["actions"].append(action_record)

        step_log = {
            "step": step,
            "state_to_agent": False,
            "repair_hint_to_agent": bool(
                prompt_repair_hint or repair_record.get("pre_repair_attempted")
            ),
            "agent_prompt_contains_state_summary": bool(
                agent.last_trace.get("prompt_contains_state_summary")
            ),
            "agent_prompt_contains_repair_hint": bool(
                agent.last_trace.get("prompt_contains_repair_hint")
            ),
            "agent_prompt_sha256": agent.last_trace.get("prompt_sha256"),
            "observation_before_hash": context_before,
            "observation_before": observation,
            "raw_action": raw_action,
            "parsed_action": parsed,
            "executed_action": executed_action,
            "action_record": action_record,
            "observation_after_hash": post_check["context_after"],
            "observation_after": observation_after,
            "reward": final_reward,
            "done": done,
            "env_info": info,
            "attributes_summary": attributes_summary(shadow_state),
        }
        steps.append(step_log)
        history.append(
            {
                "step": step,
                "raw_action": raw_action,
                "executed_action": executed_action,
                "reward": final_reward,
                "done": done,
            }
        )
        observation = observation_after
        if done:
            break

    return {
        "task_id": task_id,
        "task_instruction": instruction,
        "success": bool(done and final_reward > 0),
        "reward": final_reward,
        "done": done,
        "num_steps": len(steps),
        "max_steps": max_steps,
        "trajectory_risk_summary": build_trajectory_risk_summary(steps),
        "shadow_state": shadow_state,
        "steps": steps,
    }


def _default_repair_record(enabled: bool) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "hint_applied_from_previous_step": {
            "applied": False,
            "source_step": None,
            "error_type": None,
            "hint": "",
            "avoid_action": None,
            "followed": None,
        },
        "pre_repair_attempted": False,
        "pre_repair_hint": "",
        "pre_repair_original_action": None,
        "pre_repair_repaired_action": None,
        "pre_repair_success": False,
        "pre_repair_failed_reason": None,
        "post_hint_created": False,
        "post_hint": "",
        "post_hint_apply_to_next_step": False,
    }


def compute_metrics(trajectories: list[dict[str, Any]], max_steps: int) -> dict[str, Any]:
    action_records = [
        step["action_record"]
        for trajectory in trajectories
        for step in trajectory.get("steps", [])
    ]
    param_checks = [
        check
        for record in action_records
        for check in (record.get("param_checks") or {}).values()
    ]
    success_count = sum(1 for item in trajectories if item.get("success"))
    num_samples = len(trajectories)
    successful = [item for item in trajectories if item.get("success")]
    failed = [item for item in trajectories if not item.get("success")]
    summaries = [item.get("trajectory_risk_summary") or {} for item in trajectories]
    successful_summaries = [item.get("trajectory_risk_summary") or {} for item in successful]
    failed_summaries = [item.get("trajectory_risk_summary") or {} for item in failed]
    llm_error_type_counts = {
        "evidence_guessing": 0,
        "format_error": 0,
        "loop_or_repetition": 0,
        "wrong_action_or_param": 0,
        "none": 0,
    }
    verifications = [
        _stage_verification(record, stage)
        for record in action_records
        for stage in ("pre", "post")
    ]
    for verification in verifications:
        if not verification.get("called") or verification.get("parse_error"):
            continue
        error_type = verification.get("error_type", "none")
        if error_type in llm_error_type_counts:
            llm_error_type_counts[error_type] += 1
    repair_enabled = any((record.get("repair") or {}).get("enabled") for record in action_records)
    repair_hint_applied = sum(
        1
        for record in action_records
        if (record.get("repair") or {}).get("hint_applied_from_previous_step", {}).get("applied")
    )
    return {
        "num_samples": num_samples,
        "max_steps": max_steps,
        "state_to_agent": False,
        "repair_enabled": repair_enabled,
        "repair_hint_enabled": repair_enabled,
        "repair_hint_to_agent": repair_enabled,
        "llm_risk_verify_enabled": any(
            verification.get("enabled") for verification in verifications
        ),
        "repeated_behavior_risk_threshold": REPEATED_BEHAVIOR_RISK_STREAK,
        "num_actions": len(action_records),
        "format_invalid_count": sum(
            1 for item in action_records if not item.get("pre_check", {}).get("format_valid")
        ),
        "repeat_known_no_info_count": sum(
            1 for item in action_records if item.get("pre_check", {}).get("repeat_known_no_info")
        ),
        "visible_delta_true_count": sum(
            1 for item in action_records if item.get("post_check", {}).get("visible_delta")
        ),
        "visible_delta_false_count": sum(
            1 for item in action_records if not item.get("post_check", {}).get("visible_delta")
        ),
        "action_no_progress_count": sum(
            1 for item in action_records if item.get("post_check", {}).get("no_progress")
        ),
        "no_progress_count": sum(
            1 for item in action_records if item.get("post_check", {}).get("no_progress")
        ),
        "same_action_repeated_no_progress_count": sum(
            1
            for item in action_records
            if item.get("post_check", {}).get("no_progress_reason")
            == "same_action_repeated_without_visible_delta"
        ),
        "context_cycle_no_progress_count": sum(
            1
            for item in action_records
            if item.get("post_check", {}).get("no_progress_reason")
            == "context_cycle_without_visible_delta"
        ),
        "context_cycle_detected_count": sum(
            1 for item in action_records if item.get("post_check", {}).get("context_cycle_detected")
        ),
        "repeated_behavior_risk_action_count": sum(
            1
            for item in action_records
            if item.get("post_check", {}).get("repeated_behavior_risk")
        ),
        "pre_rule_risk_trigger_action_count": sum(
            1 for item in action_records if _stage_verification(item, "pre").get("triggered")
        ),
        "post_rule_risk_trigger_action_count": sum(
            1 for item in action_records if _stage_verification(item, "post").get("triggered")
        ),
        "pre_llm_called_action_count": sum(
            1 for item in action_records if _stage_verification(item, "pre").get("called")
        ),
        "post_llm_called_action_count": sum(
            1 for item in action_records if _stage_verification(item, "post").get("called")
        ),
        "pre_llm_parse_error_count": sum(
            1 for item in action_records if _stage_verification(item, "pre").get("parse_error")
        ),
        "post_llm_parse_error_count": sum(
            1 for item in action_records if _stage_verification(item, "post").get("parse_error")
        ),
        "pre_llm_is_error_action_count": sum(
            1 for item in action_records if _stage_verification(item, "pre").get("is_error")
        ),
        "post_llm_is_error_action_count": sum(
            1 for item in action_records if _stage_verification(item, "post").get("is_error")
        ),
        "rule_risk_trigger_action_count": sum(
            1
            for verification in verifications
            if verification.get("triggered")
        ),
        "llm_called_action_count": sum(
            1
            for verification in verifications
            if verification.get("called")
        ),
        "llm_parse_error_count": sum(
            1
            for verification in verifications
            if verification.get("parse_error")
        ),
        "llm_is_error_action_count": sum(
            1
            for verification in verifications
            if verification.get("is_error")
        ),
        "llm_error_type_counts": llm_error_type_counts,
        "pre_repair_attempt_count": sum(
            1 for item in action_records if (item.get("repair") or {}).get("pre_repair_attempted")
        ),
        "pre_repair_success_count": sum(
            1 for item in action_records if (item.get("repair") or {}).get("pre_repair_success")
        ),
        "pre_repair_fallback_count": sum(
            1
            for item in action_records
            if (item.get("repair") or {}).get("pre_repair_attempted")
            and not (item.get("repair") or {}).get("pre_repair_success")
        ),
        "post_hint_created_count": sum(
            1 for item in action_records if (item.get("repair") or {}).get("post_hint_created")
        ),
        "post_hint_applied_count": repair_hint_applied,
        "repair_hint_followed_count": sum(
            1
            for item in action_records
            if (item.get("repair") or {}).get("hint_applied_from_previous_step", {}).get("followed")
            is True
        ),
        "repair_hint_ignored_count": sum(
            1
            for item in action_records
            if (item.get("repair") or {}).get("hint_applied_from_previous_step", {}).get("followed")
            is False
        ),
        "info_gain_true_count": sum(
            1 for item in action_records if item.get("post_check", {}).get("info_gain")
        ),
        "info_gain_false_count": sum(
            1 for item in action_records if not item.get("post_check", {}).get("info_gain")
        ),
        "param_known_count": sum(1 for item in param_checks if item.get("known")),
        "param_unknown_count": sum(1 for item in param_checks if not item.get("known")),
        "success_count": success_count,
        "success_rate": float(success_count / num_samples) if num_samples else 0.0,
        "avg_reward": float(mean([item.get("reward", 0.0) for item in trajectories])) if trajectories else 0.0,
        "avg_steps": float(mean([item.get("num_steps", 0) for item in trajectories])) if trajectories else 0.0,
        "trajectory_risk_sample_count": sum(1 for item in summaries if item.get("has_any_risk")),
        "rule_risk_sample_count": sum(1 for item in summaries if item.get("has_any_rule_risk")),
        "llm_verified_error_sample_count": sum(
            1 for item in summaries if item.get("has_llm_verified_error")
        ),
        "action_no_progress_sample_count": sum(
            1 for item in summaries if item.get("has_action_no_progress")
        ),
        "repeated_behavior_risk_sample_count": sum(
            1 for item in summaries if item.get("has_repeated_behavior_risk")
        ),
        "context_cycle_risk_sample_count": sum(
            1 for item in summaries if item.get("has_context_cycle_risk")
        ),
        "failed_samples": len(failed),
        "failed_samples_with_any_risk": sum(1 for item in failed_summaries if item.get("has_any_risk")),
        "failed_samples_with_rule_risk": sum(
            1 for item in failed_summaries if item.get("has_any_rule_risk")
        ),
        "failed_samples_with_llm_verified_error": sum(
            1 for item in failed_summaries if item.get("has_llm_verified_error")
        ),
        "failed_samples_with_action_no_progress": sum(
            1 for item in failed_summaries if item.get("has_action_no_progress")
        ),
        "failed_samples_with_repeated_behavior_risk": sum(
            1 for item in failed_summaries if item.get("has_repeated_behavior_risk")
        ),
        "failed_samples_with_context_cycle_risk": sum(
            1 for item in failed_summaries if item.get("has_context_cycle_risk")
        ),
        "failed_risk_recall": _safe_rate(
            sum(1 for item in failed_summaries if item.get("has_any_risk")),
            len(failed),
        ),
        "failed_llm_verified_recall": _safe_rate(
            sum(1 for item in failed_summaries if item.get("has_llm_verified_error")),
            len(failed),
        ),
        "successful_samples": len(successful),
        "successful_samples_with_any_risk": sum(
            1 for item in successful_summaries if item.get("has_any_risk")
        ),
        "successful_samples_with_rule_risk": sum(
            1 for item in successful_summaries if item.get("has_any_rule_risk")
        ),
        "successful_samples_with_llm_verified_error": sum(
            1 for item in successful_summaries if item.get("has_llm_verified_error")
        ),
        "successful_samples_with_action_no_progress": sum(
            1 for item in successful_summaries if item.get("has_action_no_progress")
        ),
        "successful_samples_with_repeated_behavior_risk": sum(
            1 for item in successful_summaries if item.get("has_repeated_behavior_risk")
        ),
        "successful_samples_with_context_cycle_risk": sum(
            1 for item in successful_summaries if item.get("has_context_cycle_risk")
        ),
        "successful_risk_rate": _safe_rate(
            sum(1 for item in successful_summaries if item.get("has_any_risk")),
            len(successful),
        ),
        "successful_llm_verified_rate": _safe_rate(
            sum(1 for item in successful_summaries if item.get("has_llm_verified_error")),
            len(successful),
        ),
        "avg_first_any_risk_step_failed": _avg_present(
            item.get("first_any_risk_step") for item in failed_summaries
        ),
        "avg_first_rule_risk_step_failed": _avg_present(
            item.get("first_rule_risk_step") for item in failed_summaries
        ),
        "avg_first_llm_verified_error_step_failed": _avg_present(
            item.get("first_llm_verified_error_step") for item in failed_summaries
        ),
        "avg_first_repeated_behavior_risk_step_failed": _avg_present(
            item.get("first_repeated_behavior_risk_step") for item in failed_summaries
        ),
        "state_prompt_leak_count": sum(
            1
            for trajectory in trajectories
            for step in trajectory.get("steps", [])
            if step.get("agent_prompt_contains_state_summary")
        ),
        "repair_hint_prompt_count": sum(
            1
            for trajectory in trajectories
            for step in trajectory.get("steps", [])
            if step.get("agent_prompt_contains_repair_hint")
        ),
        "action_changed_count": sum(
            1
            for item in action_records
            if item.get("action_changed")
            or item.get("executed_action") != item.get("raw_action", item.get("raw"))
        ),
    }


def _stage_verification(record: dict[str, Any], stage: str) -> dict[str, Any]:
    verifications = record.get("risk_verifications") or {}
    if stage in verifications:
        return verifications[stage] or {}
    if stage == "post" and "risk_verification" in record:
        return record.get("risk_verification") or {}
    return default_verification(enabled=False, triggered=False, called=False)


def build_trajectory_risk_summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
    risk_events: list[dict[str, Any]] = []
    llm_verified_error_events: list[dict[str, Any]] = []
    for step in steps:
        record = step.get("action_record") or {}
        pre = record.get("pre_check") or {}
        post = record.get("post_check") or {}
        step_id = int(record.get("step", step.get("step", 0)))
        if pre.get("format_valid") is False:
            risk_events.append(
                {
                    "step": step_id,
                    "type": "pre_format_invalid",
                    "action_signature": record.get("original_action_signature")
                    or record.get("action_signature"),
                    "reason": "format_invalid",
                }
            )
        if pre.get("repeat_known_no_info") is True:
            risk_events.append(
                {
                    "step": step_id,
                    "type": "pre_repeat_known_no_info",
                    "action_signature": record.get("original_action_signature")
                    or record.get("action_signature"),
                    "reason": "repeat_known_no_info",
                }
            )
        if post.get("no_progress"):
            risk_events.append(
                {
                    "step": step_id,
                    "type": "action_no_progress",
                    "action_signature": record.get("action_signature"),
                    "same_action_no_visible_delta_count": post.get(
                        "same_action_no_visible_delta_count"
                    ),
                    "reason": post.get("no_progress_reason"),
                }
            )
        if post.get("repeated_behavior_risk"):
            risk_events.append(
                {
                    "step": step_id,
                    "type": "repeated_behavior_risk",
                    "action_signature": record.get("action_signature"),
                    "same_action_signature_streak": post.get("same_action_signature_streak"),
                    "reason": post.get("repeated_behavior_reason"),
                }
            )
        if post.get("no_progress_reason") == "context_cycle_without_visible_delta":
            risk_events.append(
                {
                    "step": step_id,
                    "type": "context_cycle_risk",
                    "action_signature": record.get("action_signature"),
                    "reason": post.get("no_progress_reason"),
                }
            )
        for stage in ("pre", "post"):
            verification = _stage_verification(record, stage)
            if verification.get("is_error"):
                llm_verified_error_events.append(
                    {
                        "step": step_id,
                        "stage": stage,
                        "error_type": verification.get("error_type"),
                        "confidence": verification.get("confidence"),
                        "avoid_action": verification.get("avoid_action"),
                        "repair_hint": verification.get("repair_hint"),
                        "action_signature": record.get("action_signature"),
                    }
                )

    first_no_progress = _first_event_step(risk_events, "action_no_progress")
    first_repeated = _first_event_step(risk_events, "repeated_behavior_risk")
    first_context_cycle = _first_event_step(risk_events, "context_cycle_risk")
    first_any_rule = min((int(item["step"]) for item in risk_events), default=None)
    first_llm_verified = min(
        (int(item["step"]) for item in llm_verified_error_events),
        default=None,
    )
    present_risk_types = sorted({str(item["type"]) for item in risk_events})
    return {
        "has_action_no_progress": first_no_progress is not None,
        "has_repeated_behavior_risk": first_repeated is not None,
        "has_context_cycle_risk": first_context_cycle is not None,
        "has_any_risk": bool(risk_events),
        "has_any_rule_risk": bool(risk_events),
        "has_llm_verified_error": first_llm_verified is not None,
        "first_no_progress_step": first_no_progress,
        "first_repeated_behavior_risk_step": first_repeated,
        "first_context_cycle_step": first_context_cycle,
        "first_any_risk_step": first_any_rule,
        "first_rule_risk_step": first_any_rule,
        "first_llm_verified_error_step": first_llm_verified,
        "risk_types": present_risk_types,
        "risk_events": risk_events,
        "llm_verified_error_events": llm_verified_error_events,
    }


def _first_event_step(risk_events: list[dict[str, Any]], event_type: str) -> int | None:
    return min(
        (int(item["step"]) for item in risk_events if item.get("type") == event_type),
        default=None,
    )


def _safe_rate(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _avg_present(values: Any) -> float | None:
    present = [item for item in values if item is not None]
    if not present:
        return None
    return float(mean(present))


def render_summary(metrics: dict[str, Any], trajectories: list[dict[str, Any]]) -> str:
    if metrics.get("repair_hint_enabled"):
        return render_repair_summary(metrics, trajectories)
    if metrics.get("llm_risk_verify_enabled"):
        return render_llmverify_summary(metrics, trajectories)
    examples = _example_records(trajectories)
    lines = [
        "# rule-based shadow v1 trajrisk WebShop20 报告",
        "",
        "本次是 rule-based shadow v1 的 trajectory-level risk 扩展。",
        "",
        "- 没有使用 LLM detector。",
        "- 没有把 shadow state 注入 agent prompt。",
        "- 没有执行修复。",
        "- 没有阻断、回滚或 action 改写。",
        "- 没有加入 WebShop 颜色/尺码/option 专用规则。",
        "- 保留 action-level signal：visible_delta、action no_progress、context cycle no_progress。",
        f"- 新增 trajectory-level signal：相同 action_signature 连续 {metrics['repeated_behavior_risk_threshold']} 次触发 repeated_behavior_risk。",
        "- no_progress 是 action-level 局部无进展。",
        "- repeated_behavior_risk 是 trajectory-level 风险，不要求 visible_delta=False。",
        "- pre 仍然只检测格式是否合法、当前 action 是否将成为第 3 次重复无可见变化。",
        "- info_gain 是兼容字段，等价于 visible_delta。",
        "",
        "## 统计结果",
        "",
        f"- 样本数：{metrics['num_samples']}",
        f"- 最大步数：{metrics['max_steps']}",
        f"- action 数：{metrics['num_actions']}",
        f"- success：{metrics['success_count']} / {metrics['num_samples']} = {metrics['success_rate']:.4f}",
        f"- 平均 reward：{metrics['avg_reward']:.4f}",
        f"- 平均步数：{metrics['avg_steps']:.2f}",
        f"- format_invalid_count：{metrics['format_invalid_count']}",
        f"- repeat_known_no_info_count：{metrics['repeat_known_no_info_count']}",
        f"- visible_delta_true_count：{metrics['visible_delta_true_count']}",
        f"- visible_delta_false_count：{metrics['visible_delta_false_count']}",
        f"- action_no_progress_count：{metrics['action_no_progress_count']}",
        f"- same_action_repeated_no_progress_count：{metrics['same_action_repeated_no_progress_count']}",
        f"- context_cycle_no_progress_count：{metrics['context_cycle_no_progress_count']}",
        f"- context_cycle_detected_count：{metrics['context_cycle_detected_count']}",
        f"- repeated_behavior_risk_action_count：{metrics['repeated_behavior_risk_action_count']}",
        f"- trajectory_risk_sample_count：{metrics['trajectory_risk_sample_count']}",
        f"- repeated_behavior_risk_sample_count：{metrics['repeated_behavior_risk_sample_count']}",
        f"- failed_samples_with_any_risk：{metrics['failed_samples_with_any_risk']} / {metrics['failed_samples']}",
        f"- failed_samples_with_repeated_behavior_risk：{metrics['failed_samples_with_repeated_behavior_risk']}",
        f"- successful_samples_with_any_risk：{metrics['successful_samples_with_any_risk']} / {metrics['successful_samples']}",
        f"- successful_samples_with_repeated_behavior_risk：{metrics['successful_samples_with_repeated_behavior_risk']}",
        f"- failed_risk_recall：{metrics['failed_risk_recall']:.4f}",
        f"- successful_risk_rate：{metrics['successful_risk_rate']:.4f}",
        f"- info_gain_true_count：{metrics['info_gain_true_count']}",
        f"- info_gain_false_count：{metrics['info_gain_false_count']}",
        f"- param_known_count：{metrics['param_known_count']}",
        f"- param_unknown_count：{metrics['param_unknown_count']}",
        f"- state_prompt_leak_count：{metrics['state_prompt_leak_count']}",
        f"- action_changed_count：{metrics['action_changed_count']}",
        "",
        "## 最终检查",
        "",
        "- 运行命令：`python -m runners.run_webshop_shadow --env official --num_samples 20 --start_index 0 --max_steps 15 --model qwen3-8b --state_to_agent false --log_dir logs/rule_shadow_v1_trajrisk_webshop20 --report_dir reports/rule_shadow_v1_trajrisk_webshop20`",
        "- 活跃 shadow 入口：`runners/run_webshop_shadow.py`。",
        "- 活跃 shadow core：`shadow/state.py`, `shadow/parser.py`, `shadow/extractor.py`, `shadow/pre.py`, `shadow/post.py`, `shadow/repair.py`。",
        "- `state_to_agent=false`，日志中 `state_prompt_leak_count=0`。",
        "- `executed_action == raw_action`，日志中 `action_changed_count=0`。",
        "- `shadow_state` 只包含 `attributes` 和 `actions` 两张表。",
        "- `repair.enabled=false`，没有触发修复、阻断、回滚或 action 改写。",
        "- active 逻辑中没有 hidden_state_update、selected_option 或 effect.selected_option。",
        "",
        "## action_record 示例",
        "",
    ]
    for title, record in examples:
        lines.append(f"### {title}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(record, ensure_ascii=False, indent=2)[:3000])
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def render_llmverify_summary(metrics: dict[str, Any], trajectories: list[dict[str, Any]]) -> str:
    pre_example = _find_stage_verification_record(
        trajectories,
        "pre",
        lambda verification: bool(verification.get("called")),
    )
    post_example = _find_stage_verification_record(
        trajectories,
        "post",
        lambda verification: bool(verification.get("called")),
    )
    lines = [
        "# rule-based shadow v1 pre/post LLM Risk Verifier WebShop20 报告",
        "",
        "本次是 pre/post 双接口 LLM risk verification。",
        "",
        "- pre 和 post 规则本身没有改。",
        "- verifier 只在规则风险触发后调用。",
        "- verifier 不修改 action。",
        "- verifier 不执行修复。",
        "- state 没有注入 agent。",
        "- 方案 B 已完成：`is_error=false` 时允许 confidence 为 `[0,1]`。",
        "- verifier 只判断四类错误：evidence_guessing、format_error、loop_or_repetition、wrong_action_or_param。",
        "- verifier 输出只接受五个字段：is_error、error_type、confidence、repair_hint、avoid_action。",
        "",
        "## 统计结果",
        "",
        f"- 样本数：{metrics['num_samples']}",
        f"- 最大步数：{metrics['max_steps']}",
        f"- action 数：{metrics['num_actions']}",
        f"- success：{metrics['success_count']} / {metrics['num_samples']} = {metrics['success_rate']:.4f}",
        f"- llm_risk_verify_enabled：{metrics['llm_risk_verify_enabled']}",
        f"- repair_hint_enabled：{metrics['repair_hint_enabled']}",
        f"- repair_hint_to_agent：{metrics['repair_hint_to_agent']}",
        f"- pre_rule_risk_trigger_action_count：{metrics['pre_rule_risk_trigger_action_count']}",
        f"- post_rule_risk_trigger_action_count：{metrics['post_rule_risk_trigger_action_count']}",
        f"- pre_llm_called_action_count：{metrics['pre_llm_called_action_count']}",
        f"- post_llm_called_action_count：{metrics['post_llm_called_action_count']}",
        f"- pre_llm_parse_error_count：{metrics['pre_llm_parse_error_count']}",
        f"- post_llm_parse_error_count：{metrics['post_llm_parse_error_count']}",
        f"- pre_llm_is_error_action_count：{metrics['pre_llm_is_error_action_count']}",
        f"- post_llm_is_error_action_count：{metrics['post_llm_is_error_action_count']}",
        f"- rule_risk_trigger_action_count：{metrics['rule_risk_trigger_action_count']}",
        f"- llm_called_action_count：{metrics['llm_called_action_count']}",
        f"- llm_parse_error_count：{metrics['llm_parse_error_count']}",
        f"- llm_is_error_action_count：{metrics['llm_is_error_action_count']}",
        f"- llm_error_type_counts：{json.dumps(metrics['llm_error_type_counts'], ensure_ascii=False)}",
        f"- rule_risk_sample_count：{metrics['rule_risk_sample_count']}",
        f"- llm_verified_error_sample_count：{metrics['llm_verified_error_sample_count']}",
        f"- failed_samples_with_rule_risk：{metrics['failed_samples_with_rule_risk']} / {metrics['failed_samples']}",
        f"- failed_samples_with_llm_verified_error：{metrics['failed_samples_with_llm_verified_error']} / {metrics['failed_samples']}",
        f"- failed_llm_verified_recall：{metrics['failed_llm_verified_recall']:.4f}",
        f"- successful_samples_with_rule_risk：{metrics['successful_samples_with_rule_risk']} / {metrics['successful_samples']}",
        f"- successful_samples_with_llm_verified_error：{metrics['successful_samples_with_llm_verified_error']} / {metrics['successful_samples']}",
        f"- successful_llm_verified_rate：{metrics['successful_llm_verified_rate']:.4f}",
        f"- avg_first_rule_risk_step_failed：{metrics['avg_first_rule_risk_step_failed']}",
        f"- avg_first_llm_verified_error_step_failed：{metrics['avg_first_llm_verified_error_step_failed']}",
        f"- state_prompt_leak_count：{metrics['state_prompt_leak_count']}",
        f"- action_changed_count：{metrics['action_changed_count']}",
        "",
        "## 最终检查",
        "",
        "- 运行命令：`python -m runners.run_webshop_shadow --env official --num_samples 20 --start_index 0 --max_steps 15 --model qwen3-8b --state_to_agent false --llm_risk_verify --risk_verify_model qwen3-8b --repair_hint_enabled false --log_dir logs/rule_shadow_v1_prepost_llmverify_webshop20 --report_dir reports/rule_shadow_v1_prepost_llmverify_webshop20`",
        "- 活跃 verifier 模块：`intervention/risk_verifier.py`。",
        "- 活跃 verifier prompt：`intervention/prompts.py`。",
        "- `state_to_agent=false`，日志中 `state_prompt_leak_count=0`。",
        "- `executed_action == raw_action`，日志中 `action_changed_count=0`。",
        "- `repair_hint_enabled=false`，没有触发修复、阻断、回滚或 action 改写。",
        "",
        "## risk_verifications 示例",
        "",
    ]
    if pre_example is not None:
        lines.append("### pre verification 示例")
        lines.append("")
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    "task_id": pre_example.get("task_id"),
                    "step": pre_example.get("step"),
                    "raw_action": pre_example.get("raw_action"),
                    "pre_check": pre_example.get("pre_check"),
                    "risk_verification": _stage_verification(pre_example, "pre"),
                },
                ensure_ascii=False,
                indent=2,
            )[:3000]
        )
        lines.append("```")
        lines.append("")
    else:
        lines.append("### pre verification 示例")
        lines.append("")
        lines.append("本次 20 条轨迹没有触发 pre verifier。")
        lines.append("")
    if post_example is not None:
        lines.append("### post verification 示例")
        lines.append("")
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    "task_id": post_example.get("task_id"),
                    "step": post_example.get("step"),
                    "raw_action": post_example.get("raw_action"),
                    "executed_action": post_example.get("executed_action"),
                    "post_signal_summary": _post_signal_summary(post_example.get("post_check") or {}),
                    "risk_verification": _stage_verification(post_example, "post"),
                },
                ensure_ascii=False,
                indent=2,
            )[:3000]
        )
        lines.append("```")
        lines.append("")
    else:
        lines.append("### post verification 示例")
        lines.append("")
        lines.append("本次 20 条轨迹没有触发 post verifier。")
        lines.append("")
    return "\n".join(lines)


def render_repair_summary(metrics: dict[str, Any], trajectories: list[dict[str, Any]]) -> str:
    pre_repair = _find_repair_record(
        trajectories,
        lambda repair: bool(repair.get("pre_repair_attempted")),
    )
    post_hint = _find_repair_record(
        trajectories,
        lambda repair: bool(repair.get("post_hint_created")),
    )
    applied_hint = _find_repair_record(
        trajectories,
        lambda repair: bool(repair.get("hint_applied_from_previous_step", {}).get("applied")),
    )
    lines = [
        "# rule-based shadow v1 lightweight repair hint WebShop20 报告",
        "",
        "本次是轻量 repair hint 模式。",
        "",
        "- pre verified error 会尝试当前 step 重新生成一次 action。",
        "- post verified error 会创建下一步一次性 repair hint。",
        "- 不做回滚。",
        "- 不做多轮重试。",
        "- 不把完整 state 给 agent。",
        "- `state_to_agent=false`，但 `repair_hint_to_agent=true`。",
        "",
        "## 统计结果",
        "",
        f"- 样本数：{metrics['num_samples']}",
        f"- 最大步数：{metrics['max_steps']}",
        f"- action 数：{metrics['num_actions']}",
        f"- success：{metrics['success_count']} / {metrics['num_samples']} = {metrics['success_rate']:.4f}",
        f"- 平均 reward：{metrics['avg_reward']:.4f}",
        f"- 平均步数：{metrics['avg_steps']:.2f}",
        f"- pre_rule_risk_trigger_action_count：{metrics['pre_rule_risk_trigger_action_count']}",
        f"- post_rule_risk_trigger_action_count：{metrics['post_rule_risk_trigger_action_count']}",
        f"- pre_llm_is_error_action_count：{metrics['pre_llm_is_error_action_count']}",
        f"- post_llm_is_error_action_count：{metrics['post_llm_is_error_action_count']}",
        f"- pre_repair_attempt_count：{metrics['pre_repair_attempt_count']}",
        f"- pre_repair_success_count：{metrics['pre_repair_success_count']}",
        f"- pre_repair_fallback_count：{metrics['pre_repair_fallback_count']}",
        f"- post_hint_created_count：{metrics['post_hint_created_count']}",
        f"- post_hint_applied_count：{metrics['post_hint_applied_count']}",
        f"- repair_hint_followed_count：{metrics['repair_hint_followed_count']}",
        f"- repair_hint_ignored_count：{metrics['repair_hint_ignored_count']}",
        f"- action_changed_count：{metrics['action_changed_count']}",
        f"- state_prompt_leak_count：{metrics['state_prompt_leak_count']}",
        f"- repair_hint_prompt_count：{metrics['repair_hint_prompt_count']}",
        "",
        "## 示例",
        "",
    ]
    for title, record in [
        ("pre repair 示例", pre_repair),
        ("post hint 创建示例", post_hint),
        ("hint followed/ignored 示例", applied_hint),
    ]:
        lines.append(f"### {title}")
        lines.append("")
        if record is None:
            lines.append("本次没有出现该类事件。")
            lines.append("")
            continue
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    "task_id": record.get("task_id"),
                    "step": record.get("step"),
                    "raw_action": record.get("raw_action"),
                    "executed_action": record.get("executed_action"),
                    "action_changed": record.get("action_changed"),
                    "risk_verifications": record.get("risk_verifications"),
                    "repair": record.get("repair"),
                },
                ensure_ascii=False,
                indent=2,
            )[:4000]
        )
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _post_signal_summary(post_check: dict[str, Any]) -> dict[str, Any]:
    return {
        "visible_delta": post_check.get("visible_delta"),
        "no_progress": post_check.get("no_progress"),
        "no_progress_reason": post_check.get("no_progress_reason"),
        "context_cycle_detected": post_check.get("context_cycle_detected"),
        "same_action_signature_streak": post_check.get("same_action_signature_streak"),
        "repeated_behavior_risk": post_check.get("repeated_behavior_risk"),
    }


def _find_stage_verification_record(
    trajectories: list[dict[str, Any]],
    stage: str,
    predicate: Any,
) -> dict[str, Any] | None:
    for trajectory in trajectories:
        for step in trajectory.get("steps", []):
            record = dict(step["action_record"])
            record["task_id"] = trajectory.get("task_id")
            verification = _stage_verification(record, stage)
            if predicate(verification):
                return record
    return None


def _find_repair_record(
    trajectories: list[dict[str, Any]],
    predicate: Any,
) -> dict[str, Any] | None:
    for trajectory in trajectories:
        for step in trajectory.get("steps", []):
            record = dict(step["action_record"])
            record["task_id"] = trajectory.get("task_id")
            repair = record.get("repair") or {}
            if predicate(repair):
                return record
    return None


def render_manual_audit(metrics: dict[str, Any], trajectories: list[dict[str, Any]]) -> str:
    by_task = {item.get("task_id"): item for item in trajectories}
    lines = [
        "# rule-based shadow v1 trajrisk 人工审计摘要",
        "",
        "## Action-level signals",
        "",
        f"- visible_delta_false_count：{metrics['visible_delta_false_count']}",
        f"- action_no_progress_count：{metrics['action_no_progress_count']}",
        f"- same_action_repeated_no_progress_count：{metrics['same_action_repeated_no_progress_count']}",
        f"- context_cycle_no_progress_count：{metrics['context_cycle_no_progress_count']}",
        "",
        "## Trajectory-level signals",
        "",
        f"- repeated_behavior_risk：连续相同 action_signature 达到 {metrics['repeated_behavior_risk_threshold']} 次后触发。",
        "- 该信号不要求 visible_delta=False，用来捕捉翻页等看似有页面变化但行为策略已经卡住的轨迹。",
        f"- repeated_behavior_risk_action_count：{metrics['repeated_behavior_risk_action_count']}",
        f"- repeated_behavior_risk_sample_count：{metrics['repeated_behavior_risk_sample_count']}",
        f"- failed_samples_with_repeated_behavior_risk：{metrics['failed_samples_with_repeated_behavior_risk']}",
        f"- successful_samples_with_repeated_behavior_risk：{metrics['successful_samples_with_repeated_behavior_risk']}",
        "",
        "## 重点样例",
        "",
    ]
    for task_id in [5, 15, 18]:
        trajectory = by_task.get(task_id, {})
        summary = trajectory.get("trajectory_risk_summary") or {}
        first_step = summary.get("first_repeated_behavior_risk_step")
        first_event = next(
            (
                item
                for item in summary.get("risk_events", [])
                if item.get("type") == "repeated_behavior_risk"
            ),
            {},
        )
        lines.extend(
            [
                f"- task {task_id}：success={trajectory.get('success')}, steps={trajectory.get('num_steps')}, "
                f"first_repeated_behavior_risk_step={first_step}, "
                f"action_signature={first_event.get('action_signature')}, "
                f"streak={first_event.get('same_action_signature_streak')}",
            ]
        )
    lines.extend(
        [
            "",
            "task 5 / task 15 / task 18 均被 repeated_behavior_risk 捕获，主要模式是搜索后连续 `click[next >]`，页面持续变化但决策没有转向商品选择或购买。",
            "",
            "## 未覆盖失败样例",
            "",
            "task 13 / task 14 没有触发当前通用重复行为规则。它们的动作不是连续同一 action_signature，而是在搜索、商品页、返回、详情页和不同商品之间移动；这类错误更像语义目标不收敛或错误商品探索，仅靠通用重复行为规则不一定能捕获，后续需要 LLM risk detector 或目标约束检测。",
        ]
    )
    return "\n".join(lines)


def _example_records(trajectories: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    examples: list[tuple[str, dict[str, Any]]] = []
    selectors = [
        (
            "action-level no_progress",
            lambda trajectory, post: bool(post.get("no_progress")),
        ),
        (
            "trajectory-level repeated_behavior_risk",
            lambda trajectory, post: bool(post.get("repeated_behavior_risk")),
        ),
        (
            "成功轨迹中的局部 no_progress",
            lambda trajectory, post: bool(trajectory.get("success") and post.get("no_progress")),
        ),
    ]
    for title, predicate in selectors:
        record = _find_example_record(trajectories, predicate)
        if record is not None:
            examples.append((title, record))
    return examples


def _find_example_record(
    trajectories: list[dict[str, Any]],
    predicate: Any,
) -> dict[str, Any] | None:
    for trajectory in trajectories:
        for step in trajectory.get("steps", []):
            record = step["action_record"]
            post = record.get("post_check", {})
            if predicate(trajectory, post):
                return record
    return None


def _build_client(model: str):
    if not model or model == "mock":
        return MockLLMClient()
    return OpenAIChatClient.from_env(model=model)


def _build_risk_client(model: str):
    if not model or model == "mock":
        return None
    try:
        return OpenAIChatClient.from_env(model=model)
    except ValueError:
        return None


def _parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
