"""Run WebShop shadow-mode agent episodes."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from agents.llm_client import MockLLMClient, OpenAIChatClient
from agents.react_agent import WebShopReactAgent
from detectors.post_action import PostActionDeltaVerifier
from detectors.pre_action import PreActionDetector
from policies.shadow_policy import ShadowInterventionPolicy
from runners.webshop_env import make_webshop_env
from state.entity_state import StateManager


def main() -> None:
    args = parse_args()
    run_webshop_shadow(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_tasks", type=int, default=20)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--max_steps", type=int, default=15)
    parser.add_argument("--model", default=os.getenv("LLM_MODEL") or os.getenv("QWEN_MODEL") or "mock")
    parser.add_argument("--log_dir", default="logs/webshop_shadow")
    parser.add_argument("--shadow", default="true")
    parser.add_argument("--env", choices=["auto", "official", "mock"], default="auto")
    parser.add_argument("--webshop_repo", default="external/webshop")
    parser.add_argument("--num_products", type=int, default=1000)
    parser.add_argument("--use_llm_judge", action="store_true")
    return parser.parse_args()


def run_webshop_shadow(args: argparse.Namespace) -> dict[str, Any]:
    if str(args.shadow).lower() != "true":
        raise ValueError("Only shadow=true is supported in Phase 1.")

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d_%H%M%S_webshop_shadow")
    env = make_webshop_env(args.env, repo_path=args.webshop_repo, num_products=args.num_products)
    client = build_client(args.model)
    agent = WebShopReactAgent(client)
    pre_detector = PreActionDetector(
        llm_judge=client if args.use_llm_judge else None,
        use_llm_judge=bool(args.use_llm_judge),
    )
    post_verifier = PostActionDeltaVerifier()
    policy = ShadowInterventionPolicy()

    config = {
        "run_id": run_id,
        "env": env.env_name,
        "requested_env": args.env,
        "model": getattr(client, "model", args.model),
        "num_tasks": args.num_tasks,
        "start_index": args.start_index,
        "max_steps": args.max_steps,
        "shadow": True,
        "use_llm_judge": bool(args.use_llm_judge),
    }
    (log_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=True) + "\n")

    summaries: list[dict[str, Any]] = []
    with (log_dir / "steps.jsonl").open("w", encoding="utf-8") as step_fh, (
        log_dir / "episodes.jsonl"
    ).open("w", encoding="utf-8") as episode_fh:
        for offset in range(args.num_tasks):
            task_id = args.start_index + offset
            summary = _run_episode(
                run_id=run_id,
                task_id=task_id,
                env=env,
                agent=agent,
                pre_detector=pre_detector,
                post_verifier=post_verifier,
                policy=policy,
                max_steps=args.max_steps,
                step_fh=step_fh,
            )
            summaries.append(summary)
            episode_fh.write(json.dumps(summary, ensure_ascii=True) + "\n")
            episode_fh.flush()
    return {"config": config, "episodes": summaries}


def build_client(model: str):
    if not model or model == "mock":
        return MockLLMClient()
    return OpenAIChatClient.from_env(model=model)


def _run_episode(
    run_id: str,
    task_id: int,
    env: Any,
    agent: WebShopReactAgent,
    pre_detector: PreActionDetector,
    post_verifier: PostActionDeltaVerifier,
    policy: ShadowInterventionPolicy,
    max_steps: int,
    step_fh: Any,
) -> dict[str, Any]:
    observation = env.reset(task_id)
    instruction = env.get_instruction_text()
    available = env.get_available_actions()
    state_manager = StateManager()
    state_manager.reset(instruction, observation, available, step_id=0)
    history: list[dict[str, Any]] = []
    step_logs: list[dict[str, Any]] = []
    final_reward = 0.0
    done = False

    for step_id in range(max_steps):
        available = env.get_available_actions()
        state_manager.update_observation(observation, available, step_id)
        raw_action = agent.act(
            task_instruction=instruction,
            observation=observation,
            action_history=history,
            available_actions=available,
            state_summary=state_manager.summary(),
        )
        state_manager.update_action(raw_action, step_id)
        state_before = state_manager.snapshot()
        pre_report = pre_detector.detect(
            task_instruction=instruction,
            observation=observation,
            raw_action=raw_action,
            available_actions=available,
            state_manager=state_manager,
            action_history=history,
        )
        decision = policy.decide_before_action(pre_report, raw_action)
        if decision.executed_action != raw_action:
            raise AssertionError("Shadow mode violated: executed_action changed raw_action.")

        next_observation, reward, done, info = env.step(decision.executed_action)
        final_reward = reward
        next_available = env.get_available_actions()
        state_manager.update_observation(next_observation, next_available, step_id + 1)
        state_after = state_manager.snapshot()
        post_report = post_verifier.verify(
            task_instruction=instruction,
            observation_before=observation,
            observation_after=next_observation,
            raw_action=raw_action,
            pre_action_report=pre_report.to_dict(),
            state_before=state_before,
            state_after=state_after,
            reward=reward,
            done=done,
            info=info,
        )
        repair_decision = policy.repair_after_action(post_report)
        step_log = {
            "run_id": run_id,
            "task_id": task_id,
            "step_id": step_id,
            "task_instruction": instruction,
            "observation_before": observation,
            "raw_action": raw_action,
            "executed_action": decision.executed_action,
            "action_history": history,
            "state_before": state_before,
            "pre_action_report": pre_report.to_dict(),
            "intervention_decision": decision.to_dict(),
            "observation_after": next_observation,
            "reward": reward,
            "done": done,
            "info": info,
            "state_after": state_after,
            "post_action_report": post_report.to_dict(),
            "repair_decision": repair_decision.to_dict(),
        }
        step_fh.write(json.dumps(step_log, ensure_ascii=True) + "\n")
        step_fh.flush()
        step_logs.append(step_log)
        history.append(
            {
                "step_id": step_id,
                "action": raw_action,
                "executed_action": decision.executed_action,
                "reward": reward,
                "done": done,
                "pre_risk_level": pre_report.risk_level,
                "post_error": post_report.post_error,
            }
        )
        observation = next_observation
        if done:
            break

    return _episode_summary(task_id, instruction, final_reward, done, step_logs)


def _episode_summary(
    task_id: int,
    instruction: str,
    final_reward: float,
    done: bool,
    step_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    pre_high = [
        step
        for step in step_logs
        if step["pre_action_report"].get("risk_level") == "high"
    ]
    post_errors = [
        step
        for step in step_logs
        if step["post_action_report"].get("post_error")
    ]
    risk_counts: dict[str, int] = {}
    post_counts: dict[str, int] = {}
    for step in step_logs:
        for category in step["pre_action_report"].get("risk_categories", []):
            risk_counts[category] = risk_counts.get(category, 0) + 1
        for category in step["post_action_report"].get("error_categories", []):
            post_counts[category] = post_counts.get(category, 0) + 1
    return {
        "task_id": task_id,
        "task_instruction": instruction,
        "final_success": bool(done and final_reward > 0),
        "final_reward": final_reward,
        "num_steps": len(step_logs),
        "first_high_risk_step": pre_high[0]["step_id"] if pre_high else None,
        "first_post_error_step": post_errors[0]["step_id"] if post_errors else None,
        "num_pre_high_risk": len(pre_high),
        "num_post_errors": len(post_errors),
        "risk_categories_count": risk_counts,
        "post_error_categories_count": post_counts,
        "had_premature_buy": any("premature_buy" in step["pre_action_report"].get("risk_categories", []) for step in step_logs),
        "had_missing_attribute_before_buy": any(
            step["raw_action"].lower() == "click[buy now]"
            and bool(step["pre_action_report"].get("missing_attributes"))
            for step in step_logs
        ),
        "had_potential_preventable_failure": any(
            "potential_preventable_failure" in step["post_action_report"].get("error_categories", [])
            for step in step_logs
        ),
    }


if __name__ == "__main__":
    main()

