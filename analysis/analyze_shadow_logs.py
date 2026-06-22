"""Analyze action-centric WebShop shadow logs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Callable


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log_dir", default="logs/webshop_shadow_qwen20_max15")
    parser.add_argument("--report_dir", default="reports/webshop_shadow_qwen20_max15")
    args = parser.parse_args()
    analyze_shadow_logs(Path(args.log_dir), Path(args.report_dir))


def analyze_shadow_logs(log_dir: Path, report_dir: Path) -> dict[str, Any]:
    config = read_json(log_dir / "config.json")
    steps = read_jsonl(log_dir / "steps.jsonl")
    episodes = read_jsonl(log_dir / "episodes.jsonl")
    alerts = read_jsonl(log_dir / "alert_review.jsonl")
    metrics = compute_metrics(steps, episodes, alerts)
    cases = build_case_analysis(steps, episodes)

    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(report_dir / "metrics.json", metrics)
    with (report_dir / "case_analysis.jsonl").open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=True) + "\n")
    (report_dir / "summary_zh.md").write_text(render_summary(config, metrics, cases), encoding="utf-8")
    return metrics


def compute_metrics(
    steps: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
) -> dict[str, Any]:
    total_episodes = len(episodes)
    total_steps = len(steps)
    successes = [episode for episode in episodes if episode.get("success")]
    failures = [episode for episode in episodes if not episode.get("success")]
    pre_warning_steps = [step for step in steps if step["pre_report"].get("pre_warning")]
    pre_error_steps = [step for step in steps if step["pre_report"].get("pre_error")]
    post_warning_steps = [step for step in steps if step["post_report"].get("post_warning")]
    post_error_steps = [step for step in steps if step["post_report"].get("post_error")]
    prompt_state_leak_steps = [step for step in steps if step.get("agent_prompt_contains_state_summary")]
    action_changed_steps = [step for step in steps if step.get("action_changed")]

    pre_categories = Counter()
    post_categories = Counter()
    for step in steps:
        pre_categories.update(step["pre_report"].get("categories", []))
        post_categories.update(step["post_report"].get("categories", []))

    episode_failed = {int(episode["task_id"]): not episode.get("success") for episode in episodes}
    episode_success = {int(episode["task_id"]): bool(episode.get("success")) for episode in episodes}
    pre_episode_pred = episode_prediction(steps, lambda step: step["pre_report"].get("pre_warning"))
    pre_error_episode_pred = episode_prediction(steps, lambda step: step["pre_report"].get("pre_error"))
    post_episode_pred = episode_prediction(steps, lambda step: step["post_report"].get("post_warning"))
    post_error_episode_pred = episode_prediction(steps, lambda step: step["post_report"].get("post_error"))

    return {
        "total_episodes": total_episodes,
        "total_steps": total_steps,
        "success_count": len(successes),
        "failure_count": len(failures),
        "success_rate": ratio(len(successes), total_episodes),
        "avg_reward": avg([episode.get("final_reward", 0.0) for episode in episodes]),
        "avg_steps": avg([episode.get("num_steps", 0) for episode in episodes]),
        "shadow_integrity": {
            "action_changed_steps": len(action_changed_steps),
            "state_to_agent_prompt_leak_steps": len(prompt_state_leak_steps),
            "raw_equals_executed": len(action_changed_steps) == 0,
            "state_to_agent_false": len(prompt_state_leak_steps) == 0,
        },
        "pre": {
            "warning_steps": len(pre_warning_steps),
            "error_steps": len(pre_error_steps),
            "warning_step_rate": ratio(len(pre_warning_steps), total_steps),
            "error_step_rate": ratio(len(pre_error_steps), total_steps),
            "category_counts": dict(pre_categories),
            "failure_recall_warning": recall(pre_episode_pred, episode_failed),
            "failure_recall_error": recall(pre_error_episode_pred, episode_failed),
            "success_warning_rate": false_positive_rate(pre_episode_pred, episode_success),
            "success_error_rate": false_positive_rate(pre_error_episode_pred, episode_success),
            "true_positive_warning_episodes": true_positive_count(pre_episode_pred, episode_failed),
            "false_positive_warning_episodes": false_positive_count(pre_episode_pred, episode_success),
            "true_positive_error_episodes": true_positive_count(pre_error_episode_pred, episode_failed),
            "false_positive_error_episodes": false_positive_count(pre_error_episode_pred, episode_success),
        },
        "post": {
            "warning_steps": len(post_warning_steps),
            "error_steps": len(post_error_steps),
            "warning_step_rate": ratio(len(post_warning_steps), total_steps),
            "error_step_rate": ratio(len(post_error_steps), total_steps),
            "category_counts": dict(post_categories),
            "failure_recall_warning": recall(post_episode_pred, episode_failed),
            "failure_recall_error": recall(post_error_episode_pred, episode_failed),
            "success_warning_rate": false_positive_rate(post_episode_pred, episode_success),
            "success_error_rate": false_positive_rate(post_error_episode_pred, episode_success),
            "true_positive_warning_episodes": true_positive_count(post_episode_pred, episode_failed),
            "false_positive_warning_episodes": false_positive_count(post_episode_pred, episode_success),
            "true_positive_error_episodes": true_positive_count(post_error_episode_pred, episode_failed),
            "false_positive_error_episodes": false_positive_count(post_error_episode_pred, episode_success),
        },
        "alert_review_rows": len(alerts),
        "llm_state": {
            "fallback_steps": sum(1 for step in steps if step["state_before_metadata"].get("fallback_used")),
            "parse_error_steps": sum(1 for step in steps if step["state_before_metadata"].get("parse_error")),
            "request_error_steps": sum(1 for step in steps if step["state_before_metadata"].get("request_error")),
        },
    }


def build_case_analysis(
    steps: list[dict[str, Any]], episodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_task: dict[int, list[dict[str, Any]]] = {}
    for step in steps:
        by_task.setdefault(int(step["task_id"]), []).append(step)
    cases: list[dict[str, Any]] = []
    for episode in episodes:
        task_id = int(episode["task_id"])
        task_steps = by_task.get(task_id, [])
        first_pre = first_matching(task_steps, lambda step: step["pre_report"].get("pre_warning"))
        first_post = first_matching(task_steps, lambda step: step["post_report"].get("post_warning"))
        first_error = first_matching(
            task_steps,
            lambda step: step["pre_report"].get("pre_error") or step["post_report"].get("post_error"),
        )
        cases.append(
            {
                "task_id": task_id,
                "task_instruction": episode.get("task_instruction", ""),
                "success": bool(episode.get("success")),
                "final_reward": episode.get("final_reward"),
                "num_steps": episode.get("num_steps"),
                "first_pre_warning": compact_step(first_pre),
                "first_post_warning": compact_step(first_post),
                "first_error": compact_step(first_error),
                "trajectory": [compact_step(step) for step in task_steps],
                "manual_review_hint": review_hint(episode, first_pre, first_post, first_error),
            }
        )
    return cases


def compact_step(step: dict[str, Any] | None) -> dict[str, Any] | None:
    if step is None:
        return None
    return {
        "step_id": step.get("step_id"),
        "raw_action": step.get("raw_action"),
        "executed_action": step.get("executed_action"),
        "pre_warning": step["pre_report"].get("pre_warning"),
        "pre_error": step["pre_report"].get("pre_error"),
        "pre_categories": step["pre_report"].get("categories", []),
        "post_warning": step["post_report"].get("post_warning"),
        "post_error": step["post_report"].get("post_error"),
        "post_categories": step["post_report"].get("categories", []),
        "reward": step.get("reward"),
        "done": step.get("done"),
    }


def review_hint(
    episode: dict[str, Any],
    first_pre: dict[str, Any] | None,
    first_post: dict[str, Any] | None,
    first_error: dict[str, Any] | None,
) -> str:
    if episode.get("success") and first_error:
        return "任务成功但检测器报 error，优先人工复核是否为误报。"
    if not episode.get("success") and not first_pre and not first_post:
        return "任务失败但 shadow 没抓到明显风险，属于漏检候选。"
    if not episode.get("success") and first_error:
        return "任务失败且已有 error，可从 first_error 步骤溯源。"
    if not episode.get("success"):
        return "任务失败且仅有 warning，检查 warning 是否足以提前预警。"
    return "任务成功且无 error，通常作为正常样本。"


def render_summary(config: dict[str, Any], metrics: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    lines = [
        "# WebShop Shadow-only 检测报告",
        "",
        "本报告只对应当前最小版本：ReAct agent 正常动作，Action-Centric State 只做 shadow 检测，不干预、不修复、不回滚。",
        "",
        "## 运行配置",
        "",
        f"- run_id: `{config.get('run_id', 'unknown')}`",
        f"- env: `{config.get('env', 'unknown')}` / requested `{config.get('requested_env', 'unknown')}`",
        f"- model: `{config.get('model', 'unknown')}`",
        f"- tasks: {config.get('start_index', 0)} - {config.get('start_index', 0) + config.get('num_tasks', 0) - 1}",
        f"- max_steps: {config.get('max_steps', 'unknown')}",
        f"- state_to_agent: `{config.get('state_to_agent', False)}`",
        "",
        "## 核心结果",
        "",
        f"- 成功率: {metrics['success_count']}/{metrics['total_episodes']} = {metrics['success_rate']:.4f}",
        f"- 平均 reward: {metrics['avg_reward']:.4f}",
        f"- 平均步数: {metrics['avg_steps']:.2f}",
        f"- action 被改写步数: {metrics['shadow_integrity']['action_changed_steps']}",
        f"- agent prompt 中出现 state summary 的步数: {metrics['shadow_integrity']['state_to_agent_prompt_leak_steps']}",
        "",
        "## Pre-action 检测",
        "",
        f"- warning 步数: {metrics['pre']['warning_steps']}，error 步数: {metrics['pre']['error_steps']}",
        f"- warning 对失败任务召回: {metrics['pre']['failure_recall_warning']:.4f}",
        f"- warning 在成功任务上的触发率: {metrics['pre']['success_warning_rate']:.4f}",
        f"- 正判 warning episode: {metrics['pre']['true_positive_warning_episodes']}，疑似误报 warning episode: {metrics['pre']['false_positive_warning_episodes']}",
        f"- 类别计数: `{metrics['pre']['category_counts']}`",
        "",
        "## Post-action 检测",
        "",
        f"- warning 步数: {metrics['post']['warning_steps']}，error 步数: {metrics['post']['error_steps']}",
        f"- warning 对失败任务召回: {metrics['post']['failure_recall_warning']:.4f}",
        f"- warning 在成功任务上的触发率: {metrics['post']['success_warning_rate']:.4f}",
        f"- 正判 warning episode: {metrics['post']['true_positive_warning_episodes']}，疑似误报 warning episode: {metrics['post']['false_positive_warning_episodes']}",
        f"- 类别计数: `{metrics['post']['category_counts']}`",
        "",
        "## 样例索引",
        "",
    ]
    for case in cases[:10]:
        lines.append(
            f"- task {case['task_id']}: success={case['success']}, steps={case['num_steps']}, hint={case['manual_review_hint']}"
        )
    lines.append("")
    lines.append("完整逐任务分析见 `case_analysis.jsonl`；原始逐步轨迹见对应 log 目录的 `steps.jsonl`。")
    return "\n".join(lines) + "\n"


def episode_prediction(
    steps: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]
) -> dict[int, bool]:
    predicted: dict[int, bool] = {}
    for step in steps:
        task_id = int(step["task_id"])
        predicted[task_id] = predicted.get(task_id, False) or bool(predicate(step))
    return predicted


def recall(predicted: dict[int, bool], failed: dict[int, bool]) -> float:
    positive = [task_id for task_id, is_failed in failed.items() if is_failed]
    hits = sum(1 for task_id in positive if predicted.get(task_id))
    return ratio(hits, len(positive))


def false_positive_rate(predicted: dict[int, bool], succeeded: dict[int, bool]) -> float:
    positive = [task_id for task_id, is_success in succeeded.items() if is_success]
    hits = sum(1 for task_id in positive if predicted.get(task_id))
    return ratio(hits, len(positive))


def true_positive_count(predicted: dict[int, bool], failed: dict[int, bool]) -> int:
    return sum(1 for task_id, is_failed in failed.items() if is_failed and predicted.get(task_id))


def false_positive_count(predicted: dict[int, bool], succeeded: dict[int, bool]) -> int:
    return sum(1 for task_id, is_success in succeeded.items() if is_success and predicted.get(task_id))


def first_matching(
    steps: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]
) -> dict[str, Any] | None:
    for step in steps:
        if predicate(step):
            return step
    return None


def avg(values: list[float | int]) -> float:
    return float(mean(values)) if values else 0.0


def ratio(num: int, den: int) -> float:
    return float(num / den) if den else 0.0


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
