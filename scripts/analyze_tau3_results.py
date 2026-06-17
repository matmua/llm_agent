#!/usr/bin/env python3
"""Analyze predictor-only tau3/tau2 guard runs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_task_summaries(run_dir: Path) -> list[dict[str, Any]]:
    summaries = []
    for path in sorted(run_dir.glob("task_*_summary.json")):
        summaries.append(load_json(path))
    if summaries:
        return summaries

    for path in sorted(run_dir.glob("task_*.jsonl")):
        task_id = path.stem.removeprefix("task_")
        rows = load_jsonl(path)
        high_steps = [
            row.get("step")
            for row in rows
            if (row.get("prediction") or {}).get("risk_level") == "high"
        ]
        critical_steps = [
            row.get("step")
            for row in rows
            if (row.get("prediction") or {}).get("risk_level") == "critical"
        ]
        summaries.append(
            {
                "task_id": task_id,
                "final_success": False,
                "num_steps": len(rows),
                "predictor_called": sum(1 for row in rows if row.get("prediction")),
                "high_risk_count": len(high_steps),
                "critical_risk_count": len(critical_steps),
                "had_high_risk_warning": bool(high_steps),
                "had_critical_risk_warning": bool(critical_steps),
                "first_high_risk_step": high_steps[0] if high_steps else None,
                "first_critical_risk_step": critical_steps[0] if critical_steps else None,
                "revise_once_count": sum(
                    1
                    for row in rows
                    if (row.get("controller_decision") or {}).get("decision")
                    == "revise_once"
                ),
                "changed_by_controller_count": sum(
                    1 for row in rows if row.get("changed_by_controller")
                ),
            }
        )
    return summaries


def build_analysis(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    run_summary = load_json(summary_path) if summary_path.exists() else {}
    run_meta = load_json(run_dir / "run_meta.json") if (run_dir / "run_meta.json").exists() else {}
    task_summaries = load_task_summaries(run_dir)
    risk_distribution = Counter()
    first_high_distribution = Counter()
    failed_with_warning = 0
    failed_without_warning = 0
    success_with_warning = 0
    success_without_warning = 0

    for item in task_summaries:
        if item.get("high_risk_count", 0):
            risk_distribution["high"] += int(item.get("high_risk_count", 0))
        if item.get("critical_risk_count", 0):
            risk_distribution["critical"] += int(item.get("critical_risk_count", 0))
        first_high = item.get("first_high_risk_step")
        if first_high is not None:
            first_high_distribution[str(first_high)] += 1
        had_warning = bool(
            item.get("had_high_risk_warning")
            or item.get("had_critical_risk_warning")
        )
        if item.get("final_success") and had_warning:
            success_with_warning += 1
        elif item.get("final_success") and not had_warning:
            success_without_warning += 1
        elif not item.get("final_success") and had_warning:
            failed_with_warning += 1
        else:
            failed_without_warning += 1

    analysis = {
        "run_name": run_summary.get("run_name") or run_dir.name,
        "run_dir": str(run_dir),
        "setting": {
            "domain": run_summary.get("domain") or run_meta.get("domain"),
            "task_ids": run_summary.get("task_ids") or run_meta.get("task_ids") or [],
            "mode": run_summary.get("mode") or run_meta.get("mode"),
            "agent_model": run_summary.get("agent_model") or run_meta.get("agent_model"),
            "user_model": run_summary.get("user_model") or run_meta.get("user_model"),
            "evaluator_model": run_summary.get("evaluator_model") or run_meta.get("evaluator_model"),
            "predictor_model": run_summary.get("predictor_model") or run_meta.get("predictor_model"),
        },
        "metrics": {
            "success_rate": run_summary.get("success_rate", 0.0),
            "avg_steps": run_summary.get("avg_steps", 0.0),
            "predictor_called": run_summary.get("predictor_called", 0),
            "high_risk_count": run_summary.get("high_risk_count", 0),
            "critical_risk_count": run_summary.get("critical_risk_count", 0),
            "had_high_risk_warning_count": sum(
                1 for item in task_summaries if item.get("had_high_risk_warning")
            ),
            "had_critical_risk_warning_count": sum(
                1 for item in task_summaries if item.get("had_critical_risk_warning")
            ),
            "failed_tasks_with_high_or_critical_warning": failed_with_warning,
            "success_tasks_with_high_or_critical_warning": success_with_warning,
            "revise_once_count": run_summary.get("revise_once_count", 0),
            "changed_by_controller_count": run_summary.get("changed_by_controller_count", 0),
        },
        "warning_vs_final_outcome": {
            "failed_tasks_with_high_or_critical_warning": failed_with_warning,
            "failed_tasks_without_high_or_critical_warning": failed_without_warning,
            "successful_tasks_with_high_or_critical_warning": success_with_warning,
            "successful_tasks_without_high_or_critical_warning": success_without_warning,
        },
        "risk_distribution": dict(risk_distribution),
        "first_high_risk_step_distribution": dict(first_high_distribution),
        "task_summaries": task_summaries,
    }
    return analysis


def write_markdown(path: Path, analysis: dict[str, Any]) -> None:
    setting = analysis["setting"]
    metrics = analysis["metrics"]
    warning_outcomes = analysis["warning_vs_final_outcome"]
    lines = [
        f"# Run Analysis: {analysis['run_name']}",
        "",
        "## Setting",
        f"- Domain: {setting.get('domain')}",
        f"- Task IDs: {setting.get('task_ids')}",
        f"- Mode: {setting.get('mode')}",
        f"- Agent: {setting.get('agent_model')}",
        f"- User simulator: {setting.get('user_model')}",
        f"- Evaluator: {setting.get('evaluator_model')}",
        f"- Predictor: {setting.get('predictor_model')}",
        "",
        "## Main Results",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        if isinstance(value, float):
            lines.append(f"| {key} | {value:.4f} |")
        else:
            lines.append(f"| {key} | {value} |")

    lines.extend(["", "## Predictor Warning Distribution", "| Risk Level | Count |", "|---|---:|"])
    risk_distribution = analysis.get("risk_distribution") or {}
    if risk_distribution:
        for risk_level, count in sorted(risk_distribution.items()):
            lines.append(f"| {risk_level} | {count} |")
    else:
        lines.append("| none | 0 |")

    lines.extend(["", "## Warning vs Final Outcome", "| Group | Count |", "|---|---:|"])
    labels = {
        "failed_tasks_with_high_or_critical_warning": "Failed tasks with high/critical warning",
        "failed_tasks_without_high_or_critical_warning": "Failed tasks without high/critical warning",
        "successful_tasks_with_high_or_critical_warning": "Successful tasks with high/critical warning",
        "successful_tasks_without_high_or_critical_warning": "Successful tasks without high/critical warning",
    }
    for key, label in labels.items():
        lines.append(f"| {label} | {warning_outcomes.get(key, 0)} |")

    lines.extend(
        [
            "",
            "## First High Risk Step Distribution",
            "| Step | Count |",
            "|---|---:|",
        ]
    )
    first_high = analysis.get("first_high_risk_step_distribution") or {}
    if first_high:
        for step, count in sorted(first_high.items(), key=lambda item: int(item[0])):
            lines.append(f"| {step} | {count} |")
    else:
        lines.append("| none | 0 |")

    lines.extend(
        [
            "",
            "## Per-task Summary",
            "| Task ID | Success | Steps | High Risk | Critical Risk | First High Risk Step | First Critical Risk Step | Revise Once |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in analysis["task_summaries"]:
        lines.append(
            "| {task_id} | {success} | {steps} | {high} | {critical} | {first_high} | {first_critical} | {revise} |".format(
                task_id=item.get("task_id"),
                success=bool(item.get("final_success")),
                steps=item.get("num_steps", 0),
                high=item.get("high_risk_count", 0),
                critical=item.get("critical_risk_count", 0),
                first_high=item.get("first_high_risk_step"),
                first_critical=item.get("first_critical_risk_step"),
                revise=item.get("revise_once_count", 0),
            )
        )

    lines.extend(
        [
            "",
            "## Notes",
            "- Do not claim improvement from predictor_shadow because it does not intervene.",
            "- Compare predictor_soft only against direct under the same user simulator and evaluator.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--report-path", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    analysis = build_analysis(run_dir)
    (run_dir / "analysis.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report_path = args.report_path
    if report_path is None:
        report_path = PROJECT_ROOT / "reports" / f"{analysis['run_name']}_analysis.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(report_path, analysis)
    print(json.dumps(analysis, indent=2, ensure_ascii=False))
    print(f"report_path={report_path}")


if __name__ == "__main__":
    main()
