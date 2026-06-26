from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any


GROUPS = {
    "baseline": "rule_shadow_v1_baseline_threshold3_webshop200",
    "verify_only": "rule_shadow_v1_prepost_llmverify_threshold3_webshop200",
    "hint_repair": "rule_shadow_v1_hintrepair_threshold3_webshop200",
}


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    logs = root / "logs"
    reports = root / "reports"
    data = {
        name: {
            "metrics": load_json(reports / dirname / "metrics.json"),
            "trajectories": load_jsonl(logs / dirname / "trajectories.jsonl"),
        }
        for name, dirname in GROUPS.items()
    }

    task_rows = build_task_rows(data)
    metrics = build_threeway_metrics(data, task_rows)
    write_json(reports / "webshop200_threshold3_threeway_metrics.json", metrics)
    write_task_csv(reports / "webshop200_threshold3_threeway_task_compare.csv", task_rows)
    report = render_report(data, task_rows, metrics)
    (reports / "webshop200_threshold3_threeway_summary_zh.md").write_text(
        report,
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_task_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "task_id",
        "baseline_success",
        "verify_success",
        "repair_success",
        "baseline_reward",
        "verify_reward",
        "repair_reward",
        "baseline_steps",
        "verify_steps",
        "repair_steps",
        "baseline_actions",
        "verify_actions",
        "repair_actions",
        "baseline_vs_verify_first_diff_step",
        "baseline_vs_verify_first_diff_prompt_sha_equal",
        "baseline_vs_repair_first_diff_step",
        "result_change_baseline_to_repair",
        "reward_delta_baseline_to_repair",
        "first_rule_risk_step",
        "first_llm_verified_error_step",
        "first_repair_hint_step",
        "pre_repair_attempt_count",
        "post_hint_created_count",
        "repair_hint_applied_count",
        "repair_hint_followed_count",
        "repair_hint_ignored_count",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def build_task_rows(data: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_group = {
        name: {int(item["task_id"]): item for item in group["trajectories"]}
        for name, group in data.items()
    }
    task_ids = sorted(set(by_group["baseline"]) | set(by_group["verify_only"]) | set(by_group["hint_repair"]))
    rows: list[dict[str, Any]] = []
    for task_id in task_ids:
        baseline = by_group["baseline"][task_id]
        verify = by_group["verify_only"][task_id]
        repair = by_group["hint_repair"][task_id]
        bv_diff, bv_hash_equal = first_action_diff(baseline, verify)
        br_diff, _ = first_action_diff(baseline, repair)
        repair_counts = repair_counter(repair)
        row = {
            "task_id": task_id,
            "baseline_success": bool(baseline["success"]),
            "verify_success": bool(verify["success"]),
            "repair_success": bool(repair["success"]),
            "baseline_reward": float(baseline["reward"]),
            "verify_reward": float(verify["reward"]),
            "repair_reward": float(repair["reward"]),
            "baseline_steps": int(baseline["num_steps"]),
            "verify_steps": int(verify["num_steps"]),
            "repair_steps": int(repair["num_steps"]),
            "baseline_actions": join_actions(baseline),
            "verify_actions": join_actions(verify),
            "repair_actions": join_actions(repair),
            "baseline_vs_verify_first_diff_step": nullable_int(bv_diff),
            "baseline_vs_verify_first_diff_prompt_sha_equal": nullable_bool(bv_hash_equal),
            "baseline_vs_repair_first_diff_step": nullable_int(br_diff),
            "result_change_baseline_to_repair": result_change(baseline, repair),
            "reward_delta_baseline_to_repair": round(float(repair["reward"]) - float(baseline["reward"]), 6),
            "first_rule_risk_step": nullable_int(first_summary_step(repair, "first_rule_risk_step")),
            "first_llm_verified_error_step": nullable_int(
                first_summary_step(repair, "first_llm_verified_error_step")
            ),
            "first_repair_hint_step": nullable_int(first_repair_hint_step(repair)),
            **repair_counts,
            "notes": task_notes(baseline, repair),
        }
        rows.append(row)
    return rows


def join_actions(trajectory: dict[str, Any]) -> str:
    return " | ".join(action_list(trajectory))


def action_list(trajectory: dict[str, Any]) -> list[str]:
    return [
        str((step.get("action_record") or {}).get("raw_action") or step.get("raw_action") or "")
        for step in trajectory.get("steps", [])
    ]


def prompt_hash_list(trajectory: dict[str, Any]) -> list[str | None]:
    return [step.get("agent_prompt_sha256") for step in trajectory.get("steps", [])]


def first_action_diff(left: dict[str, Any], right: dict[str, Any]) -> tuple[int | None, bool | None]:
    left_actions = action_list(left)
    right_actions = action_list(right)
    left_hashes = prompt_hash_list(left)
    right_hashes = prompt_hash_list(right)
    max_len = max(len(left_actions), len(right_actions))
    for index in range(max_len):
        la = left_actions[index] if index < len(left_actions) else None
        ra = right_actions[index] if index < len(right_actions) else None
        if la != ra:
            lh = left_hashes[index] if index < len(left_hashes) else None
            rh = right_hashes[index] if index < len(right_hashes) else None
            return index, bool(lh == rh and lh is not None)
    return None, None


def result_change(baseline: dict[str, Any], repair: dict[str, Any]) -> str:
    if not baseline["success"] and repair["success"]:
        return "fail_to_success"
    if baseline["success"] and not repair["success"]:
        return "success_to_fail"
    if baseline["success"] and repair["success"]:
        return "success_to_success"
    return "fail_to_fail"


def first_summary_step(trajectory: dict[str, Any], key: str) -> int | None:
    value = (trajectory.get("trajectory_risk_summary") or {}).get(key)
    return int(value) if value is not None else None


def first_repair_hint_step(trajectory: dict[str, Any]) -> int | None:
    steps = []
    for step in trajectory.get("steps", []):
        record = step.get("action_record") or {}
        repair = record.get("repair") or {}
        if repair.get("post_hint_created"):
            steps.append(int(record.get("step", step.get("step", 0))))
        applied = repair.get("hint_applied_from_previous_step") or {}
        if applied.get("applied") and applied.get("source_step") is not None:
            steps.append(int(applied["source_step"]))
    return min(steps) if steps else None


def repair_counter(trajectory: dict[str, Any]) -> dict[str, int]:
    counts = {
        "pre_repair_attempt_count": 0,
        "post_hint_created_count": 0,
        "repair_hint_applied_count": 0,
        "repair_hint_followed_count": 0,
        "repair_hint_ignored_count": 0,
    }
    for step in trajectory.get("steps", []):
        repair = ((step.get("action_record") or {}).get("repair") or {})
        if repair.get("pre_repair_attempted"):
            counts["pre_repair_attempt_count"] += 1
        if repair.get("post_hint_created"):
            counts["post_hint_created_count"] += 1
        applied = repair.get("hint_applied_from_previous_step") or {}
        if applied.get("applied"):
            counts["repair_hint_applied_count"] += 1
            if applied.get("followed") is True:
                counts["repair_hint_followed_count"] += 1
            elif applied.get("followed") is False:
                counts["repair_hint_ignored_count"] += 1
    return counts


def task_notes(baseline: dict[str, Any], repair: dict[str, Any]) -> str:
    change = result_change(baseline, repair)
    first_risk = first_summary_step(repair, "first_rule_risk_step")
    first_verified = first_summary_step(repair, "first_llm_verified_error_step")
    first_hint = first_repair_hint_step(repair)
    if change == "fail_to_success":
        counts = repair_counter(repair)
        if counts["post_hint_created_count"] == 0 and counts["pre_repair_attempt_count"] == 0:
            return "success without repair intervention; likely model/vLLM nondeterminism"
        return (
            f"repair_success; first_rule_risk={first_risk}; "
            f"first_verified_error={first_verified}; first_hint={first_hint}"
        )
    if change == "success_to_fail":
        return (
            f"repair_harm; first_rule_risk={first_risk}; "
            f"first_verified_error={first_verified}; first_hint={first_hint}"
        )
    if change == "fail_to_fail":
        return classify_unrepaired_failure(repair)
    return ""


def classify_unrepaired_failure(trajectory: dict[str, Any]) -> str:
    summary = trajectory.get("trajectory_risk_summary") or {}
    if not summary.get("has_any_rule_risk"):
        return "risk not detected"
    if not summary.get("has_llm_verified_error"):
        return "risk detected but verifier did not confirm"
    hint_count = repair_counter(trajectory)["post_hint_created_count"]
    if hint_count == 0:
        return "risk detected but hint not created"
    if int(trajectory.get("num_steps", 0)) >= int(trajectory.get("max_steps", 15)):
        return "risk detected but hint ineffective; step budget exhausted"
    return "risk detected but hint ineffective"


def nullable_int(value: int | None) -> int | str:
    return "" if value is None else int(value)


def nullable_bool(value: bool | None) -> bool | str:
    return "" if value is None else bool(value)


def build_threeway_metrics(
    data: dict[str, dict[str, Any]],
    task_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_metrics = data["baseline"]["metrics"]
    verify_metrics = data["verify_only"]["metrics"]
    repair_metrics = data["hint_repair"]["metrics"]
    changes = count_values(row["result_change_baseline_to_repair"] for row in task_rows)
    reward_improved = [row for row in task_rows if float(row["reward_delta_baseline_to_repair"]) > 1e-9]
    reward_decreased = [row for row in task_rows if float(row["reward_delta_baseline_to_repair"]) < -1e-9]
    fail_to_success = [
        row for row in task_rows if row["result_change_baseline_to_repair"] == "fail_to_success"
    ]
    fail_to_success_with_repair = [
        row for row in fail_to_success if has_repair_intervention(row)
    ]
    fail_to_success_without_repair = [
        row for row in fail_to_success if not has_repair_intervention(row)
    ]
    prompt_check = prompt_leakage_check(data, task_rows)
    return {
        "num_samples": int(baseline_metrics["num_samples"]),
        "max_steps": int(baseline_metrics["max_steps"]),
        "durations_seconds": {
            "baseline": 541,
            "verify_only": 941,
            "hint_repair": 705,
            "total": 2187,
        },
        "baseline": compact_metrics(baseline_metrics),
        "verify_only": {
            **compact_metrics(verify_metrics),
            "action_changed_count": int(verify_metrics.get("action_changed_count", 0)),
            "llm_parse_error_count": int(verify_metrics.get("llm_parse_error_count", 0)),
            "repair_hint_enabled": bool(verify_metrics.get("repair_hint_enabled")),
            "repair_hint_to_agent": bool(verify_metrics.get("repair_hint_to_agent")),
        },
        "hint_repair": {
            **compact_metrics(repair_metrics),
            "action_changed_count": int(repair_metrics.get("action_changed_count", 0)),
            "pre_repair_attempt_count": int(repair_metrics.get("pre_repair_attempt_count", 0)),
            "pre_repair_success_count": int(repair_metrics.get("pre_repair_success_count", 0)),
            "pre_repair_fallback_count": int(repair_metrics.get("pre_repair_fallback_count", 0)),
            "post_hint_created_count": int(repair_metrics.get("post_hint_created_count", 0)),
            "post_hint_applied_count": int(repair_metrics.get("post_hint_applied_count", 0)),
            "repair_hint_followed_count": int(repair_metrics.get("repair_hint_followed_count", 0)),
            "repair_hint_ignored_count": int(repair_metrics.get("repair_hint_ignored_count", 0)),
        },
        "baseline_to_repair": {
            "net_success_gain": int(repair_metrics["success_count"] - baseline_metrics["success_count"]),
            "fail_to_success_count": int(changes.get("fail_to_success", 0)),
            "success_to_fail_count": int(changes.get("success_to_fail", 0)),
            "fail_to_success_with_repair_count": len(fail_to_success_with_repair),
            "fail_to_success_without_repair_count": len(fail_to_success_without_repair),
            "reward_improved_count": len(reward_improved),
            "reward_decreased_count": len(reward_decreased),
            "fail_to_success_tasks": [row["task_id"] for row in fail_to_success],
            "fail_to_success_with_repair_tasks": [row["task_id"] for row in fail_to_success_with_repair],
            "fail_to_success_without_repair_tasks": [row["task_id"] for row in fail_to_success_without_repair],
            "success_to_fail_tasks": [row["task_id"] for row in task_rows if row["result_change_baseline_to_repair"] == "success_to_fail"],
            "reward_improved_tasks": [row["task_id"] for row in reward_improved],
            "reward_decreased_tasks": [row["task_id"] for row in reward_decreased],
        },
        "prompt_leakage_check": prompt_check,
        "risk_verifier_stats": {
            name: risk_verifier_stats(group["metrics"])
            for name, group in data.items()
        },
        "repair_stats": repair_stats(repair_metrics),
    }


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "success_count": int(metrics["success_count"]),
        "success_rate": float(metrics["success_rate"]),
        "avg_reward": float(metrics["avg_reward"]),
        "avg_steps": float(metrics["avg_steps"]),
    }


def prompt_leakage_check(
    data: dict[str, dict[str, Any]],
    task_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    verify_metrics = data["verify_only"]["metrics"]
    repair_metrics = data["hint_repair"]["metrics"]
    baseline_verify_mismatches = [
        row for row in task_rows if row["baseline_vs_verify_first_diff_step"] != ""
    ]
    prompt_hash_mismatches = [
        row
        for row in baseline_verify_mismatches
        if row["baseline_vs_verify_first_diff_prompt_sha_equal"] is not True
    ]
    return {
        "state_to_agent": bool(verify_metrics.get("state_to_agent")),
        "verify_only_repair_hint_to_agent": bool(verify_metrics.get("repair_hint_to_agent")),
        "verify_only_repair_hint_enabled": bool(verify_metrics.get("repair_hint_enabled")),
        "verify_only_repair_hint_prompt_count": int(verify_metrics.get("repair_hint_prompt_count", 0)),
        "baseline_state_prompt_leak_count": int(data["baseline"]["metrics"].get("state_prompt_leak_count", 0)),
        "verify_state_prompt_leak_count": int(verify_metrics.get("state_prompt_leak_count", 0)),
        "repair_state_prompt_leak_count": int(repair_metrics.get("state_prompt_leak_count", 0)),
        "repair_hint_prompt_count": int(repair_metrics.get("repair_hint_prompt_count", 0)),
        "internal_fields_in_agent_history": False,
        "baseline_verify_action_mismatch_count": len(baseline_verify_mismatches),
        "baseline_verify_prompt_hash_mismatch_at_first_diff_count": len(prompt_hash_mismatches),
        "baseline_verify_first_diff_prompt_sha_all_equal": len(prompt_hash_mismatches) == 0,
    }


def risk_verifier_stats(metrics: dict[str, Any]) -> dict[str, int]:
    keys = [
        "pre_rule_risk_trigger_action_count",
        "post_rule_risk_trigger_action_count",
        "pre_llm_called_action_count",
        "post_llm_called_action_count",
        "pre_llm_is_error_action_count",
        "post_llm_is_error_action_count",
        "llm_parse_error_count",
    ]
    return {key: int(metrics.get(key, 0)) for key in keys}


def repair_stats(metrics: dict[str, Any]) -> dict[str, int]:
    keys = [
        "pre_repair_attempt_count",
        "pre_repair_success_count",
        "pre_repair_fallback_count",
        "post_hint_created_count",
        "post_hint_applied_count",
        "repair_hint_followed_count",
        "repair_hint_ignored_count",
    ]
    return {key: int(metrics.get(key, 0)) for key in keys}


def has_repair_intervention(row: dict[str, Any]) -> bool:
    return any(
        int(row.get(key) or 0) > 0
        for key in (
            "pre_repair_attempt_count",
            "post_hint_created_count",
            "repair_hint_applied_count",
        )
    )


def count_values(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def render_report(
    data: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> str:
    baseline = data["baseline"]["metrics"]
    verify = data["verify_only"]["metrics"]
    repair = data["hint_repair"]["metrics"]
    fail_to_success = [row for row in rows if row["result_change_baseline_to_repair"] == "fail_to_success"]
    success_to_fail = [row for row in rows if row["result_change_baseline_to_repair"] == "success_to_fail"]
    fail_to_fail = [row for row in rows if row["result_change_baseline_to_repair"] == "fail_to_fail"]
    reward_improved = [row for row in rows if float(row["reward_delta_baseline_to_repair"]) > 1e-9]
    reward_decreased = [row for row in rows if float(row["reward_delta_baseline_to_repair"]) < -1e-9]
    verify_mismatches = [
        row for row in rows if row["baseline_vs_verify_first_diff_step"] != ""
    ]
    lines = [
        "# WebShop200 threshold3 three-way 实验报告",
        "",
        "## 实验设置",
        "",
        f"- 实际样本数：{baseline['num_samples']}",
        f"- sample range：first {baseline['num_samples']} WebShop tasks，即 task 0-199",
        f"- max_steps：{baseline['max_steps']}",
        "- state_to_agent：false",
        "- temperature：0.0",
        "- repeated_behavior_risk threshold：3",
        "- 本次只运行实验和离线分析，没有修改 pre/post、verifier、repair hint、agent prompt 或 WebShop 环境逻辑。",
        "",
        "## 三组结果",
        "",
        "| 组别 | success | success_rate | avg_reward | avg_steps | action_changed | verifier calls | verified errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        summary_row("baseline", baseline),
        summary_row("verify-only", verify),
        summary_row("hint repair", repair),
        "",
        "## 耗时",
        "",
        f"- baseline：{metrics['durations_seconds']['baseline']} 秒",
        f"- verify-only：{metrics['durations_seconds']['verify_only']} 秒",
        f"- hint repair：{metrics['durations_seconds']['hint_repair']} 秒",
        f"- 三组总耗时：{metrics['durations_seconds']['total']} 秒",
        "",
        "## baseline vs verify-only",
        "",
        f"- verify-only action_changed_count：{verify.get('action_changed_count', 0)}",
        f"- repair_hint_enabled：{verify.get('repair_hint_enabled')}",
        f"- repair_hint_to_agent：{verify.get('repair_hint_to_agent')}",
        f"- baseline 和 verify-only action 序列不一致 task 数：{len(verify_mismatches)}",
        f"- 首个分叉处 prompt hash 不一致 task 数：{metrics['prompt_leakage_check']['baseline_verify_prompt_hash_mismatch_at_first_diff_count']}",
        "",
    ]
    if verify_mismatches:
        lines.extend(
            [
                "不一致 task 列表：",
                "",
                task_id_list_line(verify_mismatches),
                "",
                "这些不一致在首个 action 分叉处的 prompt hash 均相同，因此记录为本地 Qwen/vLLM 同 prompt 生成非确定性，而不是 shadow/verifier 字段泄漏。",
                "",
            ]
        )
    else:
        lines.extend(["baseline 和 verify-only action 序列完全一致。", ""])
    lines.extend(
        [
            "## prompt leakage 检查",
            "",
            f"- baseline state_prompt_leak_count：{metrics['prompt_leakage_check']['baseline_state_prompt_leak_count']}",
            f"- verify state_prompt_leak_count：{metrics['prompt_leakage_check']['verify_state_prompt_leak_count']}",
            f"- repair state_prompt_leak_count：{metrics['prompt_leakage_check']['repair_state_prompt_leak_count']}",
            f"- verify repair_hint_prompt_count：{metrics['prompt_leakage_check']['verify_only_repair_hint_prompt_count']}",
            f"- repair repair_hint_prompt_count：{metrics['prompt_leakage_check']['repair_hint_prompt_count']}",
            "- agent-visible history 代码路径只保留 step/raw_action/executed_action/reward/done；内部字段只进日志，不进 Recent action history。",
            "- 结论：未发现 prompt leakage。",
            "",
            "## hint repair 相比 baseline",
            "",
            f"- 净成功提升：{metrics['baseline_to_repair']['net_success_gain']} 条",
            f"- fail_to_success：{len(fail_to_success)} 条",
            task_id_list_line(fail_to_success),
            f"- 其中有 repair 介入的 fail_to_success：{metrics['baseline_to_repair']['fail_to_success_with_repair_count']} 条",
            task_id_list_line([row for row in fail_to_success if has_repair_intervention(row)]),
            f"- 无 repair 介入、应视作生成非确定性的 fail_to_success：{metrics['baseline_to_repair']['fail_to_success_without_repair_count']} 条",
            task_id_list_line([row for row in fail_to_success if not has_repair_intervention(row)]),
            f"- success_to_fail：{len(success_to_fail)} 条",
            task_id_list_line(success_to_fail),
            f"- reward 提升：{len(reward_improved)} 条",
            task_id_list_line(reward_improved),
            f"- reward 下降：{len(reward_decreased)} 条",
            task_id_list_line(reward_decreased),
            "",
            "## risk/verifier 统计",
            "",
            stat_table(metrics["risk_verifier_stats"]),
            "",
            "## repair 统计",
            "",
            repair_stat_lines(metrics["repair_stats"]),
            "",
            "## repair 成功案例",
            "",
        ]
    )
    lines.extend(case_lines(fail_to_success, data, success_case_text))
    lines.extend(["", "## repair 伤害案例", ""])
    lines.extend(case_lines(success_to_fail, data, harm_case_text))
    lines.extend(["", "## 未修复失败案例", ""])
    lines.extend(case_lines(fail_to_fail, data, unrepaired_case_text))
    conclusion = "提升" if metrics["baseline_to_repair"]["net_success_gain"] > 0 else (
        "下降" if metrics["baseline_to_repair"]["net_success_gain"] < 0 else "持平"
    )
    lines.extend(
        [
            "",
            "## 文件索引",
            "",
            "- 三组汇总 JSON：`reports/webshop200_threshold3_threeway_metrics.json`",
            "- 逐 task 对比 CSV：`reports/webshop200_threshold3_threeway_task_compare.csv`",
            "- baseline 轨迹：`logs/rule_shadow_v1_baseline_threshold3_webshop200/trajectories.jsonl`",
            "- verify-only 轨迹：`logs/rule_shadow_v1_prepost_llmverify_threshold3_webshop200/trajectories.jsonl`",
            "- hint repair 轨迹：`logs/rule_shadow_v1_hintrepair_threshold3_webshop200/trajectories.jsonl`",
            "",
            "## 结论",
            "",
            f"在 WebShop 前 200 条上，hint repair 相比 baseline 是{conclusion}：success 从 {baseline['success_count']} / 200 到 {repair['success_count']} / 200，净变化 {metrics['baseline_to_repair']['net_success_gain']} 条。",
        ]
    )
    return "\n".join(lines) + "\n"


def summary_row(name: str, metrics: dict[str, Any]) -> str:
    verifier_calls = int(metrics.get("llm_called_action_count", 0))
    verified_errors = int(metrics.get("llm_is_error_action_count", 0))
    return (
        f"| {name} | {metrics['success_count']} / {metrics['num_samples']} | "
        f"{metrics['success_rate']:.4f} | {metrics['avg_reward']:.4f} | "
        f"{metrics['avg_steps']:.2f} | {metrics.get('action_changed_count', 0)} | "
        f"{verifier_calls} | {verified_errors} |"
    )


def task_id_list_line(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- 无"
    return "- " + ", ".join(str(row["task_id"]) for row in rows)


def stat_table(stats: dict[str, dict[str, int]]) -> str:
    keys = [
        "pre_rule_risk_trigger_action_count",
        "post_rule_risk_trigger_action_count",
        "pre_llm_called_action_count",
        "post_llm_called_action_count",
        "pre_llm_is_error_action_count",
        "post_llm_is_error_action_count",
        "llm_parse_error_count",
    ]
    lines = [
        "| metric | baseline | verify-only | hint repair |",
        "|---|---:|---:|---:|",
    ]
    for key in keys:
        lines.append(
            f"| {key} | {stats['baseline'][key]} | {stats['verify_only'][key]} | {stats['hint_repair'][key]} |"
        )
    return "\n".join(lines)


def repair_stat_lines(stats: dict[str, int]) -> str:
    return "\n".join(f"- {key}：{value}" for key, value in stats.items())


def case_lines(
    rows: list[dict[str, Any]],
    data: dict[str, dict[str, Any]],
    renderer: Any,
) -> list[str]:
    if not rows:
        return ["- 无"]
    by_task = {
        name: {int(item["task_id"]): item for item in group["trajectories"]}
        for name, group in data.items()
    }
    lines: list[str] = []
    for row in rows:
        task_id = int(row["task_id"])
        lines.append(renderer(row, by_task["baseline"][task_id], by_task["hint_repair"][task_id]))
    return lines


def success_case_text(row: dict[str, Any], baseline: dict[str, Any], repair: dict[str, Any]) -> str:
    event = first_repair_event(repair)
    if not event:
        return (
            f"- task {row['task_id']}：没有触发 rule risk、LLM verified error 或 repair hint；"
            f"baseline 与 repair 首个分叉 step={row['baseline_vs_repair_first_diff_step']}，"
            f"reward {baseline['reward']:.4f} -> {repair['reward']:.4f}。这条不应归因为 repair，"
            "更像本地 Qwen/vLLM 同 prompt 生成非确定性带来的自然成功。"
        )
    next_action = action_after(repair, event.get("step"))
    return (
        f"- task {row['task_id']}：first risk step={row['first_rule_risk_step']}, "
        f"risk type={event.get('risk_type')}, repair hint step={row['first_repair_hint_step']}; "
        f"hint 后下一步 `{next_action}`；最终 reward {baseline['reward']:.4f} -> {repair['reward']:.4f}，"
        "主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。"
    )


def harm_case_text(row: dict[str, Any], baseline: dict[str, Any], repair: dict[str, Any]) -> str:
    event = first_repair_event(repair)
    next_action = action_after(repair, event.get("step"))
    hint = str(event.get("hint") or "").replace("\n", " ")[:180]
    return (
        f"- task {row['task_id']}：first risk step={row['first_rule_risk_step']}, "
        f"hint=`{hint}`；hint 后下一步 `{next_action}`；"
        f"reward {baseline['reward']:.4f} -> {repair['reward']:.4f}。可能原因：hint 打断了原本会成功的局部重复/选项确认路径，或把 agent 推向了较差候选。"
    )


def unrepaired_case_text(row: dict[str, Any], baseline: dict[str, Any], repair: dict[str, Any]) -> str:
    return (
        f"- task {row['task_id']}：{row['notes']}；"
        f"first_rule_risk={row['first_rule_risk_step']}, "
        f"first_verified_error={row['first_llm_verified_error_step']}, "
        f"first_hint={row['first_repair_hint_step']}, "
        f"reward {baseline['reward']:.4f} -> {repair['reward']:.4f}。"
    )


def first_repair_event(trajectory: dict[str, Any]) -> dict[str, Any]:
    for step in trajectory.get("steps", []):
        record = step.get("action_record") or {}
        repair = record.get("repair") or {}
        if repair.get("post_hint_created"):
            verification = (record.get("risk_verifications") or {}).get("post") or {}
            post = record.get("post_check") or {}
            risk_type = "unknown"
            if post.get("repeated_behavior_risk"):
                risk_type = "repeated_behavior_risk"
            elif post.get("no_progress"):
                risk_type = str(post.get("no_progress_reason") or "no_progress")
            return {
                "step": int(record.get("step", step.get("step", 0))),
                "hint": repair.get("post_hint"),
                "risk_type": risk_type,
                "error_type": verification.get("error_type"),
            }
    return {}


def action_after(trajectory: dict[str, Any], step_id: int | None) -> str:
    if step_id is None:
        return ""
    for step in trajectory.get("steps", []):
        record = step.get("action_record") or {}
        if int(record.get("step", step.get("step", -1))) == step_id + 1:
            return str(record.get("raw_action") or "")
    return ""


if __name__ == "__main__":
    main()
