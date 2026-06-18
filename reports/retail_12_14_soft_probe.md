# Retail 12-14 Soft Controller v2 小样本验证

## 实验设置

- Run: `retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval`
- Tasks: retail `12,13,14`
- Agent: Qwen3-8B
- Predictor: Qwen3-8B
- User simulator: DeepSeek V4 Pro
- Evaluator: DeepSeek V4 Pro
- Controller: `predictor_soft`, `controller_version=v2`
- Thresholds: `soft_risk_level=high`, `confidence>=0.6`, `intervention_confidence>=0.6`

## 结果

| task_id | final_success | steps | revise_once | executed_revised | 结论 |
|---|---:|---:|---:|---:|---|
| 12 | true | 11 | 0 | 0 | 正确完成 |
| 13 | false | 20 | 4 | 4 | 干预后拖到 max steps |
| 14 | false | 11 | 1 | 1 | 写操作失败 |

总体成功率：`1/3 = 33.33%`。

## 对照

| task_id | direct 0-19 | shadow 0-19 | soft 12-14 |
|---|---:|---:|---:|
| 12 | true | true | true |
| 13 | true | true | false |
| 14 | false | true | false |

`shadow` 不干预，只记录 predictor 判断；因此 `13` 和 `14` 在 shadow 中成功但 soft 中失败，说明当前 Controller v2 的实际干预策略仍有副作用。

## 失败溯源

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

- Summary: `runs/retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval/summary.json`
- Step logs:
  - `runs/retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval/task_12.jsonl`
  - `runs/retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval/task_13.jsonl`
  - `runs/retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval/task_14.jsonl`
- Auto analysis: `reports/retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval_analysis.md`
