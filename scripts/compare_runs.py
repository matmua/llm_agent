#!/usr/bin/env python3
"""Compare tau3 guard runs without reading benchmark gold trajectories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", required=True, help="Comma-separated run names.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "retail_0_19_soft_comparison.md",
    )
    return parser.parse_args()


def load_run(run_name: str) -> dict[str, Any]:
    run_dir = RUNS_ROOT / run_name
    if not run_dir.exists():
        return {"run_name": run_name, "missing": True, "task_summaries": {}}
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return {"run_name": run_name, "missing": True, "reason": "summary.json missing"}
    summary = load_json(summary_path)
    tasks = {}
    for path in sorted(run_dir.glob("task_*_summary.json")):
        item = load_json(path)
        tasks[str(item.get("task_id"))] = item
    summary["missing"] = False
    summary["task_summaries_by_id"] = tasks
    return summary


def value(run: dict[str, Any], key: str, default: Any = 0) -> Any:
    if run.get("missing"):
        return "missing"
    return run.get(key, default)


def rate_text(run: dict[str, Any]) -> str:
    if run.get("missing"):
        return "missing"
    return f"{float(run.get('success_rate', 0.0)):.4f}"


def bool_text(value_: Any) -> str:
    if value_ is None:
        return "missing"
    return str(bool(value_))


def numeric_task_ids(runs: list[dict[str, Any]]) -> list[str]:
    task_ids = set()
    for run in runs:
        task_ids.update((run.get("task_summaries_by_id") or {}).keys())
    return sorted(
        task_ids,
        key=lambda item: (0, int(item)) if item.isdigit() else (1, item),
    )


def run_row(run: dict[str, Any]) -> str:
    return (
        f"| {run.get('run_name')} | {value(run, 'mode', 'missing')} | "
        f"{value(run, 'controller_version', 'missing')} | "
        f"{value(run, 'soft_risk_level', 'missing')} | "
        f"{value(run, 'soft_confidence_threshold', 'missing')} | "
        f"{rate_text(run)} | {value(run, 'success_count', 'missing')} | "
        f"{value(run, 'num_tasks', 'missing')} | {value(run, 'avg_steps', 'missing')} | "
        f"{value(run, 'predictor_called', 'missing')} | "
        f"{value(run, 'high_risk_count', 'missing')} | "
        f"{value(run, 'critical_risk_count', 'missing')} | "
        f"{value(run, 'revise_once_count', 'missing')} | "
        f"{value(run, 'changed_by_controller_count', 'missing')} | "
        f"{value(run, 'constraint_guided_revise_count', 'missing')} | "
        f"{value(run, 'second_check_count', 'missing')} | "
        f"{value(run, 'risk_reduced_after_revision_count', 'missing')} | "
        f"{value(run, 'fallback_used_count', 'missing')} | "
        f"{value(run, 'invalid_revised_action_count', 'missing')} | "
        f"{value(run, 'executed_revised_count', 'missing')} | "
        f"{value(run, 'executed_fallback_count', 'missing')} |"
    )


def main_observation(runs: list[dict[str, Any]]) -> list[str]:
    lines = [
        "- predictor_shadow is observational only; it should not be interpreted as improving success rate.",
    ]
    direct = next((run for run in runs if run.get("mode") == "direct" and not run.get("missing")), None)
    soft_runs = [
        run
        for run in runs
        if run.get("mode") == "predictor_soft" and not run.get("missing")
    ]
    if direct is None:
        lines.append("- Direct baseline is missing, so no success-rate delta is computed.")
        return lines
    direct_rate = float(direct.get("success_rate", 0.0))
    for run in soft_runs:
        rate = float(run.get("success_rate", 0.0))
        delta = rate - direct_rate
        if delta > 0:
            verdict = "improved"
        elif delta < 0:
            verdict = "decreased; this threshold may be too aggressive"
        else:
            verdict = "did not improve"
        lines.append(
            "- {run_name}: success rate {verdict} vs direct by {delta:+.4f} absolute; "
            "revise_once_count={revise}, changed_by_controller_count={changed}.".format(
                run_name=run.get("run_name"),
                verdict=verdict,
                delta=delta,
                revise=run.get("revise_once_count", 0),
                changed=run.get("changed_by_controller_count", 0),
            )
        )
    if not soft_runs:
        lines.append("- Soft runs are missing, so no intervention effect can be measured.")
    return lines


def task_value(run: dict[str, Any], task_id: str, key: str) -> Any:
    if run.get("missing"):
        return None
    task = (run.get("task_summaries_by_id") or {}).get(task_id)
    if not task:
        return None
    return task.get(key)


def write_report(runs: list[dict[str, Any]], output: Path) -> None:
    lines = [
        "# Tau3 Run Comparison",
        "",
        "## Runs",
        "| Run | Mode | Controller Version | Soft Risk Level | Soft Confidence | Success Rate | Success Count | Num Tasks | Avg Steps | Predictor Called | High Risk | Critical Risk | Revise Once | Changed By Controller | Constraint Revise | Second Check | Risk Reduced | Fallback Used | Invalid Revised Action | Executed Revised | Executed Fallback |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(run_row(run) for run in runs)
    missing = [run for run in runs if run.get("missing")]
    if missing:
        lines.extend(
            [
                "",
                "## Missing Runs",
                "| Run | Reason |",
                "|---|---|",
            ]
        )
        for run in missing:
            lines.append(f"| {run.get('run_name')} | {run.get('reason', 'run directory missing')} |")

    lines.extend(["", "## Main Observation"])
    lines.extend(main_observation(runs))
    lines.extend(
        [
            "",
            "## Per-task Comparison",
            "| Task ID | Run | Success | Constraint Revise | Second Check | Risk Reduced | Fallback | Executed Revised | Executed Fallback |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for task_id in numeric_task_ids(runs):
        for run in runs:
            if run.get("missing"):
                continue
            lines.append(
                "| {task_id} | {run_name} | {success} | {constraint_revise} | {second_check} | {risk_reduced} | {fallback} | {executed_revised} | {executed_fallback} |".format(
                    task_id=task_id,
                    run_name=run.get("run_name"),
                    success=bool_text(task_value(run, task_id, "final_success")),
                    constraint_revise=task_value(
                        run, task_id, "constraint_guided_revise_count"
                    )
                    or 0,
                    second_check=task_value(run, task_id, "second_check_count") or 0,
                    risk_reduced=task_value(
                        run, task_id, "risk_reduced_after_revision_count"
                    )
                    or 0,
                    fallback=task_value(run, task_id, "fallback_used_count") or 0,
                    executed_revised=task_value(
                        run, task_id, "executed_revised_count"
                    )
                    or 0,
                    executed_fallback=task_value(
                        run, task_id, "executed_fallback_count"
                    )
                    or 0,
                )
            )

    output = output if output.is_absolute() else PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report_path={output}")


def main() -> None:
    args = parse_args()
    run_names = [item.strip() for item in args.runs.split(",") if item.strip()]
    runs = [load_run(run_name) for run_name in run_names]
    write_report(runs, args.output)


if __name__ == "__main__":
    main()
