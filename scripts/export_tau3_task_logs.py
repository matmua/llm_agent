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


def md(value: Any, limit: int = 180) -> str:
    return truncate(value, limit).replace("|", "\\|")


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


def summarize_task_from_rows(
    task_id: str,
    rows: list[dict[str, Any]],
    reward_entry: dict[str, Any],
) -> dict[str, Any]:
    reward_info = reward_entry.get("reward_info") or {}
    return {
        "task_id": task_id,
        "final_success": reward_info.get("reward") == 1.0,
        "num_steps": len(rows),
        "predictor_called": len(rows),
        "high_risk_count": sum(
            1 for row in rows if (row.get("prediction") or {}).get("risk_level") == "high"
        ),
        "critical_risk_count": sum(
            1 for row in rows if (row.get("prediction") or {}).get("risk_level") == "critical"
        ),
        "revise_once_count": sum(
            1 for row in rows if (row.get("controller_decision") or {}).get("decision") == "revise_once"
        ),
        "changed_by_controller_count": sum(1 for row in rows if row.get("changed_by_controller")),
        "constraint_guided_revise_count": sum(
            1 for row in rows if (row.get("controller_decision") or {}).get("decision") == "revise_once"
        ),
        "second_check_count": sum(1 for row in rows if row.get("revised_prediction")),
        "risk_reduced_after_revision_count": sum(
            1 for row in rows if row.get("risk_reduced_after_revision")
        ),
        "fallback_used_count": sum(1 for row in rows if row.get("fallback_used")),
        "invalid_revised_action_count": sum(
            1 for row in rows if row.get("revised_action_valid") is False
        ),
        "executed_original_count": sum(
            1 for row in rows if row.get("executed_action_source") == "original"
        ),
        "executed_revised_count": sum(
            1 for row in rows if row.get("executed_action_source") == "revised"
        ),
        "executed_fallback_count": sum(
            1 for row in rows if row.get("executed_action_source") == "fallback"
        ),
    }


