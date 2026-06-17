# Codex Implementation Report

## Files Added

- `.env.example`
- `scripts/run_tau3.py`
- `llm_agent_guard/__init__.py`
- `llm_agent_guard/schemas.py`
- `llm_agent_guard/llm_client.py`
- `llm_agent_guard/outcome_predictor.py`
- `llm_agent_guard/predictive_controller.py`
- `llm_agent_guard/guarded_agent.py`
- `llm_agent_guard/logging_utils.py`
- `reports/*_analysis.md` for completed runs

## Files Modified

- `.gitignore`
- `README.md`
- `no_proxy_run.sh`
- `scripts/analyze_tau3_results.py`

## Files Archived

- `archive/plan_first/plan_first_agent.py`
- `archive/plan_first/tau3_plan_first_comparison.md`
- `archive/plan_first/tau3_retail_plan_first_v1_diagnostic.md`
- `archive/plan_first/tau3_retail_plan_first_v2_summary.md`
- `archive/unused_comparator/outcome_comparator.py`

## Security Check

- Whether any API key was found: no real API key was found in tracked files.
- Whether `.env` is ignored: yes, `.gitignore` contains `.env`, `*.env`, `.env.*`, and `!.env.example`.
- Whether `git grep -n "sk-"` is clean: only false positives from `--task-ids` in README / legacy script names were found.
- Project commands were run through `./no_proxy_run.sh`; `scripts/run_tau3.py` also clears proxy environment variables at startup.

## Implemented Modes

- direct: wraps the tau-bench LLMAgent but does not call predictor or change action behavior.
- predictor_shadow: calls predictor before each agent action, logs structured warnings, never changes the action.
- predictor_soft: calls predictor before each agent action and revises once only if risk is critical, confidence is at least 0.7, and recommendation is one of `revise`, `ask_user`, `recover`, or `stop`.

## Predictor Design

- Inputs: task goal, recent history, current observation, available action schema, constraints, domain metadata, and proposed action.
- Outputs: predicted outcome, task progress, risk level, risk reason, missing information, possible failure mode, recoverability, confidence, and recommendation.
- Why it is dataset-agnostic: prompts and schemas contain no retail / airline / telecom rules, no tool-name heuristics, and no benchmark-specific labels.
- What it does not access: no gold answer, no reference trajectory, no official evaluator internals, no database state beyond ordinary tool observations.

## Smoke Test Result

- Requested mock task id `0` does not exist in the installed tau2/tau3 snapshot. Available mock ids include `create_task_1`, so smoke used `create_task_1`.
- Direct command: `scripts/run_tau3.py --domain mock --task-ids create_task_1 --mode direct --run-name smoke_mock_direct_qwen_v2`
- Direct result: success, `1/1`, `success_rate=1.0`, `avg_steps=2.0`.
- Shadow command: `scripts/run_tau3.py --domain mock --task-ids create_task_1 --mode predictor_shadow --run-name smoke_mock_shadow_qwen_predictor`
- Shadow result: success, `1/1`, `predictor_called=2`, no action changed.
- Soft smoke command: `scripts/run_tau3.py --domain mock --task-ids create_task_1 --mode predictor_soft --run-name smoke_mock_soft_qwen_predictor`
- Soft smoke result: success, `1/1`, `predictor_called=2`, `revise_once_count=0`.

## Retail 0-4 Result

- Local Qwen direct command: `scripts/run_tau3.py --domain retail --task-ids 0,1,2,3,4 --mode direct --run-name retail_0_4_direct_qwen_user_eval`
- Local Qwen direct result: success/failure completed, `1/5`, `success_rate=0.2`, summary path `runs/retail_0_4_direct_qwen_user_eval/summary.json`.
- Local Qwen shadow command: `scripts/run_tau3.py --domain retail --task-ids 0,1,2,3,4 --mode predictor_shadow --run-name retail_0_4_shadow_qwen_predictor_qwen_user_eval`
- Local Qwen shadow result: completed, `1/5`, `success_rate=0.2`, `predictor_called=73`, `high_risk_count=11`, `critical_risk_count=0`, summary path `runs/retail_0_4_shadow_qwen_predictor_qwen_user_eval/summary.json`.
- DeepSeek user/evaluator direct command: `scripts/run_tau3.py --domain retail --task-ids 0,1,2,3,4 --mode direct --run-name retail_0_4_direct_qwen_deepseek_user_eval`
- DeepSeek user/evaluator direct result: completed with simulator instability, `1/5`, `success_rate=0.2`, summary path `runs/retail_0_4_direct_qwen_deepseek_user_eval/summary.json`.
- DeepSeek user/evaluator shadow command: `scripts/run_tau3.py --domain retail --task-ids 0,1,2,3,4 --mode predictor_shadow --run-name retail_0_4_shadow_qwen_predictor_deepseek_user_eval`
- DeepSeek user/evaluator shadow result: completed with simulator/evaluator instability, `0/5`, `success_rate=0.0`, `predictor_called=61`, `high_risk_count=5`, `critical_risk_count=0`, summary path `runs/retail_0_4_shadow_qwen_predictor_deepseek_user_eval/summary.json`.

## Generated Reports

- `reports/smoke_mock_shadow_qwen_predictor_analysis.md`
- `reports/smoke_mock_soft_qwen_predictor_analysis.md`
- `reports/retail_0_4_direct_qwen_user_eval_analysis.md`
- `reports/retail_0_4_shadow_qwen_predictor_qwen_user_eval_analysis.md`
- `reports/retail_0_4_direct_qwen_deepseek_user_eval_analysis.md`
- `reports/retail_0_4_shadow_qwen_predictor_deepseek_user_eval_analysis.md`

## Known Limitations

- No training yet.
- Predictor is prompt-only.
- Shadow mode does not improve success rate by design.
- Soft mode only revises once.
- No comparator implemented.
- No rollback implemented.
- No automatic recovery implemented.
- No dataset-specific heuristics implemented.
- DeepSeek user simulator produced empty-message protocol failures in several tasks, and DeepSeek NL evaluation sometimes returned malformed JSON; therefore DeepSeek `predictor_soft` was not run.
- LiteLLM prints model-cost-map warnings for local `qwen3-8b` and `deepseek-v4-pro`; these warnings do not block execution.

## Verification

- `python -m compileall .`: passed.
- `git grep -n "sk-" || true`: no real key found; only `--task-ids` false positives.
- `predictor_shadow` did not change actions: observed `changed_by_controller_count=0` in smoke and retail shadow runs.
