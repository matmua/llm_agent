# llm_agent

## Current Goal

This repo evaluates Qwen3-8B on tau-bench / tau3-bench and implements a
zero-training, dataset-agnostic outcome predictor for action-level risk warning.

## Roles

- Agent: Qwen3-8B served through a local vLLM OpenAI-compatible endpoint.
- Environment: official tau-bench tools, database, state transition, and scoring logic.
- User simulator: DeepSeek V4 Pro or another OpenAI-compatible model.
- Final evaluator: tau-bench evaluator, optionally using DeepSeek for natural-language evaluation.
- Predictor: Qwen3-8B by default, optionally DeepSeek.

DeepSeek is never the environment. It is only used as user simulator, final
evaluator LLM, or optional predictor LLM.

## Modes

- `direct`: baseline, no predictor.
- `predictor_shadow`: predictor logs structured warnings but does not intervene.
- `predictor_soft`: predictor may request one action revision only when the configured risk/confidence threshold is met. The default threshold preserves the original critical/0.7 behavior.

## What This Repo Does Not Do

- No training.
- No RL / GRPO / PPO / DPO.
- No comparator.
- No rollback.
- No automatic recovery.
- No dataset-specific heuristic rules.
- No gold answer access.
- No reference trajectory access.

## Project Layout

- `scripts/run_tau3.py`: unified runner for direct, shadow, and soft modes.
- `scripts/analyze_tau3_results.py`: analysis for predictor-only guard logs.
- `scripts/compare_runs.py`: side-by-side comparison for multiple tau3 runs.
- `scripts/export_tau3_task_logs.py`: exports ignored `runs/` task logs into commit-friendly reports.
- `llm_agent_guard/`: generic predictor, controller, logging, and agent wrapper.
- `archive/plan_first/`: older plan-first experiment files.
- `archive/unused_comparator/`: comparator code archived because this stage does not use it.
- `reports/`: human-readable reports.
- `runs/`: local run outputs, ignored by git.
- `trajectories/`: earlier baseline trajectories retained for reference.

## Current Retail 0-19 Result

The current complete retail 0-19 experiments use local Qwen for agent, user
simulator, evaluator, and predictor. DeepSeek is not used in these complete
0-19 runs.

| Run | Mode | Success | Success Rate | Revise Once | Changed By Controller |
|---|---|---:|---:|---:|---:|
| `retail_0_19_direct_qwen_user_eval` | direct | 2/20 | 0.1000 | 0 | 0 |
| `retail_0_19_shadow_qwen_predictor_qwen_user_eval` | predictor_shadow | 3/20 | 0.1500 | 0 | 0 |
| `retail_0_19_soft_high06_qwen_predictor_qwen_user_eval` | predictor_soft high/0.6 | 2/20 | 0.1000 | 18 | 14 |

`retail_0_19_soft_high07_qwen_predictor_qwen_user_eval` was interrupted and is
kept only as a partial log, not as a complete accuracy result.

Main reports:

- `reports/soft_intervention_experiment_report.md`
- `reports/retail_0_19_soft_comparison.md`
- `reports/retail_0_19_task_logs/`

## Environment Variables

See `.env.example`.

Do not commit `.env` or real API keys. Runtime commands should be launched
through `./no_proxy_run.sh` so project traffic uses the server network instead
of inherited local proxy variables.

## Start Local Qwen

```bash
./no_proxy_run.sh bash -lc '
  export CUDA_VISIBLE_DEVICES=0
  conda run -n verl python -m vllm.entrypoints.openai.api_server \
    --model /root/autodl-tmp/llm_agent/models/Qwen3-8B \
    --served-model-name qwen3-8b \
    --dtype bfloat16 \
    --host 127.0.0.1 \
    --port 8000 \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.90 \
    --enable-auto-tool-choice \
    --tool-call-parser hermes \
    --reasoning-parser qwen3 \
    --trust-remote-code
'
```

## Example Commands

Load local environment variables without printing secrets:

```bash
set -a
source .env
set +a
```

Direct baseline:

```bash
./no_proxy_run.sh .venv-tau2/bin/python scripts/run_tau3.py \
  --domain retail \
  --task-ids 0,1,2,3,4 \
  --agent-model "$QWEN_MODEL" \
  --agent-base-url "$QWEN_BASE_URL" \
  --agent-api-key "$QWEN_API_KEY" \
  --user-model "$QWEN_MODEL" \
  --user-base-url "$QWEN_BASE_URL" \
  --user-api-key-env QWEN_API_KEY \
  --evaluator-model "$QWEN_MODEL" \
  --evaluator-base-url "$QWEN_BASE_URL" \
  --evaluator-api-key-env QWEN_API_KEY \
  --mode direct \
  --run-name retail_0_4_direct_qwen_user_eval
```

Predictor shadow:

```bash
./no_proxy_run.sh .venv-tau2/bin/python scripts/run_tau3.py \
  --domain retail \
  --task-ids 0,1,2,3,4 \
  --agent-model "$QWEN_MODEL" \
  --agent-base-url "$QWEN_BASE_URL" \
  --agent-api-key "$QWEN_API_KEY" \
  --user-model "$DEEPSEEK_MODEL" \
  --user-base-url "$DEEPSEEK_BASE_URL" \
  --user-api-key-env DEEPSEEK_API_KEY \
  --evaluator-model "$DEEPSEEK_MODEL" \
  --evaluator-base-url "$DEEPSEEK_BASE_URL" \
  --evaluator-api-key-env DEEPSEEK_API_KEY \
  --predictor-model "$QWEN_MODEL" \
  --predictor-base-url "$QWEN_BASE_URL" \
  --predictor-api-key-env QWEN_API_KEY \
  --mode predictor_shadow \
  --run-name retail_0_4_shadow_qwen_predictor_deepseek_user_eval
```

Predictor soft:

```bash
./no_proxy_run.sh .venv-tau2/bin/python scripts/run_tau3.py \
  --domain retail \
  --task-ids 0,1,2,3,4 \
  --agent-model "$QWEN_MODEL" \
  --agent-base-url "$QWEN_BASE_URL" \
  --agent-api-key "$QWEN_API_KEY" \
  --user-model "$DEEPSEEK_MODEL" \
  --user-base-url "$DEEPSEEK_BASE_URL" \
  --user-api-key-env DEEPSEEK_API_KEY \
  --evaluator-model "$DEEPSEEK_MODEL" \
  --evaluator-base-url "$DEEPSEEK_BASE_URL" \
  --evaluator-api-key-env DEEPSEEK_API_KEY \
  --predictor-model "$QWEN_MODEL" \
  --predictor-base-url "$QWEN_BASE_URL" \
  --predictor-api-key-env QWEN_API_KEY \
  --mode predictor_soft \
  --run-name retail_0_4_soft_qwen_predictor_deepseek_user_eval
```

Analyze a run:

```bash
./no_proxy_run.sh .venv-tau2/bin/python scripts/analyze_tau3_results.py \
  runs/<run_name>
```
