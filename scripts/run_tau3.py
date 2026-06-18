#!/usr/bin/env python3
"""Unified tau3/tau2 runner with optional zero-training outcome predictor."""

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
RUNS_ROOT = PROJECT_ROOT / "runs"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def disable_proxy_env() -> None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "FTP_PROXY",
        "SOCKS_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "ftp_proxy",
        "socks_proxy",
        "GIT_PROXY_COMMAND",
        "git_proxy_command",
        "CURL_PROXY",
        "curl_proxy",
        "PIP_PROXY",
        "pip_proxy",
        "npm_config_proxy",
        "npm_config_https_proxy",
        "npm_config_http_proxy",
    ):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def add_tau2_to_path(tau2_root: Path) -> None:
    src = tau2_root / "src"
    if not src.exists():
        raise FileNotFoundError(f"tau2 source directory not found: {src}")
    sys.path.insert(0, str(src))


def normalize_litellm_model(model: str, base_url: str | None) -> str:
    if "/" in model:
        return model
    if base_url:
        return "openai/" + model
    return model


def parse_task_ids(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_value(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value


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
    temperature: float,
    top_p: float,
    max_tokens: int,
    enable_thinking: bool,
    response_format: bool = False,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "api_base": api_base,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }
    if extra_body is None:
        extra_body = {
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking,
            }
        }
    if extra_body:
        args["extra_body"] = extra_body
    if response_format:
        args["response_format"] = {"type": "json_object"}
    return args


def provider_extra_body(model: str, base_url: str, enable_thinking: bool) -> dict[str, Any]:
    model_lower = model.lower()
    base_lower = base_url.lower()
    if "deepseek" in model_lower or "deepseek" in base_lower:
        return {
            "thinking": {
                "type": "enabled" if enable_thinking else "disabled",
            }
        }
    return {
        "chat_template_kwargs": {
            "enable_thinking": enable_thinking,
        }
    }


def patch_nl_evaluator(model: str, eval_llm_args: dict[str, Any]) -> None:
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
            "You judge whether a customer-service conversation satisfies each "
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
        try:
            assistant_message = generate(
                model=model,
                messages=messages,
                call_name="nl_assertions_eval",
                **eval_llm_args,
            )
            result_data = extract_json_object(assistant_message.content or "{}")
            results = result_data.get("results", [])
        except Exception as exc:
            results = [
                {
                    "expectedOutcome": assertion,
                    "reasoning": f"Evaluator failed: {exc}",
                    "metExpectation": False,
                }
                for assertion in nl_assertions
            ]
        checks = []
        for index, assertion in enumerate(nl_assertions):
            result = results[index] if index < len(results) else {}
            checks.append(
                NLAssertionCheck(
                    nl_assertion=str(result.get("expectedOutcome") or assertion),
                    met=bool(result.get("metExpectation", False)),
                    justification=str(result.get("reasoning", "")),
                )
            )
        return checks

    nl_eval.NLAssertionsEvaluator.evaluate_nl_assertions = classmethod(
        local_evaluate_nl_assertions
    )


