"""Analyze WebShop shadow-mode logs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log_dir", default="logs/webshop_shadow")
    parser.add_argument("--report_dir", default="reports")
    args = parser.parse_args()
    analyze_shadow_logs(Path(args.log_dir), Path(args.report_dir))


def analyze_shadow_logs(log_dir: Path, report_dir: Path) -> dict[str, Any]:
    steps = _read_jsonl(log_dir / "steps.jsonl")
    episodes = _read_jsonl(log_dir / "episodes.jsonl")
    config = _read_json(log_dir / "config.json")
    metrics = compute_metrics(steps, episodes)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "webshop_shadow_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    cases = representative_cases(steps, episodes, limit=10)
    with (report_dir / "webshop_shadow_cases.jsonl").open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=True) + "\n")
    (report_dir / "webshop_shadow_summary.md").write_text(
        render_markdown(config, metrics, cases),
        encoding="utf-8",
    )
    return metrics


def compute_metrics(steps: list[dict[str, Any]], episodes: list[dict[str, Any]]) -> dict[str, Any]:
    total_episodes = len(episodes)
    total_steps = len(steps)
    successes = sum(1 for episode in episodes if episode.get("final_success"))
    failed = [episode for episode in episodes if not episode.get("final_success")]
    succeeded = [episode for episode in episodes if episode.get("final_success")]
    steps_by_task = _steps_by_task(steps)
    first_pre_warning = _first_step_by_task(
        steps, lambda step: _is_pre_warning(step.get("pre_action_report", {}))
    )
    first_pre_high = _first_step_by_task(
        steps, lambda step: step.get("pre_action_report", {}).get("risk_level") == "high"
    )
    first_post_error = _first_step_by_task(
        steps, lambda step: bool(step.get("post_action_report", {}).get("post_error"))
    )
    high_risk_steps = [
        step for step in steps if step.get("pre_action_report", {}).get("risk_level") == "high"
    ]
    pre_warning_steps = [
        step for step in steps if _is_pre_warning(step.get("pre_action_report", {}))
    ]
    post_error_steps = [
        step for step in steps if step.get("post_action_report", {}).get("post_error")
    ]
    episodes_with_high = [
        episode for episode in episodes if episode.get("first_high_risk_step") is not None
    ]
    episodes_with_post = [
        episode for episode in episodes if episode.get("first_post_error_step") is not None
    ]
    pre_categories = Counter()
    post_categories = Counter()
    warning_categories = Counter()
    for step in steps:
        pre_categories.update(step.get("pre_action_report", {}).get("risk_categories", []))
        post_categories.update(step.get("post_action_report", {}).get("error_categories", []))
        warning_categories.update(step.get("post_action_report", {}).get("warning_categories", []))

    high_before_failure = [
        episode
        for episode in failed
        if first_pre_high.get(int(episode["task_id"])) is not None
    ]
    warning_before_failure = [
        episode
        for episode in failed
        if first_pre_warning.get(int(episode["task_id"])) is not None
    ]
    post_before_failure = [
        episode
        for episode in failed
        if first_post_error.get(int(episode["task_id"])) is not None
    ]
    high_next_post_count = _count_high_risk_next_post_error(steps)
    high_before_post = [
        episode
        for episode in episodes
        if first_pre_high.get(int(episode["task_id"])) is not None
        and first_post_error.get(int(episode["task_id"])) is not None
        and first_pre_high[int(episode["task_id"])] <= first_post_error[int(episode["task_id"])]
    ]
    warning_before_post = [
        episode
        for episode in episodes
        if first_pre_warning.get(int(episode["task_id"])) is not None
        and first_post_error.get(int(episode["task_id"])) is not None
        and first_pre_warning[int(episode["task_id"])] <= first_post_error[int(episode["task_id"])]
    ]
    lead_times = [
        episode.get("num_steps", 0) - first_pre_high[int(episode["task_id"])] - 1
        for episode in episodes
        if first_pre_high.get(int(episode["task_id"])) is not None
    ]
    warning_lead_times = [
        episode.get("num_steps", 0) - first_pre_warning[int(episode["task_id"])] - 1
        for episode in episodes
        if first_pre_warning.get(int(episode["task_id"])) is not None
    ]
    pre_to_post_lead_times = [
        first_post_error[int(episode["task_id"])] - first_pre_warning[int(episode["task_id"])]
        for episode in episodes
        if first_pre_warning.get(int(episode["task_id"])) is not None
        and first_post_error.get(int(episode["task_id"])) is not None
        and first_pre_warning[int(episode["task_id"])] <= first_post_error[int(episode["task_id"])]
    ]
    simultaneous = [
        step
        for step in steps
        if step.get("pre_action_report", {}).get("risk_level") == "high"
        and step.get("post_action_report", {}).get("post_error")
    ]
    llm_parse_attempts = [step for step in steps if "llm_state_proposal_parse_error" in step]
    llm_parse_successes = [
        step for step in llm_parse_attempts if not step.get("llm_state_proposal_parse_error")
    ]
    fallback_steps = [
        step for step in steps if step.get("state_update_after_action", {}).get("state_fallback_used")
    ]
    entity_counts = [_generic_count(step, "entities") for step in steps]
    constraint_counts = [_generic_count(step, "constraints") for step in steps]
    conflict_counts_by_episode = [
        _episode_conflicts(steps_by_task.get(int(episode["task_id"]), [])) for episode in episodes
    ]
    return {
        "total_episodes": total_episodes,
        "total_steps": total_steps,
        "success_rate": _ratio(successes, total_episodes),
        "avg_steps": _avg([episode.get("num_steps", 0) for episode in episodes]),
        "avg_reward": _avg([episode.get("final_reward", 0.0) for episode in episodes]),
        "pre_warning_step_rate": _ratio(len(pre_warning_steps), total_steps),
        "pre_high_risk_step_rate": _ratio(len(high_risk_steps), total_steps),
        "episodes_with_high_risk_rate": _ratio(len(episodes_with_high), total_episodes),
        "avg_first_high_risk_step": _avg([episode["first_high_risk_step"] for episode in episodes_with_high]),
        "high_risk_before_failure_rate": _ratio(len(high_before_failure), len(failed)),
        "failed_episode_warning_recall": _ratio(len(high_before_failure), len(failed)),
        "failed_episode_pre_warning_recall": _ratio(len(warning_before_failure), len(failed)),
        "successful_episode_warning_rate": _ratio(
            sum(1 for episode in succeeded if episode.get("first_high_risk_step") is not None),
            len(succeeded),
        ),
        "successful_episode_pre_warning_rate": _ratio(
            sum(1 for episode in succeeded if first_pre_warning.get(int(episode["task_id"])) is not None),
            len(succeeded),
        ),
        "buy_now_pre_warning_count": sum(
            1
            for step in pre_warning_steps
            if str(step.get("raw_action", "")).lower() == "click[buy now]"
        ),
        "early_pre_warning_count": sum(1 for step in pre_warning_steps if not step.get("done")),
        "avg_pre_warning_lead_time": _avg(warning_lead_times),
        "post_error_step_rate": _ratio(len(post_error_steps), total_steps),
        "episodes_with_post_error_rate": _ratio(len(episodes_with_post), total_episodes),
        "post_error_before_failure_rate": _ratio(len(post_before_failure), len(failed)),
        "failed_episode_post_error_recall": _ratio(len(post_before_failure), len(failed)),
        "successful_episode_post_error_rate": _ratio(
            sum(1 for episode in succeeded if first_post_error.get(int(episode["task_id"])) is not None),
            len(succeeded),
        ),
        "explicit_conflict_count": post_categories.get("explicit_conflict", 0),
        "missing_evidence_count": post_categories.get("missing_evidence", 0)
        + warning_categories.get("missing_evidence", 0),
        "unexpected_transition_count": post_categories.get("unexpected_transition", 0),
        "no_effect_count": post_categories.get("no_effect", 0)
        + post_categories.get("action_no_effect", 0),
        "preventable_failure_count": post_categories.get("preventable_failure", 0)
        + post_categories.get("potential_preventable_failure", 0),
        "potential_preventable_failure_count": sum(
            1 for episode in episodes if episode.get("had_potential_preventable_failure")
        ),
        "post_error_categories": dict(post_categories),
        "post_warning_categories": dict(warning_categories),
        "pre_risk_categories": dict(pre_categories),
        "pre_warning_before_post_error_rate": _ratio(len(warning_before_post), len(episodes_with_post)),
        "avg_lead_time_pre_to_post": _avg(pre_to_post_lead_times),
        "post_error_after_high_risk_rate": _ratio(high_next_post_count, len(high_risk_steps)),
        "pre_high_risk_next_step_post_error_rate": _ratio(high_next_post_count, len(high_risk_steps)),
        "pre_high_risk_before_post_error_episode_count": len(high_before_post),
        "pre_warning_before_post_error_episode_count": len(warning_before_post),
        "avg_first_high_risk_lead_time": _avg(lead_times),
        "high_risk_and_post_error_same_step_count": len(simultaneous),
        "llm_state_parse_success_rate": _ratio(len(llm_parse_successes), len(llm_parse_attempts)),
        "avg_entities_per_step": _avg(entity_counts),
        "avg_constraints_per_step": _avg(constraint_counts),
        "conflicts_per_episode": _avg(conflict_counts_by_episode),
        "fallback_rate": _ratio(len(fallback_steps), total_steps),
        "unsupported_high_confidence_update_count": post_categories.get("unsupported_state_update", 0),
        "error_type_counts": {
            "missing_attribute": pre_categories.get("missing_attribute", 0),
            "missing_evidence": pre_categories.get("missing_evidence", 0)
            + post_categories.get("missing_evidence", 0),
            "unsupported_inference": pre_categories.get("unsupported_inference", 0),
            "premature_buy": pre_categories.get("premature_buy", 0),
            "invalid_action": pre_categories.get("invalid_action", 0),
            "no_effect": post_categories.get("no_effect", 0),
            "action_no_effect": post_categories.get("action_no_effect", 0),
            "unexpected_transition": post_categories.get("unexpected_transition", 0),
            "explicit_conflict": post_categories.get("explicit_conflict", 0),
            "constraint_conflict": post_categories.get("constraint_conflict", 0),
            "preventable_failure": post_categories.get("preventable_failure", 0),
            "unsupported_state_update": post_categories.get("unsupported_state_update", 0),
        },
    }


def representative_cases(
    steps: list[dict[str, Any]], episodes: list[dict[str, Any]], limit: int = 10
) -> list[dict[str, Any]]:
    by_task: dict[int, list[dict[str, Any]]] = {}
    for step in steps:
        by_task.setdefault(int(step["task_id"]), []).append(step)
    cases: list[dict[str, Any]] = []
    for episode in episodes:
        if episode.get("final_success"):
            continue
        task_steps = by_task.get(int(episode["task_id"]), [])
        first_suspicious = _first_suspicious(task_steps)
        if not task_steps:
            continue
        suspicious = first_suspicious or task_steps[0]
        excerpt = [
            {
                "step_id": item["step_id"],
                "raw_action": item["raw_action"],
                "pre_risk_level": item["pre_action_report"].get("risk_level"),
                "pre_categories": item["pre_action_report"].get("risk_categories", []),
                "post_error": item["post_action_report"].get("post_error"),
                "post_categories": item["post_action_report"].get("error_categories", []),
                "reward": item.get("reward"),
                "done": item.get("done"),
            }
            for item in task_steps[:8]
        ]
        cases.append(
            {
                "task_id": episode["task_id"],
                "instruction": episode.get("task_instruction", ""),
                "final_result": {
                    "success": episode.get("final_success"),
                    "reward": episode.get("final_reward"),
                    "num_steps": episode.get("num_steps"),
                },
                "first_suspicious_action": {
                    "step_id": suspicious["step_id"] if first_suspicious else None,
                    "raw_action": suspicious["raw_action"] if first_suspicious else "none_detected",
                },
                "no_suspicious_detected": first_suspicious is None,
                "pre_action_report_reason": suspicious["pre_action_report"].get("reason", ""),
                "post_action_report_reason": suspicious["post_action_report"].get("reason", ""),
                "shadow_detection_note": _shadow_detection_note(suspicious),
                "raw_trajectory_excerpt": excerpt,
            }
        )
        if len(cases) >= limit:
            break
    return cases


def render_markdown(config: dict[str, Any], metrics: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    lines = [
        "# WebShop Shadow Detection Summary",
        "",
        "This report is for Phase 1 shadow mode only. The detector logs risk, but it does not alter actions.",
        "",
        "## Run Config",
        "",
        f"- run_id: `{config.get('run_id', 'unknown')}`",
        f"- env: `{config.get('env', 'unknown')}`",
        f"- requested_env: `{config.get('requested_env', 'unknown')}`",
        f"- model: `{config.get('model', 'unknown')}`",
        f"- num_tasks: `{config.get('num_tasks', 'unknown')}`",
        f"- max_steps: `{config.get('max_steps', 'unknown')}`",
        "",
        "## Key Metrics",
        "",
        f"- total_episodes: {metrics['total_episodes']}",
        f"- total_steps: {metrics['total_steps']}",
        f"- success_rate: {metrics['success_rate']:.4f}",
        f"- avg_reward: {metrics['avg_reward']:.4f}",
        f"- pre_warning_step_rate: {metrics['pre_warning_step_rate']:.4f}",
        f"- pre_high_risk_step_rate: {metrics['pre_high_risk_step_rate']:.4f}",
        f"- failed_episode_pre_warning_recall: {metrics['failed_episode_pre_warning_recall']:.4f}",
        f"- successful_episode_pre_warning_rate: {metrics['successful_episode_pre_warning_rate']:.4f}",
        f"- post_error_step_rate: {metrics['post_error_step_rate']:.4f}",
        f"- failed_episode_post_error_recall: {metrics['failed_episode_post_error_recall']:.4f}",
        f"- explicit_conflict_count: {metrics['explicit_conflict_count']}",
        f"- missing_evidence_count: {metrics['missing_evidence_count']}",
        f"- preventable_failure_count: {metrics['preventable_failure_count']}",
        f"- llm_state_parse_success_rate: {metrics['llm_state_parse_success_rate']:.4f}",
        f"- fallback_rate: {metrics['fallback_rate']:.4f}",
        "",
        "## Risk Categories",
        "",
        "Pre-action risk counts:",
        "",
        "```json",
        json.dumps(metrics["pre_risk_categories"], indent=2, ensure_ascii=True),
        "```",
        "",
        "Post-action error counts:",
        "",
        "```json",
        json.dumps(metrics["post_error_categories"], indent=2, ensure_ascii=True),
        "```",
        "",
        "## Pre/Post Correlation",
        "",
        f"- pre_warning_before_post_error_rate: {metrics['pre_warning_before_post_error_rate']:.4f}",
        f"- avg_lead_time_pre_to_post: {metrics['avg_lead_time_pre_to_post']:.4f}",
        f"- post_error_after_high_risk_rate: {metrics['post_error_after_high_risk_rate']:.4f}",
        f"- pre_high_risk_next_step_post_error_rate: {metrics['pre_high_risk_next_step_post_error_rate']:.4f}",
        f"- pre_high_risk_before_post_error_episode_count: {metrics['pre_high_risk_before_post_error_episode_count']}",
        f"- avg_first_high_risk_lead_time: {metrics['avg_first_high_risk_lead_time']:.4f}",
        f"- high_risk_and_post_error_same_step_count: {metrics['high_risk_and_post_error_same_step_count']}",
        "",
        "## State Proposal Quality",
        "",
        f"- avg_entities_per_step: {metrics['avg_entities_per_step']:.4f}",
        f"- avg_constraints_per_step: {metrics['avg_constraints_per_step']:.4f}",
        f"- conflicts_per_episode: {metrics['conflicts_per_episode']:.4f}",
        f"- unsupported_high_confidence_update_count: {metrics['unsupported_high_confidence_update_count']}",
        "",
        "## Representative Failed Cases",
        "",
    ]
    if not cases:
        lines.append("No failed case with a suspicious action was found.")
    for case in cases:
        lines.extend(
            [
                f"### Task {case['task_id']}",
                "",
                f"- instruction: {case['instruction']}",
                f"- first suspicious action: {_format_suspicious_action(case)}",
                f"- pre-action reason: {case['pre_action_report_reason']}",
                f"- post-action reason: {case['post_action_report_reason']}",
                f"- shadow detection note: {case['shadow_detection_note']}",
                "",
                "```json",
                json.dumps(case["raw_trajectory_excerpt"], indent=2, ensure_ascii=True),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation Guardrail",
            "",
            "Shadow mode does not improve success rate by design. Treat these metrics as detection and correlation evidence only.",
            "The detector may produce missing_evidence warnings that are not counted as hard post_action errors.",
            "",
        ]
    )
    return "\n".join(lines)


def _first_suspicious(task_steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    for step in task_steps:
        if step["pre_action_report"].get("risk_level") == "high" or step["post_action_report"].get("post_error"):
            return step
    return None


def _format_suspicious_action(case: dict[str, Any]) -> str:
    action = case["first_suspicious_action"]
    if case.get("no_suspicious_detected"):
        return "none detected; excerpt starts at step 0"
    return f"step {action['step_id']} `{action['raw_action']}`"


def _shadow_detection_note(step: dict[str, Any]) -> str:
    pre = step.get("pre_action_report", {})
    post = step.get("post_action_report", {})
    if pre.get("missing_attributes"):
        return "Pre-action detector found missing evidence before the action executed."
    if "invalid_action" in pre.get("risk_categories", []):
        return "Pre-action detector found an invalid or unavailable action target."
    if post.get("post_error"):
        return "Post-action detector found a state transition, conflict, or final-failure signal."
    return "No suspicious detector signal appeared in the excerpt."


def _count_high_risk_next_post_error(steps: list[dict[str, Any]]) -> int:
    by_task_step = {(step["task_id"], step["step_id"]): step for step in steps}
    count = 0
    for step in steps:
        if step.get("pre_action_report", {}).get("risk_level") != "high":
            continue
        next_step = by_task_step.get((step["task_id"], step["step_id"] + 1))
        if next_step and next_step.get("post_action_report", {}).get("post_error"):
            count += 1
    return count


def _steps_by_task(steps: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_task: dict[int, list[dict[str, Any]]] = {}
    for step in steps:
        by_task.setdefault(int(step["task_id"]), []).append(step)
    for task_steps in by_task.values():
        task_steps.sort(key=lambda item: int(item.get("step_id", 0)))
    return by_task


def _first_step_by_task(steps: list[dict[str, Any]], predicate: Any) -> dict[int, int]:
    first: dict[int, int] = {}
    for step in sorted(steps, key=lambda item: (int(item["task_id"]), int(item["step_id"]))):
        task_id = int(step["task_id"])
        if task_id in first:
            continue
        if predicate(step):
            first[task_id] = int(step["step_id"])
    return first


def _is_pre_warning(pre_report: dict[str, Any]) -> bool:
    if pre_report.get("risk_level") in {"medium", "high"}:
        return True
    return bool(pre_report.get("risk_categories") or pre_report.get("missing_attributes"))


def _generic_count(step: dict[str, Any], key: str) -> int:
    graph = step.get("state_after", {}).get("generic_state_graph", {})
    value = graph.get(key, {})
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, list):
        return len(value)
    return 0


def _episode_conflicts(task_steps: list[dict[str, Any]]) -> int:
    if not task_steps:
        return 0
    graph = task_steps[-1].get("state_after", {}).get("generic_state_graph", {})
    conflicts = graph.get("conflicts", [])
    return len(conflicts) if isinstance(conflicts, list) else 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _ratio(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _avg(values: list[Any]) -> float:
    clean = [float(value) for value in values if value is not None]
    return mean(clean) if clean else 0.0


if __name__ == "__main__":
    main()
