# Retail Soft Controller v2 小样本验证

## 样本来源

本报告合并两段 soft Controller v2 实验：

- `0-7`: 来自中断的 partial run `retail_0_19_soft_controller_v2_qwen_predictor_deepseek_user_eval_partial_stopped_after_9_20260619_003124`
- `12-14`: 来自完整三任务 run `retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval`

说明：partial run 中 `task_8` 也已经完成，`task_9` 是中断轨迹；本报告按当前要求只合并 `0-7` 和 `12-14`。

## 实验设置

- Agent: Qwen3-8B
- Predictor: Qwen3-8B
- User simulator: DeepSeek V4 Pro
- Evaluator: DeepSeek V4 Pro
- Controller: `predictor_soft`, `controller_version=v2`
- Thresholds: `soft_risk_level=high`, `confidence>=0.6`, `intervention_confidence>=0.6`

## 合并结果

| task_id | source | final_success | reward | termination | steps | high | critical | revise_once | executed_revised | fallback | 结论 |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| 0 | partial 0-19 | false | 0.0 | max_steps | 20 | 4 | 2 | 4 | 3 | 1 | 步数耗尽 |
| 1 | partial 0-19 | false | 0.0 | user_stop | 18 | 3 | 0 | 3 | 1 | 2 | exchange 写操作失败 |
| 2 | partial 0-19 | false | 0.0 | too_many_errors | 20 | 3 | 2 | 2 | 1 | 1 | 工具/对话错误累积 |
| 3 | partial 0-19 | false | 0.0 | user_stop | 14 | 0 | 0 | 0 | 0 | 0 | NL assertion 失败 |
| 4 | partial 0-19 | false | 0.0 | max_steps | 20 | 3 | 2 | 2 | 0 | 2 | 步数耗尽 |
| 5 | partial 0-19 | false | 0.0 | user_stop | 17 | 0 | 2 | 1 | 1 | 0 | return 写操作失败 |
| 6 | partial 0-19 | false | 0.0 | user_stop | 14 | 1 | 2 | 2 | 2 | 0 | product lookup + exchange 写操作失败 |
| 7 | partial 0-19 | false | 0.0 | user_stop | 17 | 0 | 1 | 1 | 1 | 0 | product lookup + exchange 写操作失败 |
| 12 | soft 12-14 | true | 1.0 | user_stop | 11 | 0 | 0 | 0 | 0 | 0 | 正确完成 |
| 13 | soft 12-14 | false | 0.0 | max_steps | 20 | 4 | 0 | 4 | 4 | 0 | 干预后拖到 max steps |
| 14 | soft 12-14 | false | 0.0 | user_stop | 11 | 1 | 0 | 1 | 1 | 0 | return 写操作失败 |

合并成功率：`1/11 = 9.09%`。

合并干预统计：

- Predictor calls / logged steps: `182`
- High risk warnings: `19`
- Critical risk warnings: `11`
- Revise interventions: `20`
- Executed revised actions: `14`
- Executed fallback actions: `6`
- Risk reduced after revision: `14`

## 对照

| task_id | direct 0-19 | shadow 0-19 | soft sample |
|---|---:|---:|---:|
| 0 | false | false | false |
| 1 | false | false | false |
| 2 | false | false | false |
| 3 | false | false | false |
| 4 | false | false | false |
| 5 | false | false | false |
| 6 | false | true | false |
| 7 | false | false | false |
| 12 | true | true | true |
| 13 | true | true | false |
| 14 | false | true | false |

同一组任务上，direct 是 `2/11`，shadow 是 `4/11`，soft sample 是 `1/11`。`shadow` 只旁路记录，不干预；因此它不能被解释为 controller 提升，只用于观察 predictor 对风险的判断。

## 主要结论

当前 Controller v2 的工程路径是通的：能按阈值触发 revise，能记录 revised action，能做 second check，也能落完整轨迹。

但策略效果不好。主要问题不是“不会干预”，而是“干预经常把可执行写动作改成继续确认或更保守的话术”，导致任务不能在最大步数内完成，或者错过正确写操作。

## 失败溯源

### 0-7 partial

- `task 0` 和 `task 4` 都以 `max_steps` 结束。controller 多次干预后没有把路径拉回可完成状态。
- `task 1` 读信息基本可行，但 `exchange_delivered_order_items` 写操作失败。
- `task 2` 以 `too_many_errors` 结束，说明动作/对话错误累积到环境停止。
- `task 3` 没有触发 high/critical 干预，DB 可过但最终自然语言断言失败，典型沟通信息错误。
- `task 5/6/7` 主要失败在 return/exchange 写操作参数或 product lookup grounding，不是单纯缺少风险预警。

### Task 13

- Controller 触发 4 次 revise，全部执行 revised action。
- 多次把原本的 `return_delivered_order_items` tool call 改写成“请用户再次确认退款方式/是否继续”的自然语言消息。
- 第 19 步才执行使用原支付方式的 `return_delivered_order_items`，但第 20 步后达到最大步数，最终失败。
- 结论：预测器对 payment method 风险判断有价值，但 controller 的改写过于保守，把可执行写动作改成了反复确认，导致错误传播为步数耗尽。

### Task 14

- Controller 第 4 步触发 1 次 revise，把读取用户详情改成继续询问 order id。
- 后续 agent 执行 `return_delivered_order_items`，但 item_ids 包含错误/过多条目，写操作检查 0/2。
- 结论：该失败不完全由单次 revise 直接造成；主要问题是 agent 对用户意图和 item selection 的 grounding 不稳，controller 没能纠正写操作参数。

## 文件位置

- 0-7 partial raw logs: `runs/retail_0_19_soft_controller_v2_qwen_predictor_deepseek_user_eval_partial_stopped_after_9_20260619_003124/task_*.jsonl`
- 12-14 raw logs: `runs/retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval/task_*.jsonl`
- 0-7 + 12-14 exported logs:
  - `reports/soft_sample_task_logs_deepseek_v2/retail_0_19_soft_controller_v2_qwen_predictor_deepseek_user_eval_partial_stopped_after_9_20260619_003124.md`
  - `reports/soft_sample_task_logs_deepseek_v2/retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval.md`
- 12-14 auto analysis: `reports/retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval_analysis.md`
