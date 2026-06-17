#!/usr/bin/env python3
"""Export compact per-task tau3 run logs into commit-friendly reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "retail_0_19_task_logs"


RUNS = {
    "direct": "retail_0_19_direct_qwen_user_eval",
    "predictor_shadow": "retail_0_19_shadow_qwen_predictor_qwen_user_eval",
    "predictor_soft_high06": "retail_0_19_soft_high06_qwen_predictor_qwen_user_eval",
    "predictor_soft_high07_partial": "retail_0_19_soft_high07_qwen_predictor_qwen_user_eval",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def task_sort_key(task_id: str) -> tuple[int, int | str]:
    return (0, int(task_id)) if task_id.isdigit() else (1, task_id)


def truncate(value: Any, limit: int = 180) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def action_label(action: dict[str, Any] | None) -> str:
    if not action:
        return ""
    action_type = action.get("action_type")
    if action_type == "tool_call":
        return "{name}({args})".format(
            name=action.get("tool_name"),
            args=truncate(action.get("tool_arguments"), 120),
        )
    if action_type == "assistant_message":
        return "message: " + truncate(action.get("assistant_content"), 140)
    return truncate(action, 160)


def load_reward_by_task(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "tau2_results.json"
    if not path.exists():
        return {}
    data = load_json(path)
    reward_by_task = {}
    for sim in data.get("simulations", []):
        task_id = str(sim.get("task_id"))
        reward_by_task[task_id] = {
            "termination_reason": sim.get("termination_reason"),
            "duration": sim.get("duration"),
            "reward_info": sim.get("reward_info") or {},
        }
    return reward_by_task


def failed_action_checks(reward_info: dict[str, Any]) -> list[str]:
    failed = []
    for check in reward_info.get("action_checks") or []:
        if check.get("action_match"):
            continue
        action = check.get("action") or {}
        failed.append(
            "{name}({args}) [{tool_type}] reward={reward}".format(
                name=action.get("name"),
                args=truncate(action.get("arguments"), 120),
                tool_type=check.get("tool_type"),
                reward=check.get("action_reward"),
            )
        )
    return failed


def task_ids_for_run(run_dir: Path, summary: dict[str, Any]) -> list[str]:
    task_ids = set(str(item) for item in summary.get("task_ids", []))
    for path in run_dir.glob("task_*.jsonl"):
        task_ids.add(path.stem.removeprefix("task_"))
    for path in run_dir.glob("task_*_summary.json"):
        task_ids.add(path.name.removeprefix("task_").removesuffix("_summary.json"))
    return sorted(task_ids, key=task_sort_key)


def export_run(label: str, run_name: str, output_dir: Path) -> Path:
    run_dir = RUNS_ROOT / run_name
    summary_path = run_dir / "summary.json"
    summary = load_json(summary_path) if summary_path.exists() else {}
    run_meta = load_json(run_dir / "run_meta.json") if (run_dir / "run_meta.json").exists() else {}
    reward_by_task = load_reward_by_task(run_dir)
    task_ids = task_ids_for_run(run_dir, summary)
    complete = bool(summary)
    output_path = output_dir / f"{label}.md"
    lines = [
        f"# Task Logs: {label}",
        "",
        f"- Run: `{run_name}`",
        f"- Status: {'complete' if complete else 'partial/interrupted'}",
        f"- Mode: `{summary.get('mode') or run_meta.get('mode')}`",
        f"- Agent/User/Evaluator/Predictor: `{summary.get('agent_model') or run_meta.get('agent_model')}` / `{summary.get('user_model') or run_meta.get('user_model')}` / `{summary.get('evaluator_model') or run_meta.get('evaluator_model')}` / `{summary.get('predictor_model') or run_meta.get('predictor_model')}`",
        f"- Soft risk/confidence: `{summary.get('soft_risk_level') or run_meta.get('soft_risk_level')}` / `{summary.get('soft_confidence_threshold') or run_meta.get('soft_confidence_threshold')}`",
        "",
        "## Run Summary",
        "| Metric | Value |",
        "|---|---:|",
    ]
    metrics = [
        "num_tasks",
        "success_count",
        "success_rate",
        "avg_steps",
        "predictor_called",
        "high_risk_count",
        "critical_risk_count",
        "revise_once_count",
        "changed_by_controller_count",
        "had_warning_failed_tasks",
        "had_warning_success_tasks",
    ]
    for key in metrics:
        value = summary.get(key, "n/a")
        if isinstance(value, float):
            value = f"{value:.4f}"
        lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Per-task Overview",
            "| Task | Success | Reward | Termination | Steps | Predictor | High | Critical | Revise | Changed | First High | First Critical |",
            "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    summaries = {}
    for path in run_dir.glob("task_*_summary.json"):
        item = load_json(path)
        summaries[str(item.get("task_id"))] = item
    for task_id in task_ids:
        item = summaries.get(task_id, {})
        reward_info = reward_by_task.get(task_id, {}).get("reward_info") or {}
        reward = reward_info.get("reward")
        termination = reward_by_task.get(task_id, {}).get("termination_reason")
        lines.append(
            "| {task} | {success} | {reward} | {termination} | {steps} | {predictor} | {high} | {critical} | {revise} | {changed} | {first_high} | {first_critical} |".format(
                task=task_id,
                success=item.get("final_success", "n/a"),
                reward=reward if reward is not None else "n/a",
                termination=termination or "n/a",
                steps=item.get("num_steps", "n/a"),
                predictor=item.get("predictor_called", "n/a"),
                high=item.get("high_risk_count", "n/a"),
                critical=item.get("critical_risk_count", "n/a"),
                revise=item.get("revise_once_count", "n/a"),
                changed=item.get("changed_by_controller_count", "n/a"),
                first_high=item.get("first_high_risk_step", ""),
                first_critical=item.get("first_critical_risk_step", ""),
            )
        )

    lines.extend(["", "## Task Details"])
    for task_id in task_ids:
        task_summary = summaries.get(task_id, {})
        reward_entry = reward_by_task.get(task_id, {})
        reward_info = reward_entry.get("reward_info") or {}
        rows = load_jsonl(run_dir / f"task_{task_id}.jsonl")
        failed_checks = failed_action_checks(reward_info)
        lines.extend(
            [
                "",
                f"### Task {task_id}",
                "",
                f"- Final success: `{task_summary.get('final_success', 'n/a')}`",
                f"- Reward: `{reward_info.get('reward', 'n/a')}`",
                f"- Termination: `{reward_entry.get('termination_reason', 'n/a')}`",
                f"- Duration seconds: `{reward_entry.get('duration', 'n/a')}`",
                f"- Steps logged: `{len(rows)}`",
                f"- Predictor/high/critical/revise/changed: `{task_summary.get('predictor_called', 'n/a')}` / `{task_summary.get('high_risk_count', 'n/a')}` / `{task_summary.get('critical_risk_count', 'n/a')}` / `{task_summary.get('revise_once_count', 'n/a')}` / `{task_summary.get('changed_by_controller_count', 'n/a')}`",
                "",
                "Failed expected action checks:",
            ]
        )
        if failed_checks:
            lines.extend(f"- {item}" for item in failed_checks)
        else:
            lines.append("- none")
        lines.extend(
            [
                "",
                "Step log:",
                "| Step | Proposed | Executed | Changed | Risk | Conf | Recommendation | Decision | Reason |",
                "|---:|---|---|---:|---|---:|---|---|---|",
            ]
        )
        for row in rows:
            pred = row.get("prediction") or {}
            decision = row.get("controller_decision") or {}
            lines.append(
                "| {step} | {proposed} | {executed} | {changed} | {risk} | {confidence} | {recommendation} | {decision} | {reason} |".format(
                    step=row.get("step"),
                    proposed=action_label(row.get("proposed_action")).replace("|", "\\|"),
                    executed=action_label(row.get("executed_action")).replace("|", "\\|"),
                    changed=bool(row.get("changed_by_controller")),
                    risk=pred.get("risk_level", ""),
                    confidence=pred.get("confidence", ""),
                    recommendation=pred.get("recommendation", ""),
                    decision=decision.get("decision", ""),
                    reason=truncate(decision.get("reason"), 120).replace("|", "\\|"),
                )
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for label, run_name in RUNS.items():
        path = export_run(label, run_name, output_dir)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
