"""Run action-centric WebShop shadow detection.

This runner is intentionally shadow-only: the detector may warn or flag errors,
but the environment always receives the exact action produced by the agent.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from agents.llm_client import MockLLMClient, OpenAIChatClient
from agents.react_agent import WebShopReactAgent
from detectors.post_action import PostActionDetector
from detectors.pre_action import PreActionDetector
from runners.webshop_env import make_webshop_env
from state.action_state import ActionCentricState
from state.llm_state_proposer import LLMStateProposer


def main() -> None:
    args = parse_args()
    run_webshop_shadow(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["auto", "official", "mock"], default="auto")
    parser.add_argument("--webshop_repo", default="external/webshop")
    parser.add_argument("--num_products", type=int, default=1000)
    parser.add_argument("--num_tasks", type=int, default=20)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--max_steps", type=int, default=15)
    parser.add_argument("--model", default=os.getenv("LLM_MODEL") or os.getenv("QWEN_MODEL") or "mock")
    parser.add_argument("--state_to_agent", default="false")
    parser.add_argument("--log_dir", default="logs/webshop_shadow_qwen20_max15")
    return parser.parse_args()


def run_webshop_shadow(args: argparse.Namespace) -> dict[str, Any]:
    state_to_agent = parse_bool(args.state_to_agent)
    if state_to_agent:
        raise ValueError("This minimal shadow runner requires --state_to_agent false.")

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d_%H%M%S_webshop_shadow")

    env = make_webshop_env(args.env, repo_path=args.webshop_repo, num_products=args.num_products)
    client = build_client(args.model)
    agent = WebShopReactAgent(client)
    proposer = LLMStateProposer(client)
    pre_detector = PreActionDetector()
    post_detector = PostActionDetector()

    config = {
        "run_id": run_id,
        "runner": "webshop_shadow_action_centric",
        "shadow": True,
        "intervention_enabled": False,
        "env": env.env_name,
        "requested_env": args.env,
        "webshop_repo": args.webshop_repo,
        "num_products": args.num_products,
        "num_tasks": args.num_tasks,
        "start_index": args.start_index,
        "max_steps": args.max_steps,
        "model": getattr(client, "model", args.model),
        "state_to_agent": False,
        "state_schema": "ActionCentricState",
        "executed_action_policy": "raw_action_only",
    }
    write_json(log_dir / "config.json", config)

    summaries: list[dict[str, Any]] = []
    with (log_dir / "steps.jsonl").open("w", encoding="utf-8") as step_fh, (
        log_dir / "episodes.jsonl"
    ).open("w", encoding="utf-8") as episode_fh, (log_dir / "alert_review.jsonl").open(
        "w", encoding="utf-8"
    ) as alert_fh:
        for offset in range(args.num_tasks):
            task_id = args.start_index + offset
            summary, alerts = run_episode(
                run_id=run_id,
                task_id=task_id,
                env=env,
                agent=agent,
                proposer=proposer,
                pre_detector=pre_detector,
                post_detector=post_detector,
                max_steps=args.max_steps,
                step_fh=step_fh,
            )
            summaries.append(summary)
            episode_fh.write(json.dumps(summary, ensure_ascii=True) + "\n")
            episode_fh.flush()
            for alert in alerts:
                alert["final_success"] = summary["success"]
                alert["final_reward"] = summary["final_reward"]
                alert_fh.write(json.dumps(alert, ensure_ascii=True) + "\n")
            alert_fh.flush()

    return {"config": config, "episodes": summaries}


def run_episode(
    run_id: str,
    task_id: int,
    env: Any,
    agent: WebShopReactAgent,
    proposer: LLMStateProposer,
    pre_detector: PreActionDetector,
    post_detector: PostActionDetector,
    max_steps: int,
    step_fh: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    observation = env.reset(task_id)
    instruction = env.get_instruction_text()
    history: list[dict[str, Any]] = []
    previous_pre_reports: list[dict[str, Any]] = []
    step_logs: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    previous_state: ActionCentricState | None = None
    final_reward = 0.0
    done = False

    for step_id in range(max_steps):
        available_before = env.get_available_actions()
        raw_action = agent.act(
            task_instruction=instruction,
            observation=observation,
            action_history=history,
            available_actions=available_before,
            state_summary="",
        )
        agent_trace = dict(agent.last_trace)

        state_before_result = proposer.propose(
            task_instruction=instruction,
            observation=observation,
            available_actions=available_before,
            raw_action=raw_action,
            previous_action_state=previous_state,
            step_id=step_id,
        )
        state_before = state_before_result.state
        pre_report = pre_detector.detect(
            raw_action=raw_action,
            available_actions=available_before,
            state=state_before,
            previous_reports=previous_pre_reports,
        )

        executed_action = raw_action
        assert executed_action == raw_action
        next_observation, reward, done, info = env.step(executed_action)
        final_reward = reward
        available_after = env.get_available_actions()

        state_after_result = proposer.propose(
            task_instruction=instruction,
            observation=next_observation,
            available_actions=available_after,
            raw_action=raw_action,
            previous_action_state=state_before,
            step_id=step_id,
        )
        state_after = state_after_result.state
        post_report = post_detector.detect(
            state_before=state_before,
            raw_action=raw_action,
            observation_before=observation,
            observation_after=next_observation,
            state_after=state_after,
            pre_report=pre_report.to_dict(),
            reward=reward,
            done=done,
            previous_step_logs=step_logs,
            before_available=available_before,
            after_available=available_after,
            episode_ending=done or step_id == max_steps - 1,
        )
        state_after.post_check = post_report.to_post_check()

        step_log = {
            "run_id": run_id,
            "task_id": task_id,
            "step_id": step_id,
            "task_instruction": instruction,
            "state_to_agent": False,
            "agent_prompt_contains_state_summary": bool(agent_trace.get("prompt_contains_state_summary")),
            "observation_before": observation,
            "available_actions_before": available_before,
            "raw_action": raw_action,
            "executed_action": executed_action,
            "action_changed": False,
            "state_before": state_before.to_dict(),
            "state_before_metadata": state_metadata(state_before_result),
            "pre_report": pre_report.to_dict(),
            "observation_after": next_observation,
            "available_actions_after": available_after,
            "state_after": state_after.to_dict(),
            "state_after_metadata": state_metadata(state_after_result),
            "post_report": post_report.to_dict(),
            "reward": reward,
            "done": done,
            "env_info": info,
            "agent_trace": agent_trace,
        }
        step_fh.write(json.dumps(step_log, ensure_ascii=True) + "\n")
        step_fh.flush()
        step_logs.append(step_log)
        previous_pre_reports.append(pre_report.to_dict())
        alerts.extend(alert_rows(step_log))

        history.append(
            {
                "step_id": step_id,
                "raw_action": raw_action,
                "executed_action": executed_action,
                "reward": reward,
                "done": done,
            }
        )
        previous_state = state_after
        observation = next_observation
        if done:
            break

    summary = summarize_episode(run_id, task_id, instruction, step_logs, final_reward, done, max_steps)
    return summary, alerts


def build_client(model: str):
    if not model or model == "mock":
        return MockLLMClient()
    return OpenAIChatClient.from_env(model=model)


def state_metadata(result: Any) -> dict[str, Any]:
    return {
        "raw_response": getattr(result, "raw_response", "")[:4000],
        "parse_error": getattr(result, "parse_error", ""),
        "request_error": getattr(result, "request_error", ""),
        "fallback_used": bool(getattr(result, "fallback_used", False)),
    }


def alert_rows(step_log: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    pre = step_log["pre_report"]
    post = step_log["post_report"]
    if pre.get("pre_warning") or pre.get("pre_error") or pre.get("repair_trigger"):
        rows.append(
            {
                "task_id": step_log["task_id"],
                "step_id": step_log["step_id"],
                "phase": "pre",
                "severity": "error" if pre.get("pre_error") else "warning",
                "categories": pre.get("categories", []),
                "raw_action": step_log["raw_action"],
                "reason": pre.get("reason", ""),
                "requires_manual_review": True,
            }
        )
    if post.get("post_warning") or post.get("post_error") or post.get("repair_trigger"):
        rows.append(
            {
                "task_id": step_log["task_id"],
                "step_id": step_log["step_id"],
                "phase": "post",
                "severity": "error" if post.get("post_error") else "warning",
                "categories": post.get("categories", []),
                "raw_action": step_log["raw_action"],
                "reason": post.get("reason", ""),
                "requires_manual_review": True,
            }
        )
    return rows


def summarize_episode(
    run_id: str,
    task_id: int,
    instruction: str,
    step_logs: list[dict[str, Any]],
    final_reward: float,
    done: bool,
    max_steps: int,
) -> dict[str, Any]:
    pre_warnings = [step for step in step_logs if step["pre_report"].get("pre_warning")]
    pre_errors = [step for step in step_logs if step["pre_report"].get("pre_error")]
    post_warnings = [step for step in step_logs if step["post_report"].get("post_warning")]
    post_errors = [step for step in step_logs if step["post_report"].get("post_error")]
    return {
        "run_id": run_id,
        "task_id": task_id,
        "task_instruction": instruction,
        "success": bool(done and final_reward > 0),
        "done": done,
        "final_reward": final_reward,
        "num_steps": len(step_logs),
        "max_steps": max_steps,
        "pre_warning_steps": len(pre_warnings),
        "pre_error_steps": len(pre_errors),
        "post_warning_steps": len(post_warnings),
        "post_error_steps": len(post_errors),
        "first_pre_warning_step": first_step(pre_warnings),
        "first_pre_error_step": first_step(pre_errors),
        "first_post_warning_step": first_step(post_warnings),
        "first_post_error_step": first_step(post_errors),
        "action_changed_steps": 0,
        "agent_prompt_contains_state_summary": any(
            bool(step.get("agent_prompt_contains_state_summary")) for step in step_logs
        ),
    }


def first_step(steps: list[dict[str, Any]]) -> int | None:
    return steps[0]["step_id"] if steps else None


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


if __name__ == "__main__":
    main()
