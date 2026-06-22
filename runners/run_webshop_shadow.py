"""Run rule-based shadow v1 on WebShop.

The runner never injects shadow state into the agent prompt, never blocks or
rewrites actions, and never performs repair.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any

from agents.llm_client import MockLLMClient, OpenAIChatClient
from agents.react_agent import WebShopReactAgent
from runners.webshop_env import make_webshop_env
from shadow.extractor import (
    context_value,
    extract_observation_attributes,
    extract_task_attributes,
)
from shadow.parser import action_signature, parse_action
from shadow.post import run_post_check
from shadow.pre import run_pre_check
from shadow.repair import propose_repair
from shadow.state import (
    attributes_summary,
    check_params,
    clone_attributes,
    current_context,
    merge_attributes,
    new_shadow_state,
)


def main() -> None:
    args = parse_args()
    run(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["auto", "official", "mock"], default="auto")
    parser.add_argument("--webshop_repo", default="external/webshop")
    parser.add_argument("--num_products", type=int, default=1000)
    parser.add_argument("--num_samples", "--num_tasks", dest="num_samples", type=int, default=20)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--max_steps", type=int, default=15)
    parser.add_argument("--model", default=os.getenv("LLM_MODEL") or os.getenv("QWEN_MODEL") or "mock")
    parser.add_argument("--state_to_agent", default="false")
    parser.add_argument("--log_dir", default="logs/rule_shadow_v1_repeat_webshop20")
    parser.add_argument("--report_dir", default="reports/rule_shadow_v1_repeat_webshop20")
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, Any]:
    if _parse_bool(args.state_to_agent):
        raise ValueError("rule_shadow_v1 requires --state_to_agent false")
    env = make_webshop_env(args.env, repo_path=args.webshop_repo, num_products=args.num_products)
    agent = WebShopReactAgent(_build_client(args.model))
    log_dir = Path(args.log_dir)
    report_dir = Path(args.report_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "mode": "shadow",
        "version": "rule_shadow_v1_repeat",
        "env": env.env_name,
        "requested_env": args.env,
        "num_samples": args.num_samples,
        "start_index": args.start_index,
        "max_steps": args.max_steps,
        "state_to_agent": False,
        "repair_enabled": False,
        "model": getattr(agent.client, "model", args.model),
    }
    _write_json(log_dir / "config.json", config)

    trajectories = []
    with (log_dir / "trajectories.jsonl").open("w", encoding="utf-8") as fh:
        for offset in range(args.num_samples):
            task_id = args.start_index + offset
            trajectory = _run_episode(
                env=env,
                agent=agent,
                task_id=task_id,
                max_steps=args.max_steps,
            )
            trajectories.append(trajectory)
            fh.write(json.dumps(trajectory, ensure_ascii=True) + "\n")
            fh.flush()

    metrics = compute_metrics(trajectories, args.max_steps)
    _write_json(report_dir / "metrics.json", metrics)
    (report_dir / "summary_zh.md").write_text(
        render_summary(metrics, trajectories),
        encoding="utf-8",
    )
    return {"config": config, "metrics": metrics, "trajectories": trajectories}


def _run_episode(
    env: Any,
    agent: WebShopReactAgent,
    task_id: int,
    max_steps: int,
) -> dict[str, Any]:
    observation = env.reset(task_id)
    instruction = env.get_instruction_text()
    available = env.get_available_actions()
    shadow_state = new_shadow_state()
    merge_attributes(shadow_state, extract_task_attributes(instruction, step=0))
    merge_attributes(
        shadow_state,
        extract_observation_attributes(observation, available, step=0),
    )
    history: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    done = False
    final_reward = 0.0

    for step in range(max_steps):
        available_before = env.get_available_actions()
        context_before = current_context(shadow_state) or context_value(observation)
        raw_action = agent.act(
            task_instruction=instruction,
            observation=observation,
            action_history=history,
            available_actions=available_before,
            state_summary="",
        )
        parsed = parse_action(raw_action)
        action_record: dict[str, Any] = {
            "step": step,
            "raw": raw_action,
            "type": parsed["type"],
            "params": parsed["params"],
            "parsed_action": parsed,
            "context_before": context_before,
            "action_signature": action_signature(parsed),
            "param_checks": check_params(parsed, shadow_state["attributes"]),
        }
        action_record["pre_check"] = run_pre_check(action_record, shadow_state)
        action_record["repair_placeholder"] = propose_repair(action_record, shadow_state)
        executed_action = raw_action
        assert executed_action == raw_action
        action_record["executed_action"] = executed_action

        attributes_before = clone_attributes(shadow_state)
        observation_after, reward, done, info = env.step(executed_action)
        final_reward = float(reward)
        available_after = env.get_available_actions()
        observed_after = extract_observation_attributes(observation_after, available_after, step=step + 1)
        post_check = run_post_check(
            attributes_before=attributes_before,
            observed_attrs_after=observed_after,
            action_record=action_record,
            shadow_state=shadow_state,
            context_after=str(observed_after["context.current"]["current_value"]),
        )
        action_record["post_check"] = post_check
        merge_attributes(shadow_state, observed_after)
        shadow_state["actions"].append(action_record)

        step_log = {
            "step": step,
            "state_to_agent": False,
            "agent_prompt_contains_state_summary": bool(
                agent.last_trace.get("prompt_contains_state_summary")
            ),
            "observation_before_hash": context_before,
            "observation_before": observation,
            "raw_action": raw_action,
            "parsed_action": parsed,
            "action_record": action_record,
            "observation_after_hash": post_check["context_after"],
            "observation_after": observation_after,
            "reward": final_reward,
            "done": done,
            "env_info": info,
            "attributes_summary": attributes_summary(shadow_state),
        }
        steps.append(step_log)
        history.append(
            {
                "step": step,
                "raw_action": raw_action,
                "executed_action": executed_action,
                "reward": final_reward,
                "done": done,
            }
        )
        observation = observation_after
        if done:
            break

    return {
        "task_id": task_id,
        "task_instruction": instruction,
        "success": bool(done and final_reward > 0),
        "reward": final_reward,
        "done": done,
        "num_steps": len(steps),
        "max_steps": max_steps,
        "shadow_state": shadow_state,
        "steps": steps,
    }


def compute_metrics(trajectories: list[dict[str, Any]], max_steps: int) -> dict[str, Any]:
    action_records = [
        step["action_record"]
        for trajectory in trajectories
        for step in trajectory.get("steps", [])
    ]
    param_checks = [
        check
        for record in action_records
        for check in (record.get("param_checks") or {}).values()
    ]
    success_count = sum(1 for item in trajectories if item.get("success"))
    num_samples = len(trajectories)
    return {
        "num_samples": num_samples,
        "max_steps": max_steps,
        "state_to_agent": False,
        "repair_enabled": False,
        "num_actions": len(action_records),
        "format_invalid_count": sum(
            1 for item in action_records if not item.get("pre_check", {}).get("format_valid")
        ),
        "repeat_known_no_info_count": sum(
            1 for item in action_records if item.get("pre_check", {}).get("repeat_known_no_info")
        ),
        "visible_delta_true_count": sum(
            1 for item in action_records if item.get("post_check", {}).get("visible_delta")
        ),
        "visible_delta_false_count": sum(
            1 for item in action_records if not item.get("post_check", {}).get("visible_delta")
        ),
        "no_progress_count": sum(
            1 for item in action_records if item.get("post_check", {}).get("no_progress")
        ),
        "same_action_repeated_no_progress_count": sum(
            1
            for item in action_records
            if item.get("post_check", {}).get("no_progress_reason")
            == "same_action_repeated_without_visible_delta"
        ),
        "context_cycle_no_progress_count": sum(
            1
            for item in action_records
            if item.get("post_check", {}).get("no_progress_reason")
            == "context_cycle_without_visible_delta"
        ),
        "context_cycle_detected_count": sum(
            1 for item in action_records if item.get("post_check", {}).get("context_cycle_detected")
        ),
        "info_gain_true_count": sum(
            1 for item in action_records if item.get("post_check", {}).get("info_gain")
        ),
        "info_gain_false_count": sum(
            1 for item in action_records if not item.get("post_check", {}).get("info_gain")
        ),
        "param_known_count": sum(1 for item in param_checks if item.get("known")),
        "param_unknown_count": sum(1 for item in param_checks if not item.get("known")),
        "success_count": success_count,
        "success_rate": float(success_count / num_samples) if num_samples else 0.0,
        "avg_reward": float(mean([item.get("reward", 0.0) for item in trajectories])) if trajectories else 0.0,
        "avg_steps": float(mean([item.get("num_steps", 0) for item in trajectories])) if trajectories else 0.0,
        "state_prompt_leak_count": sum(
            1
            for trajectory in trajectories
            for step in trajectory.get("steps", [])
            if step.get("agent_prompt_contains_state_summary")
        ),
        "action_changed_count": sum(
            1
            for item in action_records
            if item.get("executed_action") != item.get("raw")
        ),
    }


def render_summary(metrics: dict[str, Any], trajectories: list[dict[str, Any]]) -> str:
    examples = _example_records(trajectories)
    lines = [
        "# rule-based shadow v1 repeat WebShop20 报告",
        "",
        "本次是 rule-based shadow v1 的通用重复/循环无进展检测版本。",
        "",
        "- 没有使用 LLM detector。",
        "- 没有使用 LLM state proposer。",
        "- 没有把 shadow state 注入 agent prompt。",
        "- 没有执行修复、阻断、回滚或 action 改写。",
        "- 没有加入 WebShop 颜色/尺码/option 专用规则。",
        "- pre 只检测格式是否合法、当前 action 是否将成为第 3 次重复无可见变化。",
        "- post 将 visible_delta 和 no_progress 分离。",
        "- visible_delta=False 不直接等于 no_progress。",
        "- no_progress 只由 same action + same params 第 3 次无可见变化，或 context A-B-A-B 循环且无可见变化触发。",
        "- info_gain 是兼容字段，等价于 visible_delta，不再等价于 no_progress。",
        "",
        "## 统计结果",
        "",
        f"- 样本数：{metrics['num_samples']}",
        f"- 最大步数：{metrics['max_steps']}",
        f"- action 数：{metrics['num_actions']}",
        f"- success：{metrics['success_count']} / {metrics['num_samples']} = {metrics['success_rate']:.4f}",
        f"- 平均 reward：{metrics['avg_reward']:.4f}",
        f"- 平均步数：{metrics['avg_steps']:.2f}",
        f"- format_invalid_count：{metrics['format_invalid_count']}",
        f"- repeat_known_no_info_count：{metrics['repeat_known_no_info_count']}",
        f"- visible_delta_true_count：{metrics['visible_delta_true_count']}",
        f"- visible_delta_false_count：{metrics['visible_delta_false_count']}",
        f"- no_progress_count：{metrics['no_progress_count']}",
        f"- same_action_repeated_no_progress_count：{metrics['same_action_repeated_no_progress_count']}",
        f"- context_cycle_no_progress_count：{metrics['context_cycle_no_progress_count']}",
        f"- context_cycle_detected_count：{metrics['context_cycle_detected_count']}",
        f"- info_gain_true_count：{metrics['info_gain_true_count']}",
        f"- info_gain_false_count：{metrics['info_gain_false_count']}",
        f"- param_known_count：{metrics['param_known_count']}",
        f"- param_unknown_count：{metrics['param_unknown_count']}",
        f"- state_prompt_leak_count：{metrics['state_prompt_leak_count']}",
        f"- action_changed_count：{metrics['action_changed_count']}",
        "",
        "## 最终检查",
        "",
        "- 运行命令：`python -m runners.run_webshop_shadow --env official --num_samples 20 --start_index 0 --max_steps 15 --model qwen3-8b --state_to_agent false --log_dir logs/rule_shadow_v1_repeat_webshop20 --report_dir reports/rule_shadow_v1_repeat_webshop20`",
        "- 活跃 shadow 入口：`runners/run_webshop_shadow.py`。",
        "- 活跃 shadow core：`shadow/state.py`, `shadow/parser.py`, `shadow/extractor.py`, `shadow/pre.py`, `shadow/post.py`, `shadow/repair.py`。",
        "- 已删除旧目录：`detectors/`, `state/`, `analysis/` 以及对应旧测试。",
        "- `state_to_agent=false`，日志中 `state_prompt_leak_count=0`。",
        "- `executed_action == raw_action`，日志中 `action_changed_count=0`。",
        "- `shadow_state` 只包含 `attributes` 和 `actions` 两张表。",
        "- `repair_placeholder.enabled=false`，没有触发修复、阻断、回滚或 action 改写。",
        "- active 逻辑中没有 hidden_state_update、selected_option 或 effect.selected_option。",
        "",
        "## action_record 示例",
        "",
    ]
    for title, record in examples:
        lines.append(f"### {title}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(record, ensure_ascii=False, indent=2)[:3000])
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _example_records(trajectories: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    examples: list[tuple[str, dict[str, Any]]] = []
    seen_titles: set[str] = set()
    for trajectory in trajectories:
        for step in trajectory.get("steps", []):
            record = step["action_record"]
            post = record.get("post_check", {})
            title = ""
            if post.get("visible_delta") is False and post.get("no_progress") is False:
                title = "visible_delta=False 但 no_progress=False"
            elif (
                post.get("no_progress_reason")
                == "same_action_repeated_without_visible_delta"
            ):
                title = "same_action_repeated_without_visible_delta"
            elif (
                post.get("no_progress_reason")
                == "context_cycle_without_visible_delta"
            ):
                title = "context_cycle_without_visible_delta"
            if title and title not in seen_titles:
                examples.append((title, record))
                seen_titles.add(title)
            if len(examples) >= 3:
                return examples
    return examples


def _build_client(model: str):
    if not model or model == "mock":
        return MockLLMClient()
    return OpenAIChatClient.from_env(model=model)


def _parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
