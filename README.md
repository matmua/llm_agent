# LLM Agent Tau3 Retail Smoke Test

This repository contains a lightweight local agent evaluation setup for:

- Model: Qwen3-8B served through vLLM's OpenAI-compatible API
- Benchmark: tau3-bench (`sierra-research/tau2-bench`)
- Domain: retail
- Subset: retail `base` tasks `0 1 2 3 4`

Large runtime artifacts are intentionally not committed:

- `models/Qwen3-8B`
- `external/tau2-bench`
- `.venv-tau2`
- local caches and raw downloaded data

## Files

- `scripts/run_tau3_retail_subset.py`: local runner that disables proxy env vars, calls local vLLM, and patches tau3 NL assertion evaluation to use local Qwen3-8B.
- `scripts/analyze_tau3_results.py`: summarizes rewards, failure types, tool traces, and failure roots.
- `reports/tau3_retail_subset_summary.md`: human-readable result report.
- `trajectories/20260611_tau3_retail_qwen3_8b_subset5_local_eval/`: full saved run, including `results.json`, `analysis.json`, task logs, and LLM debug JSON.
- `no_proxy_run.sh`: helper for running commands without inherited HTTP proxy variables.

## Result

Retail base subset, 5 tasks:

- Successes: `1/5`
- Accuracy: `20.0%`
- Failure types:
  - `db_state_failed`: 2
  - `nl_assertion_failed`: 1
  - `premature_termination:max_steps`: 1

See `reports/tau3_retail_subset_summary.md` for details.

## Reproduce

Expected local paths:

```bash
/root/autodl-tmp/llm_agent/models/Qwen3-8B
/root/autodl-tmp/llm_agent/external/tau2-bench
/root/autodl-tmp/llm_agent/.venv-tau2
```

Start vLLM in the existing `verl` conda environment:

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

Run the subset:

```bash
./no_proxy_run.sh .venv-tau2/bin/python scripts/run_tau3_retail_subset.py \
  --task-ids 0 1 2 3 4
```

Analyze a run:

```bash
./no_proxy_run.sh .venv-tau2/bin/python scripts/analyze_tau3_results.py \
  trajectories/<run_name>
```

