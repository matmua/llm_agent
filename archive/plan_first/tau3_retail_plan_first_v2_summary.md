# Tau3 Retail Plan-First V2 错误摘要

- 运行目录：`/root/autodl-tmp/llm_agent/trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first_v2`
- 模式：plan-first V2
- 总模拟数：5
- 有效计分模拟数：5
- 提前终止/基础设施类失败：3
- 成功数：0
- 全部尝试任务准确率：0.0000
- 有效计分任务准确率：0.0000

## 失败类型

- `premature_termination:too_many_errors`: 2
- `nl_assertion_failed`: 2
- `premature_termination:max_steps`: 1

## 单任务结果

| task_id | reward | 终止原因 | 失败类型 | 工具调用数 | 消息数 |
|---|---:|---|---|---:|---:|
| 0 | 0.0 | too_many_errors | premature_termination:too_many_errors | 5 | 14 |
| 1 | 0.0 | too_many_errors | premature_termination:too_many_errors | 5 | 22 |
| 2 | 0.0 | user_stop | nl_assertion_failed | 10 | 30 |
| 3 | 0.0 | user_stop | nl_assertion_failed | 8 | 30 |
| 4 | 0.0 | max_steps | premature_termination:max_steps | 3 | 41 |

## 官方参考值

以下是 tau3-bench 仓库快照中的完整 retail leaderboard pass^1 结果。它们不能和这个本地 5 条运行直接比较，因为这里 Qwen3-8B 同时作为 agent、user simulator 和本地 NL assertion evaluator。

- Qwen3.5-397B-A17B retail pass^1: 84.43%
- Qwen3-Max-Thinking retail pass^1: 79.39%
- GPT-4.1 retail pass^1: 74.00%
- o4-mini retail pass^1: 68.30%

## 失败轨迹摘要

### Task 0 - `premature_termination:too_many_errors`

- 最后用户消息：用户给出了猜测的 product IDs：`KB-4567` 和 `TH-8901`。
- 最后 assistant 消息：assistant 继续要求用户提供机械键盘和智能温控器的 product IDs。
- 工具错误：连续 5 次 `Error: Product not found`。

根因：agent 没有先查订单 `#W2378156`，而是先用 `mechanical_keyboard_id` 这类占位符调用 `get_product_details`。失败后又相信用户模拟器猜出的 `KB-4567`、`TH-8901`，导致重复无效查询。

### Task 1 - `premature_termination:too_many_errors`

- 最后用户消息：用户确认订单是 `#W2378156`，但没有 variant IDs，希望 agent 帮忙处理换货。
- 最后 assistant 消息：assistant 要求用户提供订单详情和 variant IDs。
- 工具错误：连续 5 次 `Error: Order not found`。

根因：agent 用 `W2378156` 查询订单，而环境里的订单 ID 需要 `#W2378156`。错误后没有切换策略，比如用姓名和 zip 找用户，再从用户订单列表中确认订单。

### Task 2 - `nl_assertion_failed`

- 最后用户消息：`###STOP###`
- 最后 assistant 消息：assistant 列出了一批 T-Shirt 选项。
- 工具错误：调用了不存在的 `get_user_orders`。
- 失败断言：benchmark 期望 agent 告诉用户有 10 个 T-shirt 选项；实际回复只说了 9 个可用选项，没有满足“总数 10 个”的断言。

根因：DB 写入侧相比 baseline 有改善，但最终回答没有覆盖 benchmark 要求的数量表述。

### Task 3 - `nl_assertion_failed`

- 最后用户消息：用户感谢并结束。
- 最后 assistant 消息：assistant 声称已修改订单 `#W6247578`。
- 工具错误：一开始查 product 时出现 `Error: Product not found`。
- 失败断言：仍未正确告诉用户有 10 个 T-shirt 选项。

根因：agent 修改了订单，但不是期望的完整订单/商品路径；还遗漏了多个期望的订单详情检查。

### Task 4 - `premature_termination:max_steps`

- 最后用户消息：用户没有 email 和 order ID，希望知道是否还有别的办法继续。
- 最后 assistant 消息：assistant 仍要求用户提供 order ID 和 email。
- 工具错误：一开始查 product 时出现 `Error: Product not found`。

根因：agent 没有充分利用用户姓名/zip 或账户查询路径，转而陷入反复向用户索要信息，最终达到最大步数。

## 总结

plan-first V2 没有提升成功率。它降低了一部分工具调用数量，但主要是因为两个任务提前失败、一个任务卡到 `max_steps`。真正需要的是代码层 guardrail，而不是继续让同一个模型用自由文本计划自我约束。
