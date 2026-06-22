"""Analyze rule_shadow_v1 trajectories.

This is an offline report utility. It does not run the agent, call an LLM, or
modify the shadow policy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    args = parse_args()
    trajectories = load_trajectories(Path(args.trajectories))
    report = analyze(trajectories)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "pre_post_diagnostics.json", report)
    write_step_jsonl(out_dir / "pre_post_step_diagnostics.jsonl", report)
    (out_dir / "pre_post_accuracy_zh.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    write_state_snapshots(
        trajectories=trajectories,
        path=Path(args.state_snapshots),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trajectories",
        default="logs/rule_shadow_v1_webshop20/trajectories.jsonl",
    )
    parser.add_argument(
        "--output_dir",
        default="reports/rule_shadow_v1_webshop20",
    )
    parser.add_argument(
        "--state_snapshots",
        default="logs/rule_shadow_v1_webshop20/state_snapshots_compact.jsonl",
    )
    return parser.parse_args()


def load_trajectories(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def analyze(trajectories: list[dict[str, Any]]) -> dict[str, Any]:
    samples = []
    all_steps = []
    for trajectory in trajectories:
        sample = analyze_sample(trajectory)
        samples.append(sample)
        all_steps.extend(sample["steps"])
    overall = summarize_steps(samples=samples, steps=all_steps)
    return {
        "definitions": definitions(),
        "overall": overall,
        "samples": samples,
    }


def analyze_sample(trajectory: dict[str, Any]) -> dict[str, Any]:
    seen_no_info: set[tuple[str, str]] = set()
    steps = []
    for step in trajectory.get("steps", []):
        action_record = step["action_record"]
        pre = action_record.get("pre_check") or {}
        post = action_record.get("post_check") or {}
        context_before = str(action_record.get("context_before") or "")
        context_after = str(post.get("context_after") or step.get("observation_after_hash") or "")
        signature = str(action_record.get("action_signature") or "")
        same_context = context_before == context_after
        reward = float(step.get("reward") or 0.0)
        done = bool(step.get("done"))
        info_gain = bool(post.get("info_gain"))
        observable_no_effect = same_context and not done and reward == 0.0
        visible_or_terminal_effect = not observable_no_effect
        predicted_no_effect = not info_gain
        expected_repeat_rule = (context_before, signature) in seen_no_info
        repeat_flag = bool(pre.get("repeat_known_no_info"))
        format_valid = bool(pre.get("format_valid"))
        parsed_format_valid = bool((action_record.get("parsed_action") or {}).get("format_valid"))

        if predicted_no_effect and observable_no_effect:
            post_no_effect_label = "TP"
        elif predicted_no_effect and not observable_no_effect:
            post_no_effect_label = "FP"
        elif not predicted_no_effect and observable_no_effect:
            post_no_effect_label = "FN"
        else:
            post_no_effect_label = "TN"

        if repeat_flag and not visible_or_terminal_effect:
            repeat_operational_label = "TP"
        elif repeat_flag and visible_or_terminal_effect:
            repeat_operational_label = "FP"
        elif not repeat_flag and expected_repeat_rule:
            repeat_operational_label = "FN"
        else:
            repeat_operational_label = "TN"

        param_checks = action_record.get("param_checks") or {}
        param_known = sum(1 for item in param_checks.values() if item.get("known"))
        param_unknown = sum(1 for item in param_checks.values() if not item.get("known"))
        step_diag = {
            "task_id": trajectory.get("task_id"),
            "step": step.get("step"),
            "raw_action": action_record.get("raw"),
            "action_type": action_record.get("type"),
            "params": action_record.get("params"),
            "format_valid": format_valid,
            "format_rule_agrees_with_parser": format_valid == parsed_format_valid,
            "param_known_count": param_known,
            "param_unknown_count": param_unknown,
            "pre_repeat_known_no_info": repeat_flag,
            "expected_repeat_rule_from_history": expected_repeat_rule,
            "pre_repeat_rule_agrees": repeat_flag == expected_repeat_rule,
            "pre_repeat_operational_label": repeat_operational_label,
            "post_info_gain": info_gain,
            "post_new_attr_count": len(post.get("new_attrs") or []),
            "post_new_attr_keys": [item.get("key") for item in (post.get("new_attrs") or [])[:30]],
            "context_before": context_before,
            "context_after": context_after,
            "same_context": same_context,
            "observable_no_effect": observable_no_effect,
            "post_predicted_no_effect": predicted_no_effect,
            "post_no_effect_label": post_no_effect_label,
            "reward": reward,
            "done": done,
            "success_after_step": done and reward > 0.0,
            "note": step_note(
                repeat_flag=repeat_flag,
                repeat_operational_label=repeat_operational_label,
                info_gain=info_gain,
                post_no_effect_label=post_no_effect_label,
                same_context=same_context,
                done=done,
                reward=reward,
            ),
        }
        steps.append(step_diag)
        if not info_gain:
            seen_no_info.add((context_before, signature))
    counts = summarize_step_counts(steps)
    return {
        "task_id": trajectory.get("task_id"),
        "success": bool(trajectory.get("success")),
        "reward": float(trajectory.get("reward") or 0.0),
        "num_steps": int(trajectory.get("num_steps") or len(steps)),
        "task_instruction": trajectory.get("task_instruction"),
        "counts": counts,
        "steps": steps,
    }


def summarize_steps(samples: list[dict[str, Any]], steps: list[dict[str, Any]]) -> dict[str, Any]:
    counts = summarize_step_counts(steps)
    num_steps = len(steps)
    num_samples = len(samples)
    success_count = sum(1 for item in samples if item.get("success"))
    post_tp = counts["post_no_effect_TP"]
    post_fp = counts["post_no_effect_FP"]
    post_fn = counts["post_no_effect_FN"]
    post_tn = counts["post_no_effect_TN"]
    repeat_tp = counts["pre_repeat_operational_TP"]
    repeat_fp = counts["pre_repeat_operational_FP"]
    return {
        "num_samples": num_samples,
        "num_steps": num_steps,
        "success_count": success_count,
        "success_rate": safe_div(success_count, num_samples),
        "avg_reward": safe_div(sum(item["reward"] for item in samples), num_samples),
        "avg_steps": safe_div(sum(item["num_steps"] for item in samples), num_samples),
        **counts,
        "format_accuracy_against_parser": safe_div(
            counts["format_rule_agrees_with_parser"],
            num_steps,
        ),
        "pre_repeat_strict_accuracy": safe_div(
            counts["pre_repeat_rule_agrees"],
            num_steps,
        ),
        "pre_repeat_operational_false_discovery_rate": safe_div(
            repeat_fp,
            repeat_tp + repeat_fp,
        ),
        "post_no_effect_accuracy_observable": safe_div(
            post_tp + post_tn,
            post_tp + post_fp + post_fn + post_tn,
        ),
        "post_no_effect_false_discovery_rate_observable": safe_div(
            post_fp,
            post_tp + post_fp,
        ),
        "post_no_effect_false_positive_rate_observable": safe_div(
            post_fp,
            post_fp + post_tn,
        ),
        "post_no_effect_false_negative_rate_observable": safe_div(
            post_fn,
            post_fn + post_tp,
        ),
    }


def summarize_step_counts(steps: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "format_valid_count": 0,
        "format_invalid_count": 0,
        "format_rule_agrees_with_parser": 0,
        "param_known_count": 0,
        "param_unknown_count": 0,
        "pre_repeat_flag_count": 0,
        "pre_repeat_rule_agrees": 0,
        "pre_repeat_strict_disagreement": 0,
        "pre_repeat_operational_TP": 0,
        "pre_repeat_operational_FP": 0,
        "pre_repeat_operational_FN": 0,
        "pre_repeat_operational_TN": 0,
        "post_info_gain_true_count": 0,
        "post_info_gain_false_count": 0,
        "observable_no_effect_count": 0,
        "post_no_effect_TP": 0,
        "post_no_effect_FP": 0,
        "post_no_effect_FN": 0,
        "post_no_effect_TN": 0,
    }
    for step in steps:
        counts["format_valid_count" if step["format_valid"] else "format_invalid_count"] += 1
        if step["format_rule_agrees_with_parser"]:
            counts["format_rule_agrees_with_parser"] += 1
        counts["param_known_count"] += int(step["param_known_count"])
        counts["param_unknown_count"] += int(step["param_unknown_count"])
        if step["pre_repeat_known_no_info"]:
            counts["pre_repeat_flag_count"] += 1
        if step["pre_repeat_rule_agrees"]:
            counts["pre_repeat_rule_agrees"] += 1
        else:
            counts["pre_repeat_strict_disagreement"] += 1
        counts[f"pre_repeat_operational_{step['pre_repeat_operational_label']}"] += 1
        counts["post_info_gain_true_count" if step["post_info_gain"] else "post_info_gain_false_count"] += 1
        if step["observable_no_effect"]:
            counts["observable_no_effect_count"] += 1
        counts[f"post_no_effect_{step['post_no_effect_label']}"] += 1
    return counts


def definitions() -> dict[str, str]:
    return {
        "format_accuracy": "pre.format_valid compared with the parser result. This has a real mechanical label.",
        "pre_repeat_strict_accuracy": "pre.repeat_known_no_info compared with the exact rule: same context and same action signature previously had post.info_gain=false.",
        "pre_repeat_operational_false_positive": "A repeat warning is counted as operational FP if the flagged action still produced an observable effect: context changed, episode ended, or reward changed.",
        "post_info_gain": "The detector's native target: whether the extractor found a new attribute key or value after the action.",
        "observable_no_effect": "Heuristic audit label: context_before == context_after and done=false and reward=0.",
        "post_no_effect_confusion": "Treat post.info_gain=false as a no-effect prediction, then compare with observable_no_effect. This is useful for auditing but stricter than the v1 design target.",
    }


def step_note(
    repeat_flag: bool,
    repeat_operational_label: str,
    info_gain: bool,
    post_no_effect_label: str,
    same_context: bool,
    done: bool,
    reward: float,
) -> str:
    parts = []
    if repeat_flag:
        if repeat_operational_label == "FP":
            parts.append("pre repeat flagged, but the action still had an observable or terminal effect")
        else:
            parts.append("pre repeat flagged and the action remained no-effect under the observable audit label")
    if not info_gain and post_no_effect_label == "FP":
        if done:
            parts.append("post saw no new attributes, but the episode ended")
        elif not same_context:
            parts.append("post saw no new attributes, but navigation returned to an already known context")
        elif reward != 0.0:
            parts.append("post saw no new attributes, but reward changed")
    if info_gain and post_no_effect_label == "FN":
        parts.append("post found new attributes even though the observable context did not change")
    return "; ".join(parts) or "no audit disagreement"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_step_jsonl(path: Path, report: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for sample in report["samples"]:
            for step in sample["steps"]:
                fh.write(json.dumps(step, ensure_ascii=False) + "\n")


def write_state_snapshots(trajectories: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for trajectory in trajectories:
            final_state = trajectory.get("shadow_state") or {}
            for step in trajectory.get("steps", []):
                summary = step.get("attributes_summary") or {}
                row = {
                    "task_id": trajectory.get("task_id"),
                    "step": step.get("step"),
                    "state_keys": sorted(final_state.keys()),
                    "num_attributes_after_step": summary.get("num_attributes"),
                    "num_actions_after_step": summary.get("num_actions"),
                    "current_context_after_step": summary.get("current_context"),
                    "sample_attributes_after_step": summary.get("sample"),
                    "action_record": step.get("action_record"),
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def render_markdown(report: dict[str, Any]) -> str:
    overall = report["overall"]
    lines = [
        "# rule-based shadow v1 pre/post 准确性分析",
        "",
        "## 结论先说",
        "",
        "这个框架的状态表和动作表是跨 benchmark 设计的，但当前实测效果只对 WebShop 前 20 条成立。",
        "跨 benchmark 可迁移的是 loop、attributes/actions schema、format parser、known/unknown 参数记录和 info_gain 的比较方法。",
        "不可直接保证迁移的是 extractor 的质量和 action grammar：OSWorld、tau-bench、WebArena 等环境需要各自 adapter，把 observation、available actions、entity/property 抽取映射到同一套 attributes schema。",
        "",
        "因此它不是“只能在 WebShop 生效”的结构，但目前不能声称在其他 benchmark 上有同等检测准确率。要跨 benchmark 测试，需要为新环境补 observation/action adapter，然后用同一份分析脚本复核误报。",
        "",
        "## 准确率定义",
        "",
        "- format 检测有机械真值：`pre.format_valid` 与 parser 结果比较。",
        "- pre repeat 检测有规则真值：同一 context、同一 action_signature 之前是否出现过 `post.info_gain=false`。",
        "- post 的原生目标不是“动作是否正确”，而是“是否出现新的 attribute value”。",
        "- 为了估计误报，我额外使用一个启发式标签：`observable_no_effect = context_before == context_after and done=false and reward=0`。",
        "- 如果把 `post.info_gain=false` 当作“no-effect 预测”，再与 `observable_no_effect` 比较，就能得到可审计的 TP/FP/FN/TN。但这比 v1 的原始设计更苛刻，因为回到已见过页面会被 post 记为 no new info，即使它确实发生了导航。",
        "",
        "## 总体统计",
        "",
        f"- 样本数：{overall['num_samples']}",
        f"- step/action 数：{overall['num_steps']}",
        f"- 成功率：{overall['success_count']} / {overall['num_samples']} = {overall['success_rate']:.4f}",
        f"- 平均 reward：{overall['avg_reward']:.4f}",
        f"- 平均步数：{overall['avg_steps']:.2f}",
        f"- format invalid：{overall['format_invalid_count']}",
        f"- format accuracy against parser：{overall['format_accuracy_against_parser']:.4f}",
        f"- pre repeat flag：{overall['pre_repeat_flag_count']}",
        f"- pre repeat strict disagreement：{overall['pre_repeat_strict_disagreement']}",
        f"- pre repeat strict accuracy：{overall['pre_repeat_strict_accuracy']:.4f}",
        f"- pre repeat operational FP：{overall['pre_repeat_operational_FP']}",
        f"- pre repeat operational FDR：{overall['pre_repeat_operational_false_discovery_rate']:.4f}",
        f"- post info_gain true / false：{overall['post_info_gain_true_count']} / {overall['post_info_gain_false_count']}",
        f"- observable no-effect：{overall['observable_no_effect_count']}",
        f"- post no-effect TP/FP/FN/TN：{overall['post_no_effect_TP']} / {overall['post_no_effect_FP']} / {overall['post_no_effect_FN']} / {overall['post_no_effect_TN']}",
        f"- post no-effect observable accuracy：{overall['post_no_effect_accuracy_observable']:.4f}",
        f"- post no-effect observable FDR：{overall['post_no_effect_false_discovery_rate_observable']:.4f}",
        f"- post no-effect observable FPR：{overall['post_no_effect_false_positive_rate_observable']:.4f}",
        f"- post no-effect observable FNR：{overall['post_no_effect_false_negative_rate_observable']:.4f}",
        "",
        "## 逐样例汇总",
        "",
        "| task | success | reward | steps | pre_strict_acc | pre_repeat | pre_repeat_FDR | post_info_false | post TP/FP/FN/TN | post_acc | post_FDR | post_FPR |",
        "|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for sample in report["samples"]:
        c = sample["counts"]
        denom = c["post_no_effect_TP"] + c["post_no_effect_FP"] + c["post_no_effect_FN"] + c["post_no_effect_TN"]
        post_acc = safe_div(c["post_no_effect_TP"] + c["post_no_effect_TN"], denom)
        pre_strict_acc = safe_div(c["pre_repeat_rule_agrees"], sample["num_steps"])
        pre_fdr = safe_div(
            c["pre_repeat_operational_FP"],
            c["pre_repeat_operational_TP"] + c["pre_repeat_operational_FP"],
        )
        post_fdr = safe_div(c["post_no_effect_FP"], c["post_no_effect_TP"] + c["post_no_effect_FP"])
        post_fpr = safe_div(c["post_no_effect_FP"], c["post_no_effect_FP"] + c["post_no_effect_TN"])
        lines.append(
            f"| {sample['task_id']} | {str(sample['success']).lower()} | {sample['reward']:.4f} | {sample['num_steps']} | "
            f"{pre_strict_acc:.4f} | {c['pre_repeat_flag_count']} | {pre_fdr:.4f} | {c['post_info_gain_false_count']} | "
            f"{c['post_no_effect_TP']}/{c['post_no_effect_FP']}/{c['post_no_effect_FN']}/{c['post_no_effect_TN']} | "
            f"{post_acc:.4f} | {post_fdr:.4f} | {post_fpr:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 文件索引",
            "",
            "- 完整原始轨迹和最终 shadow_state：`logs/rule_shadow_v1_webshop20/trajectories.jsonl`",
            "- 紧凑 state snapshot：`logs/rule_shadow_v1_webshop20/state_snapshots_compact.jsonl`",
            "- 逐 step 诊断 JSONL：`reports/rule_shadow_v1_webshop20/pre_post_step_diagnostics.jsonl`",
            "- 完整诊断 JSON：`reports/rule_shadow_v1_webshop20/pre_post_diagnostics.json`",
            "- 本报告：`reports/rule_shadow_v1_webshop20/pre_post_accuracy_zh.md`",
            "",
            "## 读数提醒",
            "",
            "post 的 FP 高，主要不是代码 bug，而是定义差异：v1 的 `info_gain=false` 表示没有新属性，不等于动作完全无效。例如返回已访问过的列表页，context 发生变化，但没有新 attribute value，会在 no-effect 启发式审计里算作 FP。",
            "",
        ]
    )
    return "\n".join(lines)


def safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


if __name__ == "__main__":
    main()
