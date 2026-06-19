"""Compare WebShop direct, shadow, and intervention runs."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


MODES = ("direct", "shadow", "intervention")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", required=True)
    parser.add_argument("--shadow", required=True)
    parser.add_argument("--intervention", required=True)
    parser.add_argument("--report_dir", default="reports/webshop_phase2")
    args = parser.parse_args()
    evaluate_interventions(
        {
            "direct": Path(args.direct),
            "shadow": Path(args.shadow),
            "intervention": Path(args.intervention),
        },
        Path(args.report_dir),
    )


def evaluate_interventions(log_dirs: dict[str, Path], report_dir: Path) -> dict[str, Any]:
    runs = {mode: _load_run(log_dirs[mode]) for mode in MODES}
    metrics = {
        mode: _compute_run_metrics(runs[mode]["steps"], runs[mode]["episodes"])
        for mode in MODES
    }
    paired = _compute_paired_metrics(runs, metrics)
    output = {"runs": metrics, "paired": paired}

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "intervention_metrics.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    (report_dir / "intervention_comparison.md").write_text(
        _render_markdown(runs, metrics, paired),
        encoding="utf-8",
    )
    _write_task_logs(runs, report_dir / "task_logs")
    _copy_raw_logs(log_dirs, report_dir / "raw_logs")
    return output


def _load_run(log_dir: Path) -> dict[str, Any]:
    return {
        "log_dir": str(log_dir),
        "config": _read_json(log_dir / "config.json"),
        "steps": _read_jsonl(log_dir / "steps.jsonl"),
        "episodes": _read_jsonl(log_dir / "episodes.jsonl"),
        "events": _read_jsonl(log_dir / "intervention_events.jsonl"),
    }


def _compute_run_metrics(
    steps: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    total_episodes = len(episodes)
    total_steps = len(steps)
    successes = [episode for episode in episodes if episode.get("final_success")]
    failed = [episode for episode in episodes if not episode.get("final_success")]
    changed_steps = [
        step
        for step in steps
        if step.get("intervention_decision", {}).get("metadata", {}).get("changed_action")
    ]
    changed_task_ids = {int(step["task_id"]) for step in changed_steps}
    repair_queued_steps = [
        step for step in steps if step.get("repair_decision", {}).get("repair_executed")
    ]
    repair_executed_steps = [
        step for step in steps if step.get("action_source") == "post_action_repair"
    ]
    repair_executed_task_ids = {int(step["task_id"]) for step in repair_executed_steps}
    post_error_steps = [
        step for step in steps if step.get("post_action_report", {}).get("post_error")
    ]
    high_risk_steps = [
        step for step in steps if step.get("pre_action_report", {}).get("risk_level") == "high"
    ]
    high_risk_blocked_steps = [
        step
        for step in changed_steps
        if step.get("intervention_decision", {}).get("would_block")
        or step.get("pre_action_report", {}).get("risk_level") == "high"
    ]
    high_risk_blocked_task_ids = {int(step["task_id"]) for step in high_risk_blocked_steps}
    by_task = _steps_by_task(steps)
    post_before, post_after, steps_before, steps_after = _repair_post_error_windows(by_task)

    pre_categories = Counter()
    post_categories = Counter()
    for step in steps:
        pre_categories.update(step.get("pre_action_report", {}).get("risk_categories", []))
        post_categories.update(step.get("post_action_report", {}).get("error_categories", []))

    token_total = sum(
        int(step.get("token_usage_estimate", {}).get("total_tokens", 0))
        for step in steps
    )
    return {
        "total_episodes": total_episodes,
        "total_steps": total_steps,
        "successes": len(successes),
        "failures": len(failed),
        "success_rate": _ratio(len(successes), total_episodes),
        "avg_steps": _avg([episode.get("num_steps", 0) for episode in episodes]),
        "avg_reward": _avg([episode.get("final_reward", 0.0) for episode in episodes]),
        "estimated_token_cost_total": token_total,
        "estimated_token_cost_avg": _ratio(token_total, total_episodes),
        "post_error_steps": len(post_error_steps),
        "post_error_step_rate": _ratio(len(post_error_steps), total_steps),
        "high_risk_steps": len(high_risk_steps),
        "high_risk_step_rate": _ratio(len(high_risk_steps), total_steps),
        "changed_actions": len(changed_steps),
        "changed_action_step_rate": _ratio(len(changed_steps), total_steps),
        "episodes_with_intervention": len(changed_task_ids | repair_executed_task_ids),
        "intervention_episode_rate": _ratio(len(changed_task_ids | repair_executed_task_ids), total_episodes),
        "changed_action_episode_success_rate": _episode_success_rate(episodes, changed_task_ids),
        "high_risk_blocked_steps": len(high_risk_blocked_steps),
        "episodes_with_high_risk_block": len(high_risk_blocked_task_ids),
        "high_risk_block_success_rate": _episode_success_rate(episodes, high_risk_blocked_task_ids),
        "repair_actions_queued": len(repair_queued_steps),
        "repair_actions_executed": len(repair_executed_steps),
        "episodes_with_repair_action": len(repair_executed_task_ids),
        "repair_success_rate": _episode_success_rate(episodes, repair_executed_task_ids),
        "recovery_success_rate": _episode_success_rate(episodes, repair_executed_task_ids),
        "post_error_before_repair_rate": _ratio(post_before, steps_before),
        "post_error_after_repair_rate": _ratio(post_after, steps_after),
        "pre_risk_categories": dict(pre_categories),
        "post_error_categories": dict(post_categories),
    }


def _compute_paired_metrics(
    runs: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    direct = _episodes_by_task(runs["direct"]["episodes"])
    shadow = _episodes_by_task(runs["shadow"]["episodes"])
    intervention = _episodes_by_task(runs["intervention"]["episodes"])
    changed_task_ids = {
        int(step["task_id"])
        for step in runs["intervention"]["steps"]
        if step.get("intervention_decision", {}).get("metadata", {}).get("changed_action")
    }
    repair_task_ids = {
        int(step["task_id"])
        for step in runs["intervention"]["steps"]
        if step.get("action_source") == "post_action_repair"
    }
    common_task_ids = sorted(set(direct) & set(shadow) & set(intervention))
    shadow_success = {
        task_id for task_id in common_task_ids if shadow[task_id].get("final_success")
    }
    direct_success = {
        task_id for task_id in common_task_ids if direct[task_id].get("final_success")
    }
    intervention_success = {
        task_id for task_id in common_task_ids if intervention[task_id].get("final_success")
    }
    false_block_against_shadow = sorted(
        task_id
        for task_id in shadow_success
        if task_id in changed_task_ids and task_id not in intervention_success
    )
    false_block_against_direct = sorted(
        task_id
        for task_id in direct_success
        if task_id in changed_task_ids and task_id not in intervention_success
    )
    rescued_from_shadow = sorted(
        task_id
        for task_id in intervention_success
        if task_id not in shadow_success and (task_id in changed_task_ids or task_id in repair_task_ids)
    )
    rescued_from_direct = sorted(
        task_id
        for task_id in intervention_success
        if task_id not in direct_success and (task_id in changed_task_ids or task_id in repair_task_ids)
    )
    shadow_high_risk_task_ids = {
        int(step["task_id"])
        for step in runs["shadow"]["steps"]
        if step.get("pre_action_report", {}).get("risk_level") == "high"
    }
    shadow_high_risk_success_rate = _episode_success_rate(
        runs["shadow"]["episodes"], shadow_high_risk_task_ids
    )
    return {
        "common_task_count": len(common_task_ids),
        "success_rate_delta_vs_direct": metrics["intervention"]["success_rate"]
        - metrics["direct"]["success_rate"],
        "success_rate_delta_vs_shadow": metrics["intervention"]["success_rate"]
        - metrics["shadow"]["success_rate"],
        "avg_steps_delta_vs_direct": metrics["intervention"]["avg_steps"]
        - metrics["direct"]["avg_steps"],
        "avg_steps_delta_vs_shadow": metrics["intervention"]["avg_steps"]
        - metrics["shadow"]["avg_steps"],
        "token_cost_delta_vs_direct": metrics["intervention"]["estimated_token_cost_avg"]
        - metrics["direct"]["estimated_token_cost_avg"],
        "token_cost_delta_vs_shadow": metrics["intervention"]["estimated_token_cost_avg"]
        - metrics["shadow"]["estimated_token_cost_avg"],
        "false_block_rate_vs_shadow_successes": _ratio(
            len(false_block_against_shadow), len(shadow_success)
        ),
        "false_block_rate_vs_direct_successes": _ratio(
            len(false_block_against_direct), len(direct_success)
        ),
        "false_block_task_ids_vs_shadow": false_block_against_shadow,
        "false_block_task_ids_vs_direct": false_block_against_direct,
        "rescued_task_ids_vs_shadow": rescued_from_shadow,
        "rescued_task_ids_vs_direct": rescued_from_direct,
        "shadow_high_risk_success_rate": shadow_high_risk_success_rate,
        "intervention_high_risk_block_success_rate": metrics["intervention"][
            "high_risk_block_success_rate"
        ],
    }


def _render_markdown(
    runs: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    paired: dict[str, Any],
) -> str:
    lines = [
        "# WebShop Phase 2 Intervention 对比报告",
        "",
        "本报告比较三种模式：原始 ReAct agent、Phase 1 shadow 检测不干预、Phase 2 intervention agent。当前实验使用同一批 task id，并保留 raw logs 与逐任务摘要。",
        "",
        "## 运行配置",
        "",
        "| 模式 | log_dir | env | model | num_tasks | max_steps |",
        "|---|---|---|---|---:|---:|",
    ]
    for mode in MODES:
        config = runs[mode]["config"]
        lines.append(
            f"| {mode} | `{runs[mode]['log_dir']}` | `{config.get('env')}` | `{config.get('model')}` | {config.get('num_tasks')} | {config.get('max_steps')} |"
        )
    lines.extend(
        [
            "",
            "## 核心指标",
            "",
            "| 模式 | 成功数 | 成功率 | 平均 step | 平均 reward | post_error率 | 改写 action | 修复执行 | 平均 token估算 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for mode in MODES:
        item = metrics[mode]
        lines.append(
            "| "
            f"{mode} | {item['successes']}/{item['total_episodes']} | {_fmt(item['success_rate'])} | "
            f"{_fmt(item['avg_steps'])} | {_fmt(item['avg_reward'])} | {_fmt(item['post_error_step_rate'])} | "
            f"{item['changed_actions']} | {item['repair_actions_executed']} | {_fmt(item['estimated_token_cost_avg'])} |"
        )

    lines.extend(
        [
            "",
            "## 关键结论",
            "",
            f"- 成功率变化：intervention 相对 direct 为 {_signed(paired['success_rate_delta_vs_direct'])}，相对 shadow 为 {_signed(paired['success_rate_delta_vs_shadow'])}。",
            f"- 平均 step 变化：intervention 相对 direct 为 {_signed(paired['avg_steps_delta_vs_direct'])}，相对 shadow 为 {_signed(paired['avg_steps_delta_vs_shadow'])}。",
            f"- 高风险阻断后的成功率：intervention 中发生高风险阻断的 episode 成功率为 {_fmt(metrics['intervention']['high_risk_block_success_rate'])}；shadow 中出现高风险提示的 episode 成功率为 {_fmt(paired['shadow_high_risk_success_rate'])}。",
            f"- 误阻断比例：以 shadow 成功任务为基准，因 intervention 改写后失败的比例为 {_fmt(paired['false_block_rate_vs_shadow_successes'])}；任务 id：{paired['false_block_task_ids_vs_shadow']}。",
            f"- 修复效果：intervention 修复动作执行 {metrics['intervention']['repair_actions_executed']} 次，涉及 {metrics['intervention']['episodes_with_repair_action']} 个 episode，最终恢复成功率为 {_fmt(metrics['intervention']['recovery_success_rate'])}。",
            f"- 修复后 post_error：修复前窗口 post_error 率 {_fmt(metrics['intervention']['post_error_before_repair_rate'])}，修复后窗口 post_error 率 {_fmt(metrics['intervention']['post_error_after_repair_rate'])}。",
            "",
            "## 任务级变化",
            "",
            f"- intervention 相对 shadow 新救回任务：{paired['rescued_task_ids_vs_shadow']}",
            f"- intervention 相对 direct 新救回任务：{paired['rescued_task_ids_vs_direct']}",
            f"- intervention 相对 shadow 误伤任务：{paired['false_block_task_ids_vs_shadow']}",
            f"- intervention 相对 direct 误伤任务：{paired['false_block_task_ids_vs_direct']}",
            "",
            "## 错误类别统计",
            "",
        ]
    )
    for mode in MODES:
        lines.extend(
            [
                f"### {mode}",
                "",
                "Pre-action risk:",
                "",
                "```json",
                json.dumps(metrics[mode]["pre_risk_categories"], indent=2, ensure_ascii=True),
                "```",
                "",
                "Post-action error:",
                "",
                "```json",
                json.dumps(metrics[mode]["post_error_categories"], indent=2, ensure_ascii=True),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## 查看位置",
            "",
            "- 指标 JSON：`reports/webshop_phase2/intervention_metrics.json`",
            "- 逐任务 Markdown 日志：`reports/webshop_phase2/task_logs/`",
            "- 原始 JSONL 日志副本：`reports/webshop_phase2/raw_logs/`",
            "",
            "## 解释边界",
            "",
            "当前数值主要评估 Phase 2 框架与规则式 intervention 是否能改变失败传播，不等价于真实强 LLM 的 WebShop benchmark 分数。若要评估模型能力，应把 `--model mock` 换成 OpenAI-compatible 本地或远端模型后重跑同一脚本。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_task_logs(runs: dict[str, dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for mode in MODES:
        episodes = _episodes_by_task(runs[mode]["episodes"])
        steps_by_task = _steps_by_task(runs[mode]["steps"])
        lines = [f"# WebShop {mode} 逐任务日志", ""]
        for task_id in sorted(episodes):
            episode = episodes[task_id]
            lines.extend(
                [
                    f"## Task {task_id}",
                    "",
                    f"- instruction: {episode.get('task_instruction', '')}",
                    f"- final_success: {episode.get('final_success')}",
                    f"- final_reward: {episode.get('final_reward')}",
                    f"- num_steps: {episode.get('num_steps')}",
                    "",
                    "| step | source | raw_action | executed_action | pre_risk | post_error | repair_action | reward | done |",
                    "|---:|---|---|---|---|---|---|---:|---|",
                ]
            )
            for step in steps_by_task.get(task_id, []):
                repair = step.get("repair_decision", {})
                lines.append(
                    "| "
                    f"{step.get('step_id')} | {step.get('action_source')} | `{_escape_cell(step.get('raw_action'))}` | "
                    f"`{_escape_cell(step.get('executed_action'))}` | "
                    f"{step.get('pre_action_report', {}).get('risk_level')}:{','.join(step.get('pre_action_report', {}).get('risk_categories', []))} | "
                    f"{step.get('post_action_report', {}).get('post_error')}:{','.join(step.get('post_action_report', {}).get('error_categories', []))} | "
                    f"`{_escape_cell(repair.get('repair_action', ''))}` | {step.get('reward')} | {step.get('done')} |"
                )
            suspicious = [
                step
                for step in steps_by_task.get(task_id, [])
                if step.get("pre_action_report", {}).get("risk_level") == "high"
                or step.get("post_action_report", {}).get("post_error")
                or step.get("raw_action") != step.get("executed_action")
                or step.get("action_source") == "post_action_repair"
            ]
            if suspicious:
                lines.extend(["", "可疑/干预步骤详情：", ""])
                for step in suspicious:
                    lines.extend(
                        [
                            f"- step {step.get('step_id')}",
                            f"  - pre_reason: {step.get('pre_action_report', {}).get('reason', '')}",
                            f"  - intervention_reason: {step.get('intervention_decision', {}).get('reason', '')}",
                            f"  - post_reason: {step.get('post_action_report', {}).get('reason', '')}",
                            f"  - repair_reason: {step.get('repair_decision', {}).get('reason', '')}",
                        ]
                    )
            lines.append("")
        (output_dir / f"{mode}.md").write_text("\n".join(lines), encoding="utf-8")


def _copy_raw_logs(log_dirs: dict[str, Path], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for mode, log_dir in log_dirs.items():
        mode_dir = output_dir / mode
        mode_dir.mkdir(parents=True, exist_ok=True)
        for name in ("config.json", "episodes.jsonl", "steps.jsonl", "intervention_events.jsonl"):
            src = log_dir / name
            if src.exists():
                shutil.copy2(src, mode_dir / name)


def _repair_post_error_windows(
    steps_by_task: dict[int, list[dict[str, Any]]]
) -> tuple[int, int, int, int]:
    post_before = 0
    post_after = 0
    steps_before = 0
    steps_after = 0
    for task_steps in steps_by_task.values():
        repair_indices = [
            int(step["step_id"])
            for step in task_steps
            if step.get("action_source") == "post_action_repair"
        ]
        if not repair_indices:
            continue
        first_repair = min(repair_indices)
        for step in task_steps:
            step_id = int(step["step_id"])
            if step_id < first_repair:
                steps_before += 1
                if step.get("post_action_report", {}).get("post_error"):
                    post_before += 1
            elif step_id > first_repair:
                steps_after += 1
                if step.get("post_action_report", {}).get("post_error"):
                    post_after += 1
    return post_before, post_after, steps_before, steps_after


def _steps_by_task(steps: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_task: dict[int, list[dict[str, Any]]] = {}
    for step in steps:
        by_task.setdefault(int(step["task_id"]), []).append(step)
    for task_steps in by_task.values():
        task_steps.sort(key=lambda item: int(item.get("step_id", 0)))
    return by_task


def _episodes_by_task(episodes: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(episode["task_id"]): episode for episode in episodes}


def _episode_success_rate(episodes: list[dict[str, Any]], task_ids: set[int]) -> float:
    if not task_ids:
        return 0.0
    by_task = _episodes_by_task(episodes)
    return _ratio(
        sum(1 for task_id in task_ids if by_task.get(task_id, {}).get("final_success")),
        len(task_ids),
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _avg(values: list[float | int]) -> float:
    return float(mean(values)) if values else 0.0


def _ratio(num: int | float, den: int | float) -> float:
    return float(num) / float(den) if den else 0.0


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _signed(value: float) -> str:
    return f"{value:+.4f}"


def _escape_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")[:180]


if __name__ == "__main__":
    main()
