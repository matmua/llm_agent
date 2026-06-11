# Tau3 Retail Plan-First V1 诊断报告

- 运行目录：`/root/autodl-tmp/llm_agent/trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first`
- 模式：plan-first V1
- 总模拟数：1
- 有效计分模拟数：1
- 提前终止/基础设施类失败：1
- 成功数：0
- 全部尝试任务准确率：0.0000
- 有效计分任务准确率：0.0000

## 失败类型

- `premature_termination:too_many_errors`: 1

## 单任务结果

| task_id | reward | 终止原因 | 失败类型 | 工具调用数 | 消息数 |
|---|---:|---|---|---:|---:|
| 0 | 0.0 | too_many_errors | premature_termination:too_many_errors | 9 | 20 |

## 官方参考值

以下是 tau3-bench 仓库快照中的完整 retail leaderboard pass^1 结果。它们不能和这个本地 1 条诊断运行直接比较，因为这里 Qwen3-8B 同时作为 agent、user simulator 和本地 NL assertion evaluator。

- Qwen3.5-397B-A17B retail pass^1: 84.43%
- Qwen3-Max-Thinking retail pass^1: 79.39%
- GPT-4.1 retail pass^1: 74.00%
- o4-mini retail pass^1: 68.30%

## 失败轨迹摘要

### Task 0 - `premature_termination:too_many_errors`

- 最后用户消息：用户仍在说明订单 `W2378156`，希望把机械键盘换成 clicky，并把智能温控器换成 Google Home 兼容版本。
- 最后 assistant 消息：`Hi! How can I help you today?`
- 关键错误：连续 5 次 `Error: Item not found`。

错误工具调用集中在：

- `get_item_details("1151293680")` 被重复查询；
- 后续又猜测并反复查询 `get_item_details("1008292230")`；
- 该 ID 不存在，最终触发 `too_many_errors`。

## 诊断结论

V1 的长计划 prompt 没有形成可靠的安全门，反而把模型带入“反复验证猜测 item ID”的坏循环。这个失败很明确：direct baseline 在同一个 task 0 上成功，说明问题来自 plan-first 策略，而不是 benchmark 环境。
