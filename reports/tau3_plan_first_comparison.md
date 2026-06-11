# Tau3 Retail Plan-First 对比报告

日期：2026-06-11

本报告对比两个本地 agent：

- 原始 direct Qwen3-8B agent。
- plan-first agent：每次真实行动前，先让模型做一次私有计划，预测下一步行动的后果、风险、代价和推荐度，然后再生成真实工具调用或用户回复。

测试集相同：tau3 retail base 子集任务 `0 1 2 3 4`。

## 代码版本说明

V1 和 V2 不是两个并存的可运行源码文件。我是在同一个 `scripts/plan_first_agent.py` 上先实现 V1，跑出诊断失败后，直接把 prompt 和计划 token 配置收紧为 V2。

因此当前仓库里可运行的 `plan_first` 代码是 V2。V1 没有作为独立源码快照保留；保留下来的是 V1 的完整实验轨迹和诊断报告：

- V1 轨迹：`trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first`
- V1 诊断报告：`reports/tau3_retail_plan_first_v1_diagnostic.md`

## 运行结果

| 运行目录 | agent 模式 | 任务数 | 成功数 | 准确率 | 备注 |
|---|---|---:|---:|---:|---|
| `20260611_tau3_retail_qwen3_8b_subset5_local_eval` | direct | 5 | 1 | 20.0% | baseline |
| `20260611_tau3_retail_qwen3_8b_subset5_plan_first` | plan-first V1 | 1 | 0 | 0.0% | 诊断性半途运行；长计划 prompt 导致反复查错 item |
| `20260611_tau3_retail_qwen3_8b_subset5_plan_first_v2` | plan-first V2 | 5 | 0 | 0.0% | 压缩计划 prompt 后的完整 5 条运行 |

## 按任务对比

| task | direct 结果 | plan-first V2 结果 | 变化 |
|---|---|---|---|
| 0 | 成功，reward 1.0 | `too_many_errors`，reward 0.0 | 明显退化；模型猜 product ID 并重复失败查询 |
| 1 | `db_state_failed`，reward 0.0 | `too_many_errors`，reward 0.0 | 退化；重复查询无效 order ID |
| 2 | `db_state_failed`，reward 0.0 | `nl_assertion_failed`，reward 0.0 | 部分改善；DB 状态通过，但最终回复说 9 个选项，没有满足“10 个 T-shirt 选项”的断言 |
| 3 | `nl_assertion_failed`，reward 0.0 | `nl_assertion_failed`，reward 0.0 | 没有成功率提升；仍遗漏必要订单检查，最终数量也不对 |
| 4 | `max_steps`，reward 0.0 | `max_steps`，reward 0.0 | 没改善；变慢，并陷入反复澄清 |

## 失败根因

Plan-first V1 暴露了最清晰的问题：

- task 0 反复调用 `get_item_details`，参数是已知错误或模型猜出来的 item ID。
- 连续 5 次 `Item not found` 后触发 `too_many_errors`。
- direct baseline 在同一个 task 0 上成功，所以这不是环境问题，而是策略退化。

Plan-first V2 压缩了计划内容，也降低了一些工具调用数，但仍没有提高成功率：

- task 0 和 task 1 都因为重复错误工具调用终止。
- task 2 的写入侧 DB 状态做对了，但最终自然语言断言失败。
- task 3 修改了一个订单，但不是期望的订单/商品路径，仍然没满足“10 个 T-shirt 选项”的断言。
- task 4 主要卡在面向用户的澄清循环，直到 `max_steps`。

## 风险与代价

plan-first 每个真实 agent turn 多一次私有计划调用，所以 LLM 调用量接近翻倍。这个 5 条本地实验里，它还显著增加了平均耗时：

| 模式 | 工具调用总数 | 平均任务耗时 |
|---|---:|---:|
| direct | 46 | 13.1s |
| plan-first V2 | 31 | 34.9s |

plan-first V2 工具调用更少不是好事：两个任务是提前因为重复工具错误终止，一个任务是在澄清中耗到 `max_steps`。

## 结论

不建议把这个 naive text plan-first 作为 Qwen3-8B 在 tau3 retail 上的默认策略。

它确实让模型在话术上更谨慎，但也更容易把模型锚定在错误计划上，尤其是：

- 伪造 ID；
- 相信用户模拟器给出的错误 ID；
- 重复查询已经失败过的参数；
- 没有优先从订单详情中拿真实 product/item/payment IDs。

## 更推荐的下一步

比继续加自由文本 plan 更靠谱的是做代码层 action reviewer / guardrail：

- 工具报错后阻止完全相同的重复工具调用；
- 拒绝没有来自用户文本或工具返回的猜测 ID；
- 写操作前强制检查 read-only 证据是否完整；
- 写操作前检查是否满足确认要求；
- 最终回复前做 benchmark-sensitive checklist，比如商品选项数量。

这个方向更可能保住 baseline 的成功样本，同时直接针对轨迹里出现的真实失败根因。

## 相关文件

- baseline 轨迹：`trajectories/20260611_tau3_retail_qwen3_8b_subset5_local_eval`
- plan-first V1 诊断轨迹：`trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first`
- plan-first V2 完整轨迹：`trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first_v2`
- baseline 报告：`reports/tau3_retail_subset_summary.md`
- V1 诊断报告：`reports/tau3_retail_plan_first_v1_diagnostic.md`
- V2 报告：`reports/tau3_retail_plan_first_v2_summary.md`
- task0 案例拆解：`reports/task0_case_study.md`
