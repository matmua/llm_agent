# llm_agent

Minimal WebShop shadow-detection project for a Qwen3-8B ReAct agent.

The current repository is intentionally narrow:

- WebShop text environment only.
- Action-centric state only.
- Pre-action and post-action shadow detection only.
- No intervention, repair, rollback, recovery, tau-bench, tau3-bench, or predictor-soft mode.
- `state_to_agent=false`: detector state is not shown to the agent in the official run.

## Layout

- `agents/llm_client.py`: OpenAI-compatible client plus deterministic mock client.
- `agents/react_agent.py`: WebShop ReAct action generator.
- `detectors/action_parser.py`: `search[...]` / `click[...]` parser.
- `detectors/pre_action.py`: pre-action warning/error detector.
- `detectors/post_action.py`: post-action delta detector.
- `state/action_state.py`: Action-Centric State schema and fallback extraction.
- `state/llm_state_proposer.py`: optional LLM proposal with fallback state.
- `runners/webshop_env.py`: official/mock WebShop environment adapter.
- `runners/run_webshop_shadow.py`: shadow-only runner.
- `analysis/analyze_shadow_logs.py`: metrics and Chinese report generation.
- `tests/`: unit and smoke tests.

`external/` and `models/` are ignored by git. They are kept locally because the
official WebShop code/data and Qwen weights are runtime dependencies.

## Network Rule

Run project commands through `./no_proxy_run.sh` so project traffic uses the
server network and does not inherit local SSH proxy variables:

```bash
./no_proxy_run.sh <command>
```

## Model Endpoint

The runner expects an OpenAI-compatible chat endpoint. The local Qwen3-8B vLLM
endpoint uses these variables:

```bash
export LLM_API_KEY=EMPTY
export LLM_BASE_URL=http://127.0.0.1:8000/v1
export LLM_MODEL=qwen3-8b
```

`OpenAIChatClient` disables urllib proxy handling internally as an extra guard.

## Run

Mock smoke run:

```bash
./no_proxy_run.sh python -m runners.run_webshop_shadow \
  --env mock \
  --num_tasks 3 \
  --start_index 0 \
  --max_steps 6 \
  --model mock \
  --state_to_agent false \
  --log_dir logs/mock_shadow_demo
```

Official WebShop 20-task run:

```bash
./no_proxy_run.sh bash -lc '
  export PATH=/root/miniconda3/envs/webshop/bin:$PATH
  export JAVA_HOME=/root/miniconda3/envs/webshop
  export JVM_PATH=/root/miniconda3/envs/webshop/lib/jvm/lib/server/libjvm.so
  set -a; [ -f .env ] && source .env; set +a
  /root/miniconda3/envs/webshop/bin/python -m runners.run_webshop_shadow \
    --env official \
    --num_tasks 20 \
    --start_index 0 \
    --max_steps 15 \
    --model "$LLM_MODEL" \
    --state_to_agent false \
    --log_dir logs/webshop_shadow_qwen20_max15
'
```

Generate the report:

```bash
./no_proxy_run.sh python -m analysis.analyze_shadow_logs \
  --log_dir logs/webshop_shadow_qwen20_max15 \
  --report_dir reports/webshop_shadow_qwen20_max15
```

## Artifacts

The committed experiment artifacts are:

- `logs/webshop_shadow_qwen20_max15/config.json`
- `logs/webshop_shadow_qwen20_max15/steps.jsonl`
- `logs/webshop_shadow_qwen20_max15/episodes.jsonl`
- `logs/webshop_shadow_qwen20_max15/alert_review.jsonl`
- `reports/webshop_shadow_qwen20_max15/metrics.json`
- `reports/webshop_shadow_qwen20_max15/summary_zh.md`
- `reports/webshop_shadow_qwen20_max15/case_analysis.jsonl`

## Tests

```bash
pytest
```
