#!/usr/bin/env python3
"""Summarize tau3-bench runs and trace likely failure causes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OFFICIAL_RESULTS = {
    "Qwen3.5-397B-A17B retail pass^1": 84.43,
    "Qwen3-Max-Thinking retail pass^1": 79.3859649122807,
    "GPT-4.1 retail pass^1": 74.0,
    "o4-mini retail pass^1": 68.3,
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_text(text: str | None, limit: int = 360) -> str:
    if not text:
        return ""
    one_line = " ".join(str(text).split())
    return one_line[:limit] + ("..." if len(one_line) > limit else "")


def message_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    calls = message.get("tool_calls") or []
    return [
        {
            "name": call.get("name"),
            "arguments": call.get("arguments"),
            "requestor": call.get("requestor"),
        }
        for call in calls
    ]


def classify_failure(sim: dict[str, Any]) -> str:
    termination = sim.get("termination_reason")
    reward_info = sim.get("reward_info") or {}
    if termination not in ("agent_stop", "user_stop"):
        return f"premature_termination:{termination}"
    if reward_info.get("reward") == 1.0:
        return "success"
    breakdown = {
        str(key).lower(): value
        for key, value in (reward_info.get("reward_breakdown") or {}).items()
    }
    if any(key.endswith("nl_assertion") and value == 0 for key, value in breakdown.items()):
        return "nl_assertion_failed"
    if any(key.endswith("db") and value == 0 for key, value in breakdown.items()):
        return "db_state_failed"
    if any(key.endswith("action") and value == 0 for key, value in breakdown.items()):
        return "action_sequence_failed"
    if any(key.endswith("communicate") and value == 0 for key, value in breakdown.items()):
        return "communication_failed"
    info_note = (reward_info.get("info") or {}).get("note")
    if info_note:
        return compact_text(info_note, 80)
    return "reward_zero_unknown"


def summarize_simulation(sim: dict[str, Any]) -> dict[str, Any]:
    messages = sim.get("messages") or []
    assistant_calls = []
    tool_errors = []
    for index, message in enumerate(messages):
        if message.get("role") == "assistant":
            for call in message_tool_calls(message):
                assistant_calls.append({"turn": index, **call})
        if message.get("role") == "tool":
            content = message.get("content")
            if content and any(
                marker in content.lower()
                for marker in ("error", "exception", "invalid", "not found", "failed")
            ):
                tool_errors.append({"turn": index, "content": compact_text(content)})

    reward_info = sim.get("reward_info") or {}
    action_checks = reward_info.get("action_checks") or []
    failed_actions = [
        {
            "expected": check.get("action"),
            "match": check.get("action_match"),
            "justification": compact_text(check.get("justification")),
        }
        for check in action_checks
        if check.get("action_match") is False
    ]
    nl_checks = reward_info.get("nl_assertions") or []
    failed_nl = [
        {
            "assertion": check.get("nl_assertion"),
            "met": check.get("met"),
            "justification": compact_text(check.get("justification")),
        }
        for check in nl_checks
        if check.get("met") is False
    ]

    last_user = next(
        (
            message.get("content")
            for message in reversed(messages)
            if message.get("role") == "user"
        ),
        None,
    )
    last_assistant = next(
        (
            message.get("content")
            for message in reversed(messages)
            if message.get("role") == "assistant" and message.get("content")
        ),
        None,
    )

    return {
        "simulation_id": sim.get("id"),
        "task_id": sim.get("task_id"),
        "trial": sim.get("trial"),
        "seed": sim.get("seed"),
        "reward": reward_info.get("reward"),
        "termination_reason": sim.get("termination_reason"),
        "duration": sim.get("duration"),
        "num_messages": len(messages),
        "num_assistant_tool_calls": len(assistant_calls),
        "failure_type": classify_failure(sim),
        "reward_breakdown": reward_info.get("reward_breakdown"),
        "tool_errors": tool_errors[:5],
        "failed_actions": failed_actions[:8],
        "failed_nl_assertions": failed_nl[:5],
        "last_user": compact_text(last_user),
        "last_assistant": compact_text(last_assistant),
        "tool_call_trace": assistant_calls,
    }


def write_markdown(
    path: Path,
    run_dir: Path,
    summary: dict[str, Any],
    official_results: dict[str, float],
) -> None:
    lines = [
        "# Tau3 Retail Subset Summary",
        "",
        f"- Run dir: `{run_dir}`",
        f"- Total simulations: {summary['total']}",
        f"- Scored simulations: {summary['scored']}",
        f"- Infrastructure/premature errors: {summary['premature_or_infra']}",
        f"- Successes: {summary['success']}",
        f"- Accuracy over all attempted tasks: {summary['accuracy_all']:.4f}",
        f"- Accuracy over scored tasks: {summary['accuracy_scored']:.4f}",
        "",
        "## Failure Types",
        "",
    ]
    for failure_type, count in summary["failure_type_counts"].items():
        lines.append(f"- {failure_type}: {count}")
    lines.extend(
        [
            "",
            "## Per Task",
            "",
            "| task_id | reward | termination | failure_type | tool_calls | messages |",
            "|---|---:|---|---|---:|---:|",
        ]
    )
    for item in summary["simulations"]:
        lines.append(
            "| {task_id} | {reward} | {termination_reason} | {failure_type} | "
            "{num_assistant_tool_calls} | {num_messages} |".format(**item)
        )
    lines.extend(
        [
            "",
            "## Official Reference",
            "",
            "These are full benchmark leaderboard pass^1 retail numbers from the "
            "tau3-bench repository snapshot. They are not directly comparable to "
            "this local 5-task run because this run uses Qwen3-8B as both agent "
            "and user simulator, and also uses a local Qwen evaluator for NL assertions.",
            "",
        ]
    )
    for name, value in official_results.items():
        lines.append(f"- {name}: {value:.2f}%")
    lines.extend(
        [
            "",
            "## Failure Trace Notes",
            "",
        ]
    )
    for item in summary["simulations"]:
        if item["reward"] == 1.0:
            continue
        lines.append(
            f"### Task {item['task_id']} - {item['failure_type']}"
        )
        lines.append(f"- Last user: {item['last_user'] or '(empty)'}")
        lines.append(f"- Last assistant: {item['last_assistant'] or '(empty)'}")
        if item["tool_errors"]:
            for err in item["tool_errors"]:
                lines.append(f"- Tool error at turn {err['turn']}: {err['content']}")
        if item["failed_actions"]:
            for failed in item["failed_actions"]:
                lines.append(
                    "- Failed action check: "
                    f"{compact_text(json.dumps(failed, ensure_ascii=False), 260)}"
                )
        if item["failed_nl_assertions"]:
            for failed in item["failed_nl_assertions"]:
                lines.append(
                    "- Failed NL assertion: "
                    f"{compact_text(json.dumps(failed, ensure_ascii=False), 260)}"
                )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=PROJECT_ROOT / "reports" / "tau3_retail_subset_summary.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    results = load_json(run_dir / "results.json")
    simulations = [summarize_simulation(sim) for sim in results.get("simulations", [])]
    total = len(simulations)
    scored = sum(1 for sim in simulations if sim["reward"] is not None)
    success = sum(1 for sim in simulations if sim["reward"] == 1.0)
    premature_or_infra = sum(
        1
        for sim in simulations
        if sim["termination_reason"] not in ("agent_stop", "user_stop")
    )
    summary = {
        "run_dir": str(run_dir),
        "total": total,
        "scored": scored,
        "success": success,
        "premature_or_infra": premature_or_infra,
        "accuracy_all": success / total if total else 0.0,
        "accuracy_scored": success / scored if scored else 0.0,
        "failure_type_counts": dict(Counter(sim["failure_type"] for sim in simulations)),
        "simulations": simulations,
        "official_reference": DEFAULT_OFFICIAL_RESULTS,
    }
    (run_dir / "analysis.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(args.report_path, run_dir, summary, DEFAULT_OFFICIAL_RESULTS)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
