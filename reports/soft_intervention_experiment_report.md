# Soft Intervention 实验报告

## Goal

本轮目标是把 `predictor_soft` 的干预阈值从默认 `critical + confidence >= 0.7` 放宽为可配置，并在 retail 0-19 上比较 direct、predictor_shadow、predictor_soft high/0.6。

本轮完整实验没有使用 DeepSeek。完整 0-19 三组运行中，agent、user simulator、evaluator、predictor 均使用本地 `qwen3-8b`，服务地址为 `http://127.0.0.1:8000/v1`。

## Code Changes

- `PredictiveController` 新增 `soft_risk_level` 和 `soft_confidence_threshold`，默认仍保持旧行为：`critical` / `0.7`。
- `scripts/run_tau3.py` 新增 `--soft-risk-level` 和 `--soft-confidence-threshold`，并写入 `run_meta.json`、`summary.json`、每个 task summary。
- 每一步 guard 日志新增 soft 阈值字段，并确保 `changed_by_controller=true` 只在 proposed action 和 executed action 实际不同的时候记录。
- `scripts/analyze_tau3_results.py` 新增 `--run-name`，并在报告里输出 soft setting 和 intervention summary。
- `scripts/compare_runs.py` 生成多 run 对比报告。
- `scripts/export_tau3_task_logs.py` 将 ignored `runs/` 里的 step/task 信息导出到可提交的 Markdown 日志。

## Experiment Matrix

| Run | Mode | Soft Risk | Soft Confidence | Status |
|---|---|---|---:|---|
| `retail_0_19_direct_qwen_user_eval` | direct | critical | 0.7 | complete |
| `retail_0_19_shadow_qwen_predictor_qwen_user_eval` | predictor_shadow | critical | 0.7 | complete |
| `retail_0_19_soft_high06_qwen_predictor_qwen_user_eval` | predictor_soft | high | 0.6 | complete |
| `retail_0_19_soft_high07_qwen_predictor_qwen_user_eval` | predictor_soft | high | 0.7 | partial/interrupted |

## Main Results

| Run | Success | Success Rate | Avg Steps | Predictor Called | High Risk | Critical Risk | Revise Once | Changed By Controller |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| direct | 2/20 | 0.1000 | 13.05 | 0 | 0 | 0 | 0 | 0 |
| shadow | 3/20 | 0.1500 | 13.05 | 261 | 49 | 4 | 0 | 0 |
| soft high/0.6 | 2/20 | 0.1000 | 12.40 | 248 | 48 | 4 | 18 | 14 |

## Did Soft Intervention Actually Trigger?

Yes. `soft high/0.6` produced `revise_once_count=18`, and `changed_by_controller_count=14`.

Example: task 1 step 6 triggered on `risk_level=high`, `confidence=0.95`, `recommendation=stop`; the controller revised once and the executed action differed from the proposed action.

## Did Success Rate Improve?

No measured improvement in this run.

- Direct: 2/20
- Soft high/0.6: 2/20
- Absolute change vs direct: +0.0000

Shadow reached 3/20, but shadow does not intervene and should not be interpreted as a guard improvement.

## Warning Correlation

Shadow generated many warnings: 49 high-risk and 4 critical-risk predictions. In shadow, 16 failed tasks and 3 successful tasks had high/critical warnings. This indicates the predictor is not merely silent, but warnings alone are not enough to improve outcomes without a stronger correction policy.

In soft high/0.6, 17 failed tasks and 1 successful task had high/critical warnings. The intervention often changed actions, but did not reliably convert failures into successes.

## Task Logs

Commit-friendly task logs are exported here:

- `reports/retail_0_19_task_logs/direct.md`
- `reports/retail_0_19_task_logs/predictor_shadow.md`
- `reports/retail_0_19_task_logs/predictor_soft_high06.md`
- `reports/retail_0_19_task_logs/predictor_soft_high07_partial.md`

Each file contains per-task success/failure, termination reason, failed expected action checks, risk warnings, revise counts, and step-level proposed/executed actions.

## Limitations

- This is a small retail 0-19 subset, not an official benchmark score.
- The user simulator and evaluator are local Qwen, not the official leaderboard setting.
- The method is prompt-only. There is no training, no RL, no rollback, no recovery, and no comparator.
- Soft intervention revises once; it does not verify the revised action before execution.
- No dataset-specific heuristic, gold answer, or reference trajectory was used.
- Predictor calls add substantial latency. Direct 0-19 finished much faster than predictor-based runs.
