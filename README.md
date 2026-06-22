# llm_agent

Minimal rule-based shadow v1 for WebShop agent trajectories.

This version only implements:

- agent loop
- shadow state table
- rule-based pre check
- rule-based post check

It does not implement LLM detectors, LLM state proposal, risk levels, blocking,
intervention, rollback, recovery, action repair, or state injection into the
agent prompt.

## Active Layout

- `runners/run_webshop_shadow.py`: the only active shadow runner.
- `shadow/parser.py`: format-only action parser.
- `shadow/extractor.py`: rule-based attribute extraction.
- `shadow/state.py`: two-table shadow state helpers.
- `shadow/pre.py`: format and repeated no-info pre check.
- `shadow/post.py`: post-action info-gain check.
- `shadow/repair.py`: no-op repair placeholder.
- `runners/webshop_env.py`: official/mock WebShop environment adapter.
- `agents/`: ReAct agent and OpenAI-compatible/mock client.

The active shadow state is only:

```json
{
  "attributes": {},
  "actions": []
}
```

## Network Rule

Run project commands through `./no_proxy_run.sh` so project traffic uses the
server network instead of inherited local proxy variables:

```bash
./no_proxy_run.sh <command>
```

## Run WebShop20

Start a local OpenAI-compatible model endpoint, then run:

```bash
./no_proxy_run.sh bash -lc '
  export PATH=/root/miniconda3/envs/webshop/bin:$PATH
  export JAVA_HOME=/root/miniconda3/envs/webshop
  export JVM_PATH=/root/miniconda3/envs/webshop/lib/jvm/lib/server/libjvm.so
  set -a; [ -f .env ] && source .env; set +a
  /root/miniconda3/envs/webshop/bin/python -m runners.run_webshop_shadow \
    --env official \
    --num_samples 20 \
    --start_index 0 \
    --max_steps 15 \
    --model "$LLM_MODEL" \
    --state_to_agent false \
    --log_dir logs/rule_shadow_v1_webshop20 \
    --report_dir reports/rule_shadow_v1_webshop20
'
```

Mock smoke run:

```bash
./no_proxy_run.sh python -m runners.run_webshop_shadow \
  --env mock \
  --num_samples 2 \
  --max_steps 5 \
  --model mock \
  --state_to_agent false
```

## Outputs

- `logs/rule_shadow_v1_webshop20/trajectories.jsonl`
- `logs/rule_shadow_v1_webshop20/state_snapshots_compact.jsonl`
- `reports/rule_shadow_v1_webshop20/metrics.json`
- `reports/rule_shadow_v1_webshop20/summary_zh.md`
- `reports/rule_shadow_v1_webshop20/pre_post_accuracy_zh.md`
- `reports/rule_shadow_v1_webshop20/manual_progress_audit_zh.md`
- `reports/rule_shadow_v1_webshop20/pre_post_diagnostics.json`
- `reports/rule_shadow_v1_webshop20/pre_post_step_diagnostics.jsonl`

Offline pre/post audit:

```bash
./no_proxy_run.sh python -m runners.analyze_rule_shadow_logs
```

## Tests

```bash
pytest
```
