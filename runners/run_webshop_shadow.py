"""Run WebShop direct, shadow, or intervention-mode agent episodes."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from agents.llm_client import MockLLMClient, OpenAIChatClient
from agents.react_agent import WebShopReactAgent
from detectors.action_parser import parse_webshop_action
from detectors.post_action import PostActionDeltaVerifier
from detectors.pre_action import PreActionDetector, PreActionReport
from policies.risk_router import RiskAwareActionRouter
from policies.shadow_policy import InterventionDecision, ShadowInterventionPolicy
from repair.checkpoint_manager import CheckpointManager
from repair.minimal_state_repair import MinimalStateRepair
from runners.intervention_logger import InterventionLogger
from runners.webshop_env import make_webshop_env
from state.entity_state import StateManager, expected_delta_for_action


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
    parser.add_argument("--mode", choices=["direct", "shadow", "intervention"], default=None)
    parser.add_argument("--env", choices=["auto", "official", "mock"], default="auto")
    parser.add_argument("--webshop_repo", default="external/webshop")
    parser.add_argument("--num_products", type=int, default=1000)
    parser.add_argument("--use_llm_judge", action="store_true")
    return parser.parse_args()


def run_webshop_shadow(args: argparse.Namespace) -> dict[str, Any]:
    mode = resolve_mode(args)

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime(f"%Y%m%d_%H%M%S_webshop_{mode}")
    env = make_webshop_env(args.env, repo_path=args.webshop_repo, num_products=args.num_products)
    client = build_client(args.model)
    agent = WebShopReactAgent(client)
    pre_detector = PreActionDetector(
        llm_judge=client if args.use_llm_judge else None,
        use_llm_judge=bool(args.use_llm_judge),
    )
    post_verifier = PostActionDeltaVerifier()
    shadow_policy = ShadowInterventionPolicy()
    risk_router = RiskAwareActionRouter()
    repair_engine = MinimalStateRepair()

    config = {
        "run_id": run_id,
        "env": env.env_name,
        "requested_env": args.env,
        "model": getattr(client, "model", args.model),
        "num_tasks": args.num_tasks,
        "start_index": args.start_index,
        "max_steps": args.max_steps,
        "mode": mode,
        "shadow": mode == "shadow",
        "intervention_enabled": mode == "intervention",
        "use_llm_judge": bool(args.use_llm_judge),
    }
    (log_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=True) + "\n")

    summaries: list[dict[str, Any]] = []
    intervention_logger = InterventionLogger(log_dir)
    try:
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
                    shadow_policy=shadow_policy,
                    risk_router=risk_router,
                    repair_engine=repair_engine,
                    mode=mode,
                    max_steps=args.max_steps,
                    step_fh=step_fh,
                    intervention_logger=intervention_logger,
                )
                summaries.append(summary)
                episode_fh.write(json.dumps(summary, ensure_ascii=True) + "\n")
                episode_fh.flush()
    finally:
        intervention_logger.close()
    return {"config": config, "episodes": summaries}


def resolve_mode(args: argparse.Namespace) -> str:
    if getattr(args, "mode", None):
        return str(args.mode)
    shadow = str(getattr(args, "shadow", "true")).lower()
    if shadow in {"true", "1", "yes"}:
        return "shadow"
    if shadow in {"false", "0", "no"}:
        return "intervention"
    raise ValueError(f"Invalid --shadow value: {args.shadow}")


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
    shadow_policy: ShadowInterventionPolicy,
    risk_router: RiskAwareActionRouter,
    repair_engine: MinimalStateRepair,
    mode: str,
    max_steps: int,
    step_fh: Any,
    intervention_logger: InterventionLogger,
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
    pending_repair_action = ""
    pending_repair_metadata: dict[str, Any] = {}
    checkpoint_manager = CheckpointManager()

    for step_id in range(max_steps):
        available = env.get_available_actions()
        state_manager.update_observation(observation, available, step_id)
        checkpoint = checkpoint_manager.create(
            task_id=task_id,
            step_id=step_id,
            observation=observation,
            available_actions=available,
            state_snapshot=state_manager.snapshot(),
            action_history=history,
        )
        action_source = "agent"
        agent_trace: dict[str, Any] = {}
        agent_raw_action = ""
        if mode == "intervention" and pending_repair_action:
            raw_action = pending_repair_action
            action_source = "post_action_repair"
            pending_repair_action = ""
            intervention_logger.log_event(
                run_id,
                task_id,
                step_id,
                "repair_action_executed",
                pending_repair_metadata,
            )
            pending_repair_metadata = {}
        else:
            raw_action = agent.act(
                task_instruction=instruction,
                observation=observation,
                action_history=history,
                available_actions=available,
                state_summary=state_manager.summary(),
            )
            agent_raw_action = raw_action
            agent_trace = dict(agent.last_trace)
        state_manager.update_action(raw_action, step_id)
        state_before = state_manager.snapshot()
        if mode == "direct":
            pre_report = default_pre_action_report(raw_action, "Direct mode: pre-action detector disabled.")
            decision = direct_decision(raw_action)
        else:
            pre_report = pre_detector.detect(
                task_instruction=instruction,
                observation=observation,
                raw_action=raw_action,
                available_actions=available,
                state_manager=state_manager,
                action_history=history,
            )
            if mode == "shadow":
                decision = shadow_policy.decide_before_action(pre_report, raw_action)
            else:
                decision = risk_router.decide_before_action(
                    pre_action_report=pre_report,
                    state_manager=state_manager,
                    raw_action=raw_action,
                    available_actions=available,
                    action_history=history,
                    observation=observation,
                )

        if mode == "shadow" and decision.executed_action != raw_action:
            raise AssertionError("Shadow mode violated: executed_action changed raw_action.")
        if decision.executed_action != raw_action:
            state_manager.update_action(decision.executed_action, step_id)
            intervention_logger.log_event(
                run_id,
                task_id,
                step_id,
                "pre_action_changed",
                decision.to_dict(),
            )

        executed_pre_report = pre_report.to_dict()
        if decision.executed_action != raw_action:
            parsed = parse_webshop_action(decision.executed_action)
            executed_pre_report["raw_expected_delta"] = executed_pre_report.get("expected_delta", {})
            executed_pre_report["expected_delta"] = expected_delta_for_action(
                parsed.action_type, parsed.target.lower()
            )

        next_observation, reward, done, info = env.step(decision.executed_action)
        final_reward = reward
        next_available = env.get_available_actions()
        state_manager.update_observation(next_observation, next_available, step_id + 1)
        state_after = state_manager.snapshot()
        post_report = post_verifier.verify(
            task_instruction=instruction,
            observation_before=observation,
            observation_after=next_observation,
            raw_action=decision.executed_action,
            pre_action_report=executed_pre_report,
            state_before=state_before,
            state_after=state_after,
            reward=reward,
            done=done,
            info=info,
        )
        if mode == "intervention":
            repair_decision = repair_engine.repair_after_action(
                post_action_report=post_report,
                state_manager=state_manager,
                checkpoint_manager=checkpoint_manager,
                checkpoint_id=checkpoint.checkpoint_id,
                available_actions=next_available,
                action_history=history
                + [
                    {
                        "step_id": step_id,
                        "action": raw_action,
                        "executed_action": decision.executed_action,
                        "action_source": action_source,
                    }
                ],
                done=done,
            )
            if repair_decision.repair_action and not done:
                pending_repair_action = repair_decision.repair_action
                pending_repair_metadata = repair_decision.to_dict()
                intervention_logger.log_event(
                    run_id,
                    task_id,
                    step_id,
                    "post_action_repair_queued",
                    repair_decision.to_dict(),
                )
        else:
            repair_decision = shadow_policy.repair_after_action(post_report)
        step_log = {
            "run_id": run_id,
            "mode": mode,
            "task_id": task_id,
            "step_id": step_id,
            "checkpoint_id": checkpoint.checkpoint_id,
            "task_instruction": instruction,
            "observation_before": observation,
            "agent_raw_action": agent_raw_action,
            "raw_action": raw_action,
            "executed_action": decision.executed_action,
            "action_source": action_source,
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
            "token_usage_estimate": {
                "agent_prompt_tokens": int(agent_trace.get("estimated_prompt_tokens", 0)),
                "agent_response_tokens": int(agent_trace.get("estimated_response_tokens", 0)),
                "agent_total_tokens": int(agent_trace.get("estimated_total_tokens", 0)),
                "intervention_tokens": 0,
                "total_tokens": int(agent_trace.get("estimated_total_tokens", 0)),
            },
        }
        step_fh.write(json.dumps(step_log, ensure_ascii=True) + "\n")
        step_fh.flush()
        step_logs.append(step_log)
        history.append(
            {
                "step_id": step_id,
                "action": raw_action,
                "agent_raw_action": agent_raw_action,
                "executed_action": decision.executed_action,
                "action_source": action_source,
                "changed_action": decision.executed_action != raw_action,
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


def default_pre_action_report(action: str, reason: str) -> PreActionReport:
    parsed = parse_webshop_action(action)
    return PreActionReport(
        risk_score=0.0,
        risk_level="low",
        should_block_hypothetical=False,
        risk_categories=[],
        missing_attributes=[],
        unsupported_assumptions=[],
        expected_delta=expected_delta_for_action(parsed.action_type, parsed.target.lower()),
        reason=reason,
    )


def direct_decision(raw_action: str):
    return InterventionDecision(
        allow_execute=True,
        raw_action=raw_action,
        executed_action=raw_action,
        would_block=False,
        would_complete=False,
        would_repair=False,
        reason="Direct mode: raw agent action executed without detector routing.",
        metadata={"mode": "direct", "changed_action": False},
    )


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
    changed_steps = [
        step
        for step in step_logs
        if step.get("intervention_decision", {}).get("metadata", {}).get("changed_action")
    ]
    repair_steps = [
        step
        for step in step_logs
        if step.get("repair_decision", {}).get("repair_executed")
    ]
    repair_action_steps = [
        step for step in step_logs if step.get("action_source") == "post_action_repair"
    ]
    token_total = sum(
        int(step.get("token_usage_estimate", {}).get("total_tokens", 0))
        for step in step_logs
    )
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
        "num_changed_actions": len(changed_steps),
        "num_repair_actions_queued": len(repair_steps),
        "num_repair_actions_executed": len(repair_action_steps),
        "had_intervention": bool(changed_steps or repair_steps or repair_action_steps),
        "estimated_token_cost": token_total,
    }


if __name__ == "__main__":
    main()
