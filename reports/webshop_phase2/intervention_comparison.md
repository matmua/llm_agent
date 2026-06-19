# WebShop Phase 2 Intervention 对比报告

本报告比较三种模式：原始 ReAct agent、Phase 1 shadow 检测不干预、Phase 2 intervention agent。当前实验使用同一批 task id，并保留 raw logs 与逐任务摘要。

## 运行配置

| 模式 | log_dir | env | model | num_tasks | max_steps |
|---|---|---|---|---:|---:|
| direct | `logs/webshop_phase2_direct` | `OfficialWebShopEnv` | `mock` | 20 | 10 |
| shadow | `logs/webshop_phase2_shadow` | `OfficialWebShopEnv` | `mock` | 20 | 10 |
| intervention | `logs/webshop_phase2_intervention` | `OfficialWebShopEnv` | `mock` | 20 | 10 |

## 核心指标

| 模式 | 成功数 | 成功率 | 平均 step | 平均 reward | post_error率 | 改写 action | 修复执行 | 平均 token估算 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| direct | 13/20 | 0.6500 | 3.0000 | 0.2662 | 0.1333 | 0 | 0 | 1599.3500 |
| shadow | 13/20 | 0.6500 | 3.0000 | 0.2662 | 0.1333 | 0 | 0 | 1599.3500 |
| intervention | 14/20 | 0.7000 | 4.3500 | 0.2807 | 0.0920 | 20 | 8 | 2431.2000 |

## 关键结论

- 成功率变化：intervention 相对 direct 为 +0.0500，相对 shadow 为 +0.0500。
- 平均 step 变化：intervention 相对 direct 为 +1.3500，相对 shadow 为 +1.3500。
- 高风险阻断后的成功率：intervention 中发生高风险阻断的 episode 成功率为 0.5000；shadow 中出现高风险提示的 episode 成功率为 1.0000。
- 误阻断比例：以 shadow 成功任务为基准，因 intervention 改写后失败的比例为 0.0000；任务 id：[]。
- 修复效果：intervention 修复动作执行 8 次，涉及 4 个 episode，最终恢复成功率为 0.5000。
- 修复后 post_error：修复前窗口 post_error 率 1.0000，修复后窗口 post_error 率 0.0000。

## 任务级变化

- intervention 相对 shadow 新救回任务：[16, 19]
- intervention 相对 direct 新救回任务：[16, 19]
- intervention 相对 shadow 误伤任务：[]
- intervention 相对 direct 误伤任务：[]

## 错误类别统计

### direct

Pre-action risk:

```json
{}
```

Post-action error:

```json
{
  "constraint_conflict": 8
}
```

### shadow

Pre-action risk:

```json
{
  "missing_attribute": 1,
  "premature_buy": 1,
  "insufficient_evidence": 4
}
```

Post-action error:

```json
{
  "constraint_conflict": 8
}
```

### intervention

Pre-action risk:

```json
{
  "missing_attribute": 17,
  "premature_buy": 17,
  "invalid_action": 10,
  "insufficient_evidence": 4
}
```

Post-action error:

```json
{
  "constraint_conflict": 4,
  "unexpected_transition": 4
}
```

## 查看位置

- 指标 JSON：`reports/webshop_phase2/intervention_metrics.json`
- 逐任务 Markdown 日志：`reports/webshop_phase2/task_logs/`
- 原始 JSONL 日志副本：`reports/webshop_phase2/raw_logs/`

## 解释边界

当前数值主要评估 Phase 2 框架与规则式 intervention 是否能改变失败传播，不等价于真实强 LLM 的 WebShop benchmark 分数。若要评估模型能力，应把 `--model mock` 换成 OpenAI-compatible 本地或远端模型后重跑同一脚本。