def export_run(
    label: str,
    run_name: str,
    output_dir: Path,
    selected_task_ids: set[str] | None = None,
) -> Path:
    run_dir = RUNS_ROOT / run_name
    summary_path = run_dir / "summary.json"
    summary = load_json(summary_path) if summary_path.exists() else {}
    run_meta = load_json(run_dir / "run_meta.json") if (run_dir / "run_meta.json").exists() else {}
    reward_by_task = load_reward_by_task(run_dir)
    task_ids = task_ids_for_run(run_dir, summary)
    if selected_task_ids is not None:
        task_ids = [task_id for task_id in task_ids if task_id in selected_task_ids]
    complete = bool(summary)
    output_path = output_dir / f"{label}.md"
    lines = [
        f"# Task Logs: {label}",
        "",
        f"- Run: `{run_name}`",
        f"- Status: {'complete' if complete else 'partial/interrupted'}",
        f"- Mode: `{summary.get('mode') or run_meta.get('mode')}`",
        f"- Controller version: `{summary.get('controller_version') or run_meta.get('controller_version')}`",
        f"- Agent/User/Evaluator/Predictor: `{summary.get('agent_model') or run_meta.get('agent_model')}` / `{summary.get('user_model') or run_meta.get('user_model')}` / `{summary.get('evaluator_model') or run_meta.get('evaluator_model')}` / `{summary.get('predictor_model') or run_meta.get('predictor_model')}`",
        f"- Soft risk/confidence: `{summary.get('soft_risk_level') or run_meta.get('soft_risk_level')}` / `{summary.get('soft_confidence_threshold') or run_meta.get('soft_confidence_threshold')}`",
        f"- Soft intervention confidence: `{summary.get('soft_intervention_confidence_threshold') or run_meta.get('soft_intervention_confidence_threshold')}`",
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
        "constraint_guided_revise_count",
        "second_check_count",
        "risk_reduced_after_revision_count",
        "fallback_used_count",
        "invalid_revised_action_count",
        "executed_original_count",
        "executed_revised_count",
        "executed_fallback_count",
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
            "| Task | Success | Reward | Termination | Steps | Predictor | High | Critical | Revise | Changed | Constraint Revise | Second Check | Risk Reduced | Fallback | Executed Revised | Executed Fallback |",
            "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    summaries = {}
    for path in run_dir.glob("task_*_summary.json"):
        item = load_json(path)
        summaries[str(item.get("task_id"))] = item
    for task_id in task_ids:
        rows = load_jsonl(run_dir / f"task_{task_id}.jsonl")
        item = summaries.get(task_id) or summarize_task_from_rows(
            task_id, rows, reward_by_task.get(task_id, {})
        )
        reward_info = reward_by_task.get(task_id, {}).get("reward_info") or {}
        reward = reward_info.get("reward")
        termination = reward_by_task.get(task_id, {}).get("termination_reason")
        lines.append(
            "| {task} | {success} | {reward} | {termination} | {steps} | {predictor} | {high} | {critical} | {revise} | {changed} | {constraint_revise} | {second_check} | {risk_reduced} | {fallback} | {executed_revised} | {executed_fallback} |".format(
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
                constraint_revise=item.get("constraint_guided_revise_count", "n/a"),
                second_check=item.get("second_check_count", "n/a"),
                risk_reduced=item.get("risk_reduced_after_revision_count", "n/a"),
                fallback=item.get("fallback_used_count", "n/a"),
                executed_revised=item.get("executed_revised_count", "n/a"),
                executed_fallback=item.get("executed_fallback_count", "n/a"),
            )
        )

    lines.extend(["", "## Task Details"])
    for task_id in task_ids:
        rows = load_jsonl(run_dir / f"task_{task_id}.jsonl")
        task_summary = summaries.get(task_id) or summarize_task_from_rows(
            task_id, rows, reward_by_task.get(task_id, {})
        )
        reward_entry = reward_by_task.get(task_id, {})
        reward_info = reward_entry.get("reward_info") or {}
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
                f"- Controller v2 counts: constraint revise `{task_summary.get('constraint_guided_revise_count', 'n/a')}`, second check `{task_summary.get('second_check_count', 'n/a')}`, risk reduced `{task_summary.get('risk_reduced_after_revision_count', 'n/a')}`, fallback `{task_summary.get('fallback_used_count', 'n/a')}`",
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
                "| Step | Proposed | Executed | Source | Changed | Risk | Conf | IntConf | Actionable | Preferred | Recommendation | Decision | Unsafe Summary | Safe Constraint | Forbidden Pattern | Revised | Revised Risk | Risk Reduced | Valid Revised | Fallback | Reason |",
                "|---:|---|---|---|---:|---|---:|---:|---|---|---|---|---|---|---|---|---|---:|---:|---:|---|",
            ]
        )
        for row in rows:
            pred = row.get("prediction") or {}
            decision = row.get("controller_decision") or {}
            revised_pred = row.get("revised_prediction") or {}
            lines.append(
                "| {step} | {proposed} | {executed} | {source} | {changed} | {risk} | {confidence} | {intervention_confidence} | {actionability} | {preferred} | {recommendation} | {decision} | {unsafe} | {constraint} | {forbidden} | {revised} | {revised_risk} | {risk_reduced} | {valid_revised} | {fallback} | {reason} |".format(
                    step=row.get("step"),
                    proposed=md(action_label(row.get("proposed_action"))),
                    executed=md(action_label(row.get("executed_action"))),
                    source=row.get("executed_action_source", ""),
                    changed=bool(row.get("changed_by_controller")),
                    risk=pred.get("risk_level", ""),
                    confidence=pred.get("confidence", ""),
                    intervention_confidence=pred.get("intervention_confidence", ""),
                    actionability=pred.get("actionability", ""),
                    preferred=pred.get("preferred_action_type", ""),
                    recommendation=pred.get("recommendation", ""),
                    decision=decision.get("decision", ""),
                    unsafe=md(pred.get("unsafe_action_summary"), 120),
                    constraint=md(pred.get("safe_action_constraint"), 140),
                    forbidden=md(pred.get("forbidden_action_pattern"), 120),
                    revised=md(action_label(row.get("revised_action"))),
                    revised_risk=revised_pred.get("risk_level", ""),
                    risk_reduced=bool(row.get("risk_reduced_after_revision")),
                    valid_revised=row.get("revised_action_valid", ""),
                    fallback=bool(row.get("fallback_used")),
                    reason=md(row.get("fallback_reason") or decision.get("reason"), 120),
                )
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs",
        help="Comma-separated run names. Defaults to the built-in retail 0-19 local runs.",
    )
    parser.add_argument(
        "--task-ids",
        help="Optional comma-separated task IDs to export from each selected run.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.runs:
        runs = {
            run_name.strip(): run_name.strip()
            for run_name in args.runs.split(",")
            if run_name.strip()
        }
    else:
        runs = RUNS
    selected_task_ids = None
    if args.task_ids:
        selected_task_ids = {task_id.strip() for task_id in args.task_ids.split(",") if task_id.strip()}
    for label, run_name in runs.items():
        path = export_run(label, run_name, output_dir, selected_task_ids)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
