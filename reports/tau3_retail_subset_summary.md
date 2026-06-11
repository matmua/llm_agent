# Tau3 Retail Direct Baseline 摘要

- 运行目录：`/root/autodl-tmp/llm_agent/trajectories/20260611_tau3_retail_qwen3_8b_subset5_local_eval`
- 模式：direct baseline
- 总模拟数：5
- 有效计分模拟数：5
- 提前终止/基础设施类失败：1
- 成功数：1
- 全部尝试任务准确率：0.2000
- 有效计分任务准确率：0.2000

## 失败类型

- `success`: 1
- `db_state_failed`: 2
- `nl_assertion_failed`: 1
- `premature_termination:max_steps`: 1

## 单任务结果

| task_id | reward | 终止原因 | 失败类型 | 工具调用数 | 消息数 |
|---|---:|---|---|---:|---:|
| 0 | 1.0 | user_stop | success | 6 | 16 |
| 1 | 0.0 | user_stop | db_state_failed | 11 | 28 |
| 2 | 0.0 | user_stop | db_state_failed | 8 | 24 |
| 3 | 0.0 | user_stop | nl_assertion_failed | 8 | 30 |
| 4 | 0.0 | max_steps | premature_termination:max_steps | 13 | 41 |

## 官方参考值

以下是 tau3-bench 仓库快照中的完整 retail leaderboard pass^1 结果。它们不能和这个本地 5 条运行直接比较，因为这里 Qwen3-8B 同时作为 agent、user simulator 和本地 NL assertion evaluator。

- Qwen3.5-397B-A17B retail pass^1: 84.43%
- Qwen3-Max-Thinking retail pass^1: 79.39%
- GPT-4.1 retail pass^1: 74.00%
- o4-mini retail pass^1: 68.30%

## 失败轨迹摘要

### Task 1 - `db_state_failed`

- 最后用户消息：`###STOP###`
- 最后 assistant 消息：assistant 声称已经完成机械键盘和智能温控器换货。
- 工具错误：连续出现 `Error: Variant not found`。
- 失败点：期望的换货写入状态没有完全匹配，尤其是 `exchange_delivered_order_items` 的旧/新 item IDs 和 payment method 路径。

### Task 2 - `db_state_failed`

- 最后用户消息：`###STOP###`
- 最后 assistant 消息：assistant 声称已经发起订单 `#W2378156` 的退货。
- 工具错误：出现 `Error: Order not found`。
- 失败点：遗漏多个期望的订单详情检查，并且最终退货 item 列表与 benchmark 期望不一致。

### Task 3 - `nl_assertion_failed`

- 最后用户消息：`###TRANSFER###`
- 最后 assistant 消息：assistant 将用户转人工。
- 工具错误：多次 `Order not found`，后面还有 `User not found`。
- 失败点：没有给出 benchmark 要求的 T-shirt 选项数量，也遗漏多个订单检查和修改动作。

### Task 4 - `premature_termination:max_steps`

- 最后用户消息：用户想修改账户里所有 pending T-shirts，并问能否一次性应用到所有订单。
- 最后 assistant 消息：assistant 已列出若干订单和 pending T-shirt 信息，但还没完成任务。
- 工具错误：多次 `Order not found` 和一次 `User not found`。
- 失败点：轨迹拖到最大步数，未完成最终修改。

## 成功样本

task 0 是 baseline 中唯一成功的任务。详细案例见：

- `reports/task0_case_study.md`
