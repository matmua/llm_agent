#!/usr/bin/env python3
"""Run a local Qwen3-8B agent on a tau3-bench retail subset.

The script intentionally clears proxy environment variables so project traffic
uses the server network, not an SSH-forwarded local proxy.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TAU2_ROOT = PROJECT_ROOT / "external" / "tau2-bench"
DEFAULT_API_BASE = "http://127.0.0.1:8000/v1"
DEFAULT_MODEL = "openai/qwen3-8b"


def disable_proxy_env() -> None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def add_tau2_to_path(tau2_root: Path) -> None:
    src = tau2_root / "src"
    if not src.exists():
        raise FileNotFoundError(f"tau2 source directory not found: {src}")
    sys.path.insert(0, str(src))


def health_check(api_base: str) -> dict[str, Any]:
    models_url = api_base.rstrip("/") + "/models"
    request = urllib.request.Request(models_url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def build_llm_args(
    api_base: str,
    api_key: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    enable_thinking: bool,
    response_format: bool = False,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "api_base": api_base,
        "api_key": api_key,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking,
            }
        },
    }
    if response_format:
        args["response_format"] = {"type": "json_object"}
    return args


def patch_local_nl_evaluator(model: str, eval_llm_args: dict[str, Any]) -> None:
    import tau2.config as tau_config
    import tau2.evaluator.evaluator_nl_assertions as nl_eval
    from tau2.data_model.message import SystemMessage, UserMessage
    from tau2.data_model.simulation import NLAssertionCheck
    from tau2.utils.llm_utils import generate

    tau_config.DEFAULT_LLM_NL_ASSERTIONS = model
    tau_config.DEFAULT_LLM_NL_ASSERTIONS_ARGS = eval_llm_args
    nl_eval.DEFAULT_LLM_NL_ASSERTIONS = model
    nl_eval.DEFAULT_LLM_NL_ASSERTIONS_ARGS = eval_llm_args

    def local_evaluate_nl_assertions(cls, trajectory, nl_assertions):
        trajectory_str = "\n".join(
            f"{message.role}: {message.content}" for message in trajectory
        )
        system_prompt = (
            "You judge whether a retail support conversation satisfies each "
            "expected outcome. Return only valid JSON with this schema: "
            '{"results":[{"expectedOutcome":"...","reasoning":"...",'
            '"metExpectation":true}]}'
        )
        user_prompt = (
            "conversation:\n"
            f"{trajectory_str}\n\n"
            "expectedOutcomes:\n"
            f"{json.dumps(nl_assertions, ensure_ascii=False)}"
        )
        messages = [
            SystemMessage(role="system", content=system_prompt),
            UserMessage(role="user", content=user_prompt),
        ]
        assistant_message = generate(
            model=model,
            messages=messages,
            call_name="nl_assertions_eval_local",
            **eval_llm_args,
        )
        result_data = extract_json_object(assistant_message.content or "{}")
        checks = []
        for result in result_data.get("results", []):
            checks.append(
                NLAssertionCheck(
                    nl_assertion=str(result.get("expectedOutcome", "")),
                    met=bool(result.get("metExpectation", False)),
                    justification=str(result.get("reasoning", "")),
                )
            )
        return checks

    nl_eval.NLAssertionsEvaluator.evaluate_nl_assertions = classmethod(
        local_evaluate_nl_assertions
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tau2-root", type=Path, default=DEFAULT_TAU2_ROOT)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--task-ids", nargs="+", default=["0", "1", "2", "3", "4"])
    parser.add_argument("--num-trials", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--max-errors", type=int, default=5)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--seed", type=int, default=300)
    parser.add_argument("--agent-temperature", type=float, default=0.3)
    parser.add_argument("--user-temperature", type=float, default=0.7)
    parser.add_argument(
        "--agent-mode",
        choices=["direct", "plan_first"],
        default="direct",
        help="direct uses tau3's default LLMAgent; plan_first plans privately before acting.",
    )
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument("--agent-max-tokens", type=int, default=768)
    parser.add_argument("--user-max-tokens", type=int, default=512)
    parser.add_argument("--eval-max-tokens", type=int, default=512)
    parser.add_argument("--plan-max-tokens", type=int, default=192)
    parser.add_argument("--plan-temperature", type=float, default=0.1)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--eval-response-format", action="store_true")
    parser.add_argument("--llm-log-mode", choices=["all", "latest"], default="all")
    parser.add_argument("--run-name")
    parser.add_argument("--skip-health-check", action="store_true")
    return parser.parse_args()


def main() -> None:
    disable_proxy_env()
    os.environ["OPENAI_API_KEY"] = "EMPTY"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

    args = parse_args()
    add_tau2_to_path(args.tau2_root.resolve())

    if not args.skip_health_check:
        model_info = health_check(args.api_base)
        ids = [item.get("id") for item in model_info.get("data", [])]
        print(f"vLLM models: {ids}")

    from tau2.data_model.simulation import TextRunConfig
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.runner.batch import run_tasks
    from tau2.runner.helpers import get_tasks
    from tau2.utils.llm_utils import set_llm_log_mode

    agent_implementation = "llm_agent"
    if args.agent_mode == "plan_first":
        from plan_first_agent import register_plan_first_agent

        register_plan_first_agent()
        agent_implementation = "plan_first_llm_agent"

    agent_llm_args = build_llm_args(
        api_base=args.api_base,
        api_key=args.api_key,
        temperature=args.agent_temperature,
        top_p=args.top_p,
        max_tokens=args.agent_max_tokens,
        enable_thinking=args.enable_thinking,
    )
    user_llm_args = build_llm_args(
        api_base=args.api_base,
        api_key=args.api_key,
        temperature=args.user_temperature,
        top_p=args.top_p,
        max_tokens=args.user_max_tokens,
        enable_thinking=args.enable_thinking,
    )
    eval_llm_args = build_llm_args(
        api_base=args.api_base,
        api_key=args.api_key,
        temperature=0.0,
        top_p=1.0,
        max_tokens=args.eval_max_tokens,
        enable_thinking=False,
        response_format=args.eval_response_format,
    )
    plan_llm_args = build_llm_args(
        api_base=args.api_base,
        api_key=args.api_key,
        temperature=args.plan_temperature,
        top_p=1.0,
        max_tokens=args.plan_max_tokens,
        enable_thinking=False,
        response_format=False,
    )
    if args.agent_mode == "plan_first":
        agent_llm_args["plan_llm_args"] = plan_llm_args
    patch_local_nl_evaluator(args.model, eval_llm_args)
    set_llm_log_mode(args.llm_log_mode)

    run_name = args.run_name or (
        datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_tau3_retail_qwen3_8b_subset"
    )
    run_dir = PROJECT_ROOT / "trajectories" / run_name
    run_dir.mkdir(parents=True, exist_ok=False)

    tasks = get_tasks(
        task_set_name="retail",
        task_split_name="base",
        task_ids=[str(task_id) for task_id in args.task_ids],
    )
    config = TextRunConfig(
        domain="retail",
        task_set_name="retail",
        task_split_name="base",
        task_ids=[str(task_id) for task_id in args.task_ids],
        agent=agent_implementation,
        llm_agent=args.model,
        llm_args_agent=agent_llm_args,
        user="user_simulator",
        llm_user=args.model,
        llm_args_user=user_llm_args,
        num_trials=args.num_trials,
        max_steps=args.max_steps,
        max_errors=args.max_errors,
        timeout=args.timeout,
        max_concurrency=args.max_concurrency,
        seed=args.seed,
        log_level="INFO",
        verbose_logs=True,
        max_retries=0,
        retry_delay=1.0,
        auto_resume=False,
        auto_review=False,
        hallucination_retries=0,
        enforce_communication_protocol=False,
    )

    metadata = {
        "run_name": run_name,
        "run_dir": str(run_dir),
        "benchmark": "tau3-bench",
        "benchmark_repo": str(args.tau2_root.resolve()),
        "domain": "retail",
        "task_split": "base",
        "task_ids": [task.id for task in tasks],
        "model": args.model,
        "agent_mode": args.agent_mode,
        "agent_implementation": agent_implementation,
        "api_base": args.api_base,
        "proxy_disabled": True,
        "agent_llm_args": agent_llm_args,
        "user_llm_args": user_llm_args,
        "nl_eval_llm_args": eval_llm_args,
        "plan_llm_args": plan_llm_args if args.agent_mode == "plan_first" else None,
    }
    (run_dir / "run_meta.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    results = run_tasks(
        config=config,
        tasks=tasks,
        save_path=run_dir / "results.json",
        save_dir=run_dir,
        evaluation_type=EvaluationType.ALL,
        console_display=True,
        results_format="json",
    )
    rewards = [
        sim.reward_info.reward
        for sim in results.simulations
        if sim.reward_info is not None
    ]
    success = sum(1 for reward in rewards if reward == 1.0)
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "total": len(results.simulations),
                "scored": len(rewards),
                "success": success,
                "accuracy": success / len(rewards) if rewards else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
