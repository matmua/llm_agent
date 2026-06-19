# WebShop Phase 2 Intervention 结果摘要

## 完成内容

- 保留 Phase 1 `shadow` 模式，仍保证 `executed_action == raw_action`。
- 新增 `intervention` 模式，只有该模式允许改写 action。
- 实现 `CompletionPolicy`、`RiskAwareActionRouter`、`MinimalStateRepair`、`CheckpointManager`、`InterventionLogger`。
- 新增 `analysis/evaluate_interventions.py`，用于比较 direct、shadow、intervention 三组结果。
- 每个任务的逐步日志已整理到 `reports/webshop_phase2/task_logs/`。
- 原始 JSONL 轨迹副本已整理到 `reports/webshop_phase2/raw_logs/`。

## 官方 WebShop small 20 条结果

当前实验使用 deterministic `MockLLMClient`，用于验证框架和干预策略，不代表 Qwen/DeepSeek 的模型能力分数。

| 模式 | 成功数 | 成功率 | 平均 step | 平均 reward | post_error率 | 改写 action | 修复执行 |
|---|---:|---:|---:|---:|---:|---:|---:|
| direct | 13/20 | 0.6500 | 3.0000 | 0.2662 | 0.1333 | 0 | 0 |
| shadow | 13/20 | 0.6500 | 3.0000 | 0.2662 | 0.1333 | 0 | 0 |
| intervention | 14/20 | 0.7000 | 4.3500 | 0.2807 | 0.0920 | 20 | 8 |

## 重点结论

- 成功率提升：intervention 相比 direct/shadow 提升 0.05，救回 task 16 和 task 19。
- 平均 step 增加：从 3.00 增加到 4.35，主要成本来自详情页补全和 `< prev>` 返回产品页。
- 高风险 action 被阻断后的 episode 成功率为 0.50；没有出现 shadow/direct 成功但 intervention 因改写失败的误伤任务。
- 修复动作执行 8 次，涉及 4 个 episode；其中 2 个最终成功，恢复成功率 0.50。
- 修复后窗口 post_error 率从 1.00 降到 0.00，说明当前最小修复对后续错误传播有抑制作用，但样本很小。

## 查看路径

- 总报告：`reports/webshop_phase2/intervention_comparison.md`
- 指标 JSON：`reports/webshop_phase2/intervention_metrics.json`
- 每任务 Markdown 日志：`reports/webshop_phase2/task_logs/direct.md`、`shadow.md`、`intervention.md`
- 原始轨迹 JSONL：`reports/webshop_phase2/raw_logs/*/steps.jsonl`

## 解释边界

本阶段重点是验证 WebShop Phase 2 干预框架是否能真实改写 action、保存轨迹、对比三模式并分析错误传播。后续如果要评估模型能力，需要把 `--model mock` 替换为 OpenAI-compatible 的 Qwen/DeepSeek/其他 LLM endpoint 后重跑同一组脚本。