def health_check(api_base: str) -> dict[str, Any]:
    models_url = api_base.rstrip("/") + "/models"
    request = urllib.request.Request(models_url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tau2-root", type=Path, default=DEFAULT_TAU2_ROOT)
    parser.add_argument("--domain", default=os.environ.get("TAU_BENCH_DOMAIN", "retail"))
    parser.add_argument("--task-ids", default=os.environ.get("TAU_BENCH_TASK_IDS", "0,1,2,3,4"))
    parser.add_argument("--task-split", default="base")
    parser.add_argument("--agent-model", default=os.environ.get("QWEN_MODEL", "qwen3-8b"))
    parser.add_argument("--agent-base-url", default=os.environ.get("QWEN_BASE_URL", "http://127.0.0.1:8000/v1"))
    parser.add_argument("--agent-api-key", default=os.environ.get("QWEN_API_KEY", "EMPTY"))
    parser.add_argument("--user-model", required=True)
    parser.add_argument("--user-base-url", required=True)
    parser.add_argument("--user-api-key-env", required=True)
    parser.add_argument("--evaluator-model", required=True)
    parser.add_argument("--evaluator-base-url", required=True)
    parser.add_argument("--evaluator-api-key-env", required=True)
    parser.add_argument("--predictor-model")
    parser.add_argument("--predictor-base-url")
    parser.add_argument("--predictor-api-key-env")
    parser.add_argument("--controller-version", default="v2")
    parser.add_argument(
        "--soft-risk-level",
        choices=["low", "medium", "high", "critical"],
        default="high",
    )
    parser.add_argument("--soft-confidence-threshold", type=float, default=0.6)
    parser.add_argument(
        "--soft-intervention-confidence-threshold",
        type=float,
        default=0.6,
    )
    parser.add_argument(
        "--mode",
        choices=["direct", "predictor_shadow", "predictor_soft"],
        default="direct",
    )
    parser.add_argument("--run-name")
    parser.add_argument("--num-trials", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--max-errors", type=int, default=5)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--seed", type=int, default=300)
    parser.add_argument("--agent-temperature", type=float, default=0.3)
    parser.add_argument("--user-temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument("--agent-max-tokens", type=int, default=768)
    parser.add_argument("--user-max-tokens", type=int, default=4096)
    parser.add_argument("--eval-max-tokens", type=int, default=4096)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--eval-response-format", action="store_true")
    parser.add_argument("--llm-log-mode", choices=["all", "latest"], default="all")
    parser.add_argument("--skip-health-check", action="store_true")
    return parser.parse_args()


def summarize_task_rows(
    *,
    run_name: str,
    domain: str,
    task_id: str,
    mode: str,
    controller_version: str,
    soft_risk_level: str,
    soft_confidence_threshold: float,
    soft_intervention_confidence_threshold: float,
    rows: list[dict[str, Any]],
    final_success: bool,
) -> dict[str, Any]:
    high_risk_steps = []
    critical_risk_steps = []
    predictor_called = 0
    revise_once_count = 0
    changed_by_controller_count = 0
    constraint_guided_revise_count = 0
    second_check_count = 0
    risk_reduced_after_revision_count = 0
    fallback_used_count = 0
    invalid_revised_action_count = 0
    executed_original_count = 0
    executed_revised_count = 0
    executed_fallback_count = 0
    for row in rows:
        prediction = row.get("prediction") or {}
        decision = row.get("controller_decision") or {}
        if prediction:
            predictor_called += 1
            if prediction.get("risk_level") == "high":
                high_risk_steps.append(row.get("step"))
            if prediction.get("risk_level") == "critical":
                critical_risk_steps.append(row.get("step"))
        if decision.get("decision") == "revise_once":
            revise_once_count += 1
            constraint_guided_revise_count += 1
        if row.get("changed_by_controller"):
            changed_by_controller_count += 1
        if row.get("revised_prediction"):
            second_check_count += 1
        if row.get("risk_reduced_after_revision"):
            risk_reduced_after_revision_count += 1
        if row.get("fallback_used"):
            fallback_used_count += 1
        if row.get("revised_action_valid") is False:
            invalid_revised_action_count += 1
        source = row.get("executed_action_source")
        if source == "original":
            executed_original_count += 1
        elif source == "revised":
            executed_revised_count += 1
        elif source == "fallback":
            executed_fallback_count += 1
    return {
        "run_name": run_name,
        "domain": domain,
        "task_id": task_id,
        "mode": mode,
        "controller_version": controller_version,
        "soft_risk_level": soft_risk_level,
        "soft_confidence_threshold": soft_confidence_threshold,
        "soft_intervention_confidence_threshold": (
            soft_intervention_confidence_threshold
        ),
        "final_success": final_success,
        "num_steps": len(rows),
        "predictor_called": predictor_called,
        "high_risk_count": len(high_risk_steps),
        "critical_risk_count": len(critical_risk_steps),
        "had_high_risk_warning": bool(high_risk_steps),
        "had_critical_risk_warning": bool(critical_risk_steps),
        "first_high_risk_step": high_risk_steps[0] if high_risk_steps else None,
        "first_critical_risk_step": critical_risk_steps[0]
        if critical_risk_steps
        else None,
        "revise_once_count": revise_once_count,
        "changed_by_controller_count": changed_by_controller_count,
        "constraint_guided_revise_count": constraint_guided_revise_count,
        "second_check_count": second_check_count,
        "risk_reduced_after_revision_count": risk_reduced_after_revision_count,
        "fallback_used_count": fallback_used_count,
        "invalid_revised_action_count": invalid_revised_action_count,
        "executed_original_count": executed_original_count,
        "executed_revised_count": executed_revised_count,
        "executed_fallback_count": executed_fallback_count,
    }


def collect_guard_stats(
    run_dir: Path,
    *,
    run_name: str,
    domain: str,
    task_ids: list[str],
    mode: str,
    controller_version: str,
    soft_risk_level: str,
    soft_confidence_threshold: float,
    soft_intervention_confidence_threshold: float,
    final_success_by_task: dict[str, bool],
) -> dict[str, Any]:
    stats = {
        "predictor_called": 0,
        "high_risk_count": 0,
        "critical_risk_count": 0,
        "revise_once_count": 0,
        "changed_by_controller_count": 0,
        "constraint_guided_revise_count": 0,
        "second_check_count": 0,
        "risk_reduced_after_revision_count": 0,
        "fallback_used_count": 0,
        "invalid_revised_action_count": 0,
        "executed_original_count": 0,
        "executed_revised_count": 0,
        "executed_fallback_count": 0,
        "had_warning_failed_tasks": 0,
        "had_warning_success_tasks": 0,
    }
    per_task_steps: dict[str, int] = {}
    rows_by_task: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in task_ids}
    for path in sorted(run_dir.glob("task_*.jsonl")):
        task_id = path.stem.removeprefix("task_")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows_by_task.setdefault(task_id, []).append(json.loads(line))

    task_summaries = []
    for task_id in task_ids:
        rows = rows_by_task.get(task_id, [])
        task_summary = summarize_task_rows(
            run_name=run_name,
            domain=domain,
            task_id=task_id,
            mode=mode,
            controller_version=controller_version,
            soft_risk_level=soft_risk_level,
            soft_confidence_threshold=soft_confidence_threshold,
            soft_intervention_confidence_threshold=(
                soft_intervention_confidence_threshold
            ),
            rows=rows,
            final_success=final_success_by_task.get(task_id, False),
        )
        (run_dir / f"task_{task_id}_summary.json").write_text(
            json.dumps(task_summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        task_summaries.append(task_summary)
        per_task_steps[task_id] = task_summary["num_steps"]
        stats["predictor_called"] += task_summary["predictor_called"]
        stats["high_risk_count"] += task_summary["high_risk_count"]
        stats["critical_risk_count"] += task_summary["critical_risk_count"]
        stats["revise_once_count"] += task_summary["revise_once_count"]
        stats["changed_by_controller_count"] += task_summary["changed_by_controller_count"]
        for key in [
            "constraint_guided_revise_count",
            "second_check_count",
            "risk_reduced_after_revision_count",
            "fallback_used_count",
            "invalid_revised_action_count",
            "executed_original_count",
            "executed_revised_count",
            "executed_fallback_count",
        ]:
            stats[key] += task_summary[key]
        had_warning = (
            task_summary["had_high_risk_warning"]
            or task_summary["had_critical_risk_warning"]
        )
        if had_warning and task_summary["final_success"]:
            stats["had_warning_success_tasks"] += 1
        if had_warning and not task_summary["final_success"]:
            stats["had_warning_failed_tasks"] += 1
    stats["avg_steps"] = (
        sum(per_task_steps.values()) / len(per_task_steps) if per_task_steps else 0.0
    )
    stats["per_task_steps"] = per_task_steps
    stats["task_summaries"] = task_summaries
    return stats


def redacted_config(args: argparse.Namespace, task_ids: list[str]) -> dict[str, Any]:
    return {
        "run_name": args.run_name,
        "domain": args.domain,
        "task_split": args.task_split,
        "task_ids": task_ids,
        "mode": args.mode,
        "controller_version": args.controller_version,
        "soft_risk_level": args.soft_risk_level,
        "soft_confidence_threshold": args.soft_confidence_threshold,
        "soft_intervention_confidence_threshold": (
            args.soft_intervention_confidence_threshold
        ),
        "agent_model": args.agent_model,
        "agent_base_url": args.agent_base_url,
        "agent_api_key": "<redacted>",
        "user_model": args.user_model,
        "user_base_url": args.user_base_url,
        "user_api_key_env": args.user_api_key_env,
        "evaluator_model": args.evaluator_model,
        "evaluator_base_url": args.evaluator_base_url,
        "evaluator_api_key_env": args.evaluator_api_key_env,
        "predictor_model": args.predictor_model,
        "predictor_base_url": args.predictor_base_url,
        "predictor_api_key_env": args.predictor_api_key_env,
        "user_max_tokens": args.user_max_tokens,
        "eval_max_tokens": args.eval_max_tokens,
        "enable_thinking": args.enable_thinking,
    }


def main() -> None:
    disable_proxy_env()
    load_dotenv()
    args = parse_args()
    add_tau2_to_path(args.tau2_root.resolve())

    user_key = env_value(args.user_api_key_env)
    evaluator_key = env_value(args.evaluator_api_key_env)
    os.environ["OPENAI_API_KEY"] = user_key or evaluator_key or args.agent_api_key
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

    agent_model = normalize_litellm_model(args.agent_model, args.agent_base_url)
    user_model = normalize_litellm_model(args.user_model, args.user_base_url)
    evaluator_model = normalize_litellm_model(args.evaluator_model, args.evaluator_base_url)
    predictor_model = args.predictor_model or args.agent_model
    predictor_base_url = args.predictor_base_url or args.agent_base_url
    predictor_api_key_env = args.predictor_api_key_env or "QWEN_API_KEY"

    from llm_agent_guard.guarded_agent import register_guarded_agent
    from tau2.data_model.simulation import TextRunConfig
    from tau2.evaluator.evaluator import EvaluationType
    from tau2.runner.batch import run_tasks
    from tau2.runner.helpers import get_options, get_tasks, load_task_splits
    from tau2.utils.llm_utils import set_llm_log_mode

    set_llm_log_mode(args.llm_log_mode)
    register_guarded_agent()

    task_ids = parse_task_ids(args.task_ids)
    task_splits = load_task_splits(args.domain)
    task_split_name = args.task_split
    if task_splits is None or task_split_name not in task_splits:
        task_split_name = None

    try:
        tasks = get_tasks(
            task_set_name=args.domain,
            task_split_name=task_split_name,
            task_ids=task_ids,
        )
    except Exception:
        options = get_options()
        print(f"Available domains: {options.domains}")
        print(f"Available task sets: {options.task_sets}")
        all_tasks = get_tasks(task_set_name=args.domain, task_split_name=task_split_name)
        print(f"Available task count for {args.domain}: {len(all_tasks)}")
        print(f"First task ids: {[task.id for task in all_tasks[:20]]}")
        raise

    if not args.skip_health_check and "127.0.0.1" in args.agent_base_url:
        model_info = health_check(args.agent_base_url)
        ids = [item.get("id") for item in model_info.get("data", [])]
        print(f"agent endpoint models: {ids}")

    run_name = args.run_name or (
        datetime.now().strftime("%Y%m%d_%H%M%S")
        + f"_{args.domain}_{args.mode}"
    )
    args.run_name = run_name
    run_dir = RUNS_ROOT / run_name
    run_dir.mkdir(parents=True, exist_ok=False)

    agent_llm_args = build_llm_args(
        api_base=args.agent_base_url,
        temperature=args.agent_temperature,
        top_p=args.top_p,
        max_tokens=args.agent_max_tokens,
        enable_thinking=args.enable_thinking,
        extra_body=provider_extra_body(
            args.agent_model,
            args.agent_base_url,
            args.enable_thinking,
        ),
    )
    agent_llm_args["guard_config"] = {
        "mode": args.mode,
        "run_name": run_name,
        "domain": args.domain,
        "runs_root": str(RUNS_ROOT),
        "controller_version": args.controller_version,
        "soft_risk_level": args.soft_risk_level,
        "soft_confidence_threshold": args.soft_confidence_threshold,
        "soft_intervention_confidence_threshold": (
            args.soft_intervention_confidence_threshold
        ),
        "predictor": {
            "model": predictor_model,
            "base_url": predictor_base_url,
            "api_key_env": predictor_api_key_env,
        },
    }
    user_llm_args = build_llm_args(
        api_base=args.user_base_url,
        temperature=args.user_temperature,
        top_p=args.top_p,
        max_tokens=args.user_max_tokens,
        enable_thinking=args.enable_thinking,
        extra_body=provider_extra_body(
            args.user_model,
            args.user_base_url,
            args.enable_thinking,
        ),
    )
    eval_llm_args = build_llm_args(
        api_base=args.evaluator_base_url,
        temperature=0.0,
        top_p=1.0,
        max_tokens=args.eval_max_tokens,
        enable_thinking=False,
        response_format=args.eval_response_format,
        extra_body=provider_extra_body(
            args.evaluator_model,
            args.evaluator_base_url,
            False,
        ),
    )
    patch_nl_evaluator(evaluator_model, eval_llm_args)

    config = TextRunConfig(
        domain=args.domain,
        task_set_name=args.domain,
        task_split_name=task_split_name,
        task_ids=[task.id for task in tasks],
        agent="guarded_llm_agent",
        llm_agent=agent_model,
        llm_args_agent=agent_llm_args,
        user="user_simulator",
        llm_user=user_model,
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

    run_meta = redacted_config(args, [task.id for task in tasks])
    run_meta["litellm_models"] = {
        "agent": agent_model,
        "user": user_model,
        "evaluator": evaluator_model,
    }
    (run_dir / "run_meta.json").write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    results = run_tasks(
        config=config,
        tasks=tasks,
        save_path=run_dir / "tau2_results.json",
        save_dir=run_dir / "artifacts",
        evaluation_type=EvaluationType.ALL,
        console_display=True,
        results_format="json",
    )
    rewards = [
        sim.reward_info.reward
        for sim in results.simulations
        if sim.reward_info is not None
    ]
    success_count = sum(1 for reward in rewards if reward == 1.0)
    final_success_by_task = {
        str(sim.task_id): bool(sim.reward_info and sim.reward_info.reward == 1.0)
        for sim in results.simulations
    }
    task_id_list = [task.id for task in tasks]
    guard_stats = collect_guard_stats(
        run_dir,
        run_name=run_name,
        domain=args.domain,
        task_ids=task_id_list,
        mode=args.mode,
        controller_version=args.controller_version,
        soft_risk_level=args.soft_risk_level,
        soft_confidence_threshold=args.soft_confidence_threshold,
        soft_intervention_confidence_threshold=(
            args.soft_intervention_confidence_threshold
        ),
        final_success_by_task=final_success_by_task,
    )
    summary = {
        "run_name": run_name,
        "domain": args.domain,
        "task_ids": task_id_list,
        "mode": args.mode,
        "controller_version": args.controller_version,
        "soft_risk_level": args.soft_risk_level,
        "soft_confidence_threshold": args.soft_confidence_threshold,
        "soft_intervention_confidence_threshold": (
            args.soft_intervention_confidence_threshold
        ),
        "agent_model": args.agent_model,
        "user_model": args.user_model,
        "evaluator_model": args.evaluator_model,
        "predictor_model": predictor_model if args.mode != "direct" else None,
        "num_tasks": len(results.simulations),
        "success_count": success_count,
        "success_rate": success_count / len(results.simulations)
        if results.simulations
        else 0.0,
        **guard_stats,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
