# rule-based shadow v1 pre/post 准确性分析

## 结论先说

这个框架的状态表和动作表是跨 benchmark 设计的，但当前实测效果只对 WebShop 前 20 条成立。
跨 benchmark 可迁移的是 loop、attributes/actions schema、format parser、known/unknown 参数记录和 info_gain 的比较方法。
不可直接保证迁移的是 extractor 的质量和 action grammar：OSWorld、tau-bench、WebArena 等环境需要各自 adapter，把 observation、available actions、entity/property 抽取映射到同一套 attributes schema。

因此它不是“只能在 WebShop 生效”的结构，但目前不能声称在其他 benchmark 上有同等检测准确率。要跨 benchmark 测试，需要为新环境补 observation/action adapter，然后用同一份分析脚本复核误报。

## 准确率定义

- format 检测有机械真值：`pre.format_valid` 与 parser 结果比较。
- pre repeat 检测有规则真值：同一 context、同一 action_signature 之前是否出现过 `post.info_gain=false`。
- post 的原生目标不是“动作是否正确”，而是“是否出现新的 attribute value”。
- 为了估计误报，我额外使用一个启发式标签：`observable_no_effect = context_before == context_after and done=false and reward=0`。
- 如果把 `post.info_gain=false` 当作“no-effect 预测”，再与 `observable_no_effect` 比较，就能得到可审计的 TP/FP/FN/TN。但这比 v1 的原始设计更苛刻，因为回到已见过页面会被 post 记为 no new info，即使它确实发生了导航。

## 总体统计

- 样本数：20
- step/action 数：191
- 成功率：13 / 20 = 0.6500
- 平均 reward：0.3709
- 平均步数：9.55
- format invalid：0
- format accuracy against parser：1.0000
- pre repeat flag：6
- pre repeat strict disagreement：0
- pre repeat strict accuracy：1.0000
- pre repeat operational FP：0
- pre repeat operational FDR：0.0000
- post info_gain true / false：137 / 54
- observable no-effect：33
- post no-effect TP/FP/FN/TN：33 / 21 / 0 / 137
- post no-effect observable accuracy：0.8901
- post no-effect observable FDR：0.3889
- post no-effect observable FPR：0.1329
- post no-effect observable FNR：0.0000

## 逐样例汇总

| task | success | reward | steps | pre_strict_acc | pre_repeat | pre_repeat_FDR | post_info_false | post TP/FP/FN/TN | post_acc | post_FDR | post_FPR |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | false | 0.0000 | 15 | 1.0000 | 0 | 0.0000 | 0 | 0/0/0/15 | 1.0000 | 0.0000 | 0.0000 |
| 1 | true | 0.4286 | 3 | 1.0000 | 0 | 0.0000 | 0 | 0/0/0/3 | 1.0000 | 0.0000 | 0.0000 |
| 2 | true | 0.3333 | 5 | 1.0000 | 0 | 0.0000 | 2 | 2/0/0/3 | 1.0000 | 0.0000 | 0.0000 |
| 3 | true | 1.0000 | 13 | 1.0000 | 0 | 0.0000 | 5 | 1/4/0/8 | 0.6923 | 0.8000 | 0.3333 |
| 4 | true | 0.8889 | 12 | 1.0000 | 1 | 0.0000 | 6 | 4/2/0/6 | 0.8333 | 0.3333 | 0.2500 |
| 5 | false | 0.0000 | 15 | 1.0000 | 0 | 0.0000 | 0 | 0/0/0/15 | 1.0000 | 0.0000 | 0.0000 |
| 6 | true | 0.5714 | 7 | 1.0000 | 0 | 0.0000 | 4 | 4/0/0/3 | 1.0000 | 0.0000 | 0.0000 |
| 7 | false | 0.0000 | 15 | 1.0000 | 3 | 0.0000 | 10 | 8/2/0/5 | 0.8667 | 0.2000 | 0.2857 |
| 8 | true | 0.0909 | 5 | 1.0000 | 0 | 0.0000 | 0 | 0/0/0/5 | 1.0000 | 0.0000 | 0.0000 |
| 9 | true | 0.4286 | 6 | 1.0000 | 0 | 0.0000 | 2 | 2/0/0/4 | 1.0000 | 0.0000 | 0.0000 |
| 10 | true | 0.6000 | 3 | 1.0000 | 0 | 0.0000 | 0 | 0/0/0/3 | 1.0000 | 0.0000 | 0.0000 |
| 11 | true | 0.6000 | 7 | 1.0000 | 2 | 0.0000 | 4 | 4/0/0/3 | 1.0000 | 0.0000 | 0.0000 |
| 12 | true | 0.3333 | 5 | 1.0000 | 0 | 0.0000 | 0 | 0/0/0/5 | 1.0000 | 0.0000 | 0.0000 |
| 13 | false | 0.0000 | 15 | 1.0000 | 0 | 0.0000 | 8 | 3/5/0/7 | 0.6667 | 0.6250 | 0.4167 |
| 14 | false | 0.0000 | 15 | 1.0000 | 0 | 0.0000 | 7 | 1/6/0/8 | 0.6000 | 0.8571 | 0.4286 |
| 15 | false | 0.0000 | 15 | 1.0000 | 0 | 0.0000 | 0 | 0/0/0/15 | 1.0000 | 0.0000 | 0.0000 |
| 16 | true | 1.0000 | 9 | 1.0000 | 0 | 0.0000 | 4 | 2/2/0/5 | 0.7778 | 0.5000 | 0.2857 |
| 17 | true | 0.1429 | 6 | 1.0000 | 0 | 0.0000 | 0 | 0/0/0/6 | 1.0000 | 0.0000 | 0.0000 |
| 18 | false | 0.0000 | 15 | 1.0000 | 0 | 0.0000 | 0 | 0/0/0/15 | 1.0000 | 0.0000 | 0.0000 |
| 19 | true | 1.0000 | 5 | 1.0000 | 0 | 0.0000 | 2 | 2/0/0/3 | 1.0000 | 0.0000 | 0.0000 |

## 文件索引

- 完整原始轨迹和最终 shadow_state：`logs/rule_shadow_v1_baseline_promptfix_webshop20/trajectories.jsonl`
- 紧凑 state snapshot：`logs/rule_shadow_v1_baseline_promptfix_webshop20/state_snapshots_compact.jsonl`
- 逐 step 诊断 JSONL：`reports/rule_shadow_v1_baseline_promptfix_webshop20/pre_post_step_diagnostics.jsonl`
- 完整诊断 JSON：`reports/rule_shadow_v1_baseline_promptfix_webshop20/pre_post_diagnostics.json`
- 本报告：`reports/rule_shadow_v1_baseline_promptfix_webshop20/pre_post_accuracy_zh.md`

## 读数提醒

post 的 FP 高，主要不是代码 bug，而是定义差异：v1 的 `info_gain=false` 表示没有新属性，不等于动作完全无效。例如返回已访问过的列表页，context 发生变化，但没有新 attribute value，会在 no-effect 启发式审计里算作 FP。
