# llm_agent

## Current Goal

Current stage: clean WebShop shadow detection refactor. The active pipeline is
about action-adjacent state maintenance plus pre/post detection. It does not
optimize intervention, recovery, rollback, or success rate.

The earlier tau3/tau-bench work is still retained below for reference.

## WebShop Shadow Pipeline

Shadow mode is detection only. The detector logs risk, missing evidence,
hypothetical blocks, hypothetical completion actions, and repair plans, but it
never changes execution. In `shadow` mode the runner asserts:

```text
executed_action == raw_action
```

The agent does not see the entity-state graph by default. `--state_to_agent`
defaults to `false`, and the prompt omits the state-summary section unless that
flag is explicitly enabled for an ablation.

Main modules:

- `agents/react_agent.py`: WebShop ReAct agent.
- `agents/llm_client.py`: OpenAI-compatible client and deterministic mock client.
- `state/base_state.py`: generic entity, attribute, constraint, relation, goal, and action schema.
- `state/state_normalizer.py`: normalizes and merges LLM/domain proposals.
- `state/llm_state_proposer.py`: LLM proposes structured state updates without mutating state.
- `state/domain_adapters/webshop_adapter.py`: WebShop rule extraction and proposal fallback.
- `state/entity_state.py`: compatibility StateManager with legacy WebShop helpers plus generic graph.
- `detectors/pre_action.py`: action format, provenance, missing precondition, premature buy, and optional LLM judge checks.
- `detectors/post_action.py`: explicit conflict, missing evidence, no-effect, transition, unsupported update, and preventable failure checks.
- `policies/shadow_policy.py`: no-op shadow intervention interface.
- `runners/run_webshop_shadow.py`: official/mock WebShop runner.
- `analysis/analyze_shadow_logs.py`: metrics, case extraction, and Markdown report generation.
- `docs/shadow_pipeline.md`: design notes for the clean shadow pipeline.

### WebShop Environment

The official WebShop source is cloned under `external/webshop` and is ignored by
git. The text environment is old and works best in a separate Python 3.8 env.
The current server has a working `webshop` conda env prepared for the text
runner.

Recreate the text-env dependencies:

```bash
./no_proxy_run.sh bash -lc '
  conda create -y -n webshop python=3.8.13
  TMPDIR=/root/autodl-tmp/pip_tmp \
  PIP_CACHE_DIR=/root/autodl-tmp/pip_cache \
  /root/miniconda3/envs/webshop/bin/python -m pip install \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r requirements-webshop-textenv.txt
  source /etc/network_turbo 2>/dev/null || true
  PATH=/root/miniconda3/envs/webshop/bin:$PATH \
    /root/miniconda3/envs/webshop/bin/python -m spacy download en_core_web_sm
  conda install -y -n webshop -c conda-forge openjdk=11 faiss-cpu
'
```

Small WebShop data was downloaded from a Hugging Face mirror because Google
Drive `gdown` stalled from the server:

```bash
./no_proxy_run.sh bash -lc '
  source /etc/network_turbo 2>/dev/null || true
  mkdir -p external/webshop/data
  cd external/webshop/data
  curl -L --fail -o items_shuffle_1000.json \
    https://huggingface.co/datasets/HongbangYuan/webshop/resolve/main/items_shuffle_1000.json
  curl -L --fail -o items_ins_v2_1000.json \
    https://huggingface.co/datasets/HongbangYuan/webshop/resolve/main/items_ins_v2_1000.json
  curl -L --fail -o items_human_ins.json \
    https://huggingface.co/datasets/HongbangYuan/webshop/resolve/main/items_human_ins.json
'
```

Build the search index:

```bash
./no_proxy_run.sh bash -lc '
  cd external/webshop/search_engine
  mkdir -p resources resources_100 resources_1k resources_100k indexes
  export PATH=/root/miniconda3/envs/webshop/bin:$PATH
  export JAVA_HOME=/root/miniconda3/envs/webshop
  export JVM_PATH=/root/miniconda3/envs/webshop/lib/jvm/lib/server/libjvm.so
  export PYTHONPATH=..
  /root/miniconda3/envs/webshop/bin/python convert_product_file_format.py
  bash run_indexing.sh
'
```

### Run Clean Shadow

Mock smoke run, no official dependencies:

```bash
./no_proxy_run.sh python -m runners.run_webshop_shadow \
  --env mock \
  --num_tasks 3 \
  --start_index 0 \
  --max_steps 6 \
  --model mock \
  --mode shadow \
  --state_builder llm_hybrid \
  --use_llm_state true \
  --state_to_agent false \
  --log_dir logs/webshop_shadow_clean_demo
```

Official WebShop shadow run:

```bash
./no_proxy_run.sh bash -lc '
  export PATH=/root/miniconda3/envs/webshop/bin:$PATH
  export JAVA_HOME=/root/miniconda3/envs/webshop
  export JVM_PATH=/root/miniconda3/envs/webshop/lib/jvm/lib/server/libjvm.so
  /root/miniconda3/envs/webshop/bin/python -m runners.run_webshop_shadow \
    --env official \
    --num_tasks 20 \
    --start_index 0 \
    --max_steps 15 \
    --model mock \
    --mode shadow \
    --state_builder llm_hybrid \
    --use_llm_state true \
    --state_to_agent false \
    --log_dir logs/webshop_shadow_clean
'
```

Use a real OpenAI-compatible model by setting `LLM_MODEL`, `LLM_BASE_URL`, and
`LLM_API_KEY`, then pass `--model "$LLM_MODEL"`.

Generate a shadow report:

```bash
./no_proxy_run.sh python -m analysis.analyze_shadow_logs \
  --log_dir logs/webshop_shadow_clean_demo \
  --report_dir reports/demo_shadow
```

### Current WebShop Notes

The current Qwen3-8B shadow analysis is tracked in
`reports/webshop_qwen_shadow_analysis/summary_zh.md`. It compares the earlier
3-step mock baseline with the Qwen3-8B run, reports reward distribution, and
breaks down pre/post detector TP/FP/FN/TN counts. The runner default remains
`--max_steps 15`.

Current WebShop reports:

- `reports/demo_shadow/webshop_shadow_summary.md`
- `reports/demo_shadow/webshop_shadow_metrics.json`
- `reports/demo_shadow/webshop_shadow_cases.jsonl`

The demo report is intentionally small and committed as a smoke artifact. Large
runtime logs and experiment reports are ignored by default.

All runtime commands should be launched through `./no_proxy_run.sh` so project
traffic uses the server network instead of inherited local proxy variables.

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
