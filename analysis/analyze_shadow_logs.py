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
    high_risk_steps = [
        step for step in steps if step.get("pre_action_report", {}).get("risk_level") == "high"
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
    for step in steps:
        pre_categories.update(step.get("pre_action_report", {}).get("risk_categories", []))
        post_categories.update(step.get("post_action_report", {}).get("error_categories", []))

    high_before_failure = [
        episode
        for episode in failed
        if episode.get("first_high_risk_step") is not None
    ]
    post_before_failure = [
        episode
        for episode in failed
        if episode.get("first_post_error_step") is not None
    ]
    high_next_post_count = _count_high_risk_next_post_error(steps)
    high_before_post = [
        episode
        for episode in episodes
        if episode.get("first_high_risk_step") is not None
        and episode.get("first_post_error_step") is not None
        and episode["first_high_risk_step"] <= episode["first_post_error_step"]
    ]
    lead_times = [
        episode.get("num_steps", 0) - episode["first_high_risk_step"] - 1
        for episode in episodes
        if episode.get("first_high_risk_step") is not None
    ]
    simultaneous = [
        step
        for step in steps
        if step.get("pre_action_report", {}).get("risk_level") == "high"
        and step.get("post_action_report", {}).get("post_error")
    ]
    return {
        "total_episodes": total_episodes,
        "total_steps": total_steps,
        "success_rate": _ratio(successes, total_episodes),
        "avg_steps": _avg([episode.get("num_steps", 0) for episode in episodes]),
        "avg_reward": _avg([episode.get("final_reward", 0.0) for episode in episodes]),
        "pre_high_risk_step_rate": _ratio(len(high_risk_steps), total_steps),
        "episodes_with_high_risk_rate": _ratio(len(episodes_with_high), total_episodes),
        "avg_first_high_risk_step": _avg([episode["first_high_risk_step"] for episode in episodes_with_high]),
        "high_risk_before_failure_rate": _ratio(len(high_before_failure), len(failed)),
        "failed_episode_warning_recall": _ratio(len(high_before_failure), len(failed)),
        "successful_episode_warning_rate": _ratio(
            sum(1 for episode in succeeded if episode.get("first_high_risk_step") is not None),
            len(succeeded),
        ),
        "post_error_step_rate": _ratio(len(post_error_steps), total_steps),
        "episodes_with_post_error_rate": _ratio(len(episodes_with_post), total_episodes),
        "post_error_before_failure_rate": _ratio(len(post_before_failure), len(failed)),
        "potential_preventable_failure_count": sum(
            1 for episode in episodes if episode.get("had_potential_preventable_failure")
        ),
        "post_error_categories": dict(post_categories),
        "pre_risk_categories": dict(pre_categories),
        "pre_high_risk_next_step_post_error_rate": _ratio(high_next_post_count, len(high_risk_steps)),
        "pre_high_risk_before_post_error_episode_count": len(high_before_post),
        "avg_first_high_risk_lead_time": _avg(lead_times),
        "high_risk_and_post_error_same_step_count": len(simultaneous),
        "error_type_counts": {
            "missing_attribute": pre_categories.get("missing_attribute", 0),
            "unsupported_inference": pre_categories.get("unsupported_inference", 0),
            "premature_buy": pre_categories.get("premature_buy", 0),
            "invalid_action": pre_categories.get("invalid_action", 0),
            "action_no_effect": post_categories.get("action_no_effect", 0),
            "unexpected_transition": post_categories.get("unexpected_transition", 0),
            "constraint_conflict": post_categories.get("constraint_conflict", 0),
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
                "why_it_may_be_preventable_in_phase2": _phase2_reason(suspicious),
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
        f"- failed_episode_warning_recall: {metrics['failed_episode_warning_recall']:.4f}",
        f"- successful_episode_warning_rate: {metrics['successful_episode_warning_rate']:.4f}",
        f"- post_error_step_rate: {metrics['post_error_step_rate']:.4f}",
        f"- potential_preventable_failure_count: {metrics['potential_preventable_failure_count']}",
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
        f"- pre_high_risk_next_step_post_error_rate: {metrics['pre_high_risk_next_step_post_error_rate']:.4f}",
        f"- pre_high_risk_before_post_error_episode_count: {metrics['pre_high_risk_before_post_error_episode_count']}",
        f"- avg_first_high_risk_lead_time: {metrics['avg_first_high_risk_lead_time']:.4f}",
        f"- high_risk_and_post_error_same_step_count: {metrics['high_risk_and_post_error_same_step_count']}",
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
                f"- Phase 2 opportunity: {case['why_it_may_be_preventable_in_phase2']}",
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


def _phase2_reason(step: dict[str, Any]) -> str:
    pre = step.get("pre_action_report", {})
    post = step.get("post_action_report", {})
    if pre.get("missing_attributes"):
        return "Attribute completion could verify missing constraints before executing the risky action."
    if "invalid_action" in pre.get("risk_categories", []):
        return "A blocker or repair policy could replace the invalid action with a visible action."
    if post.get("post_error"):
        return "Post-action repair or rollback could respond after a no-effect or unexpected transition."
    return "The case is useful as a baseline trajectory for future intervention comparison."


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
