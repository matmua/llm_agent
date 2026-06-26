# WebShop20 threshold3 repair 实验总结

## 本次改动

只做了任务安排要求的两个最小修改：

1. `shadow/post.py`：trajectory-level `repeated_behavior_risk` 阈值从连续 5 次相同 `action_signature` 改为连续 3 次。
2. `intervention/repair_hint.py`：按四类 `error_type` 输出固定 repair hint 模板。

确认未修改：

- `shadow/pre.py` 逻辑未改。
- LLM verifier prompt 与判断逻辑未改。
- agent prompt 结构未改。
- `state_to_agent=false`，没有把完整 shadow state 给 agent。
- local no-progress 仍是同 context、同 action signature、无 visible delta 第 3 次触发。
- context cycle 规则未改。
- `loop_or_repetition` 仍是同一个 error type，只在 hint 文本层面按已有 `post_check` 字段区分强弱。

## 实验设置

三组都跑 WebShop 前 20 条，`max_steps=15`，模型为本地 `qwen3-8b`，项目流量通过 `no_proxy_run.sh` 走服务器网络。

| 组别 | llm_risk_verify | repair_hint_enabled | state_to_agent | 日志 |
|---|---:|---:|---:|---|
| baseline | false | false | false | `logs/rule_shadow_v1_baseline_threshold3_webshop20/` |
| verify-only | true | false | false | `logs/rule_shadow_v1_prepost_llmverify_threshold3_webshop20/` |
| hint repair | true | true | false | `logs/rule_shadow_v1_hintrepair_threshold3_webshop20/` |

## 核心结果

| 组别 | success | success_rate | avg_reward | avg_steps | action 数 | verifier calls | verified errors | post hints | action_changed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 13 / 20 | 0.6500 | 0.3709 | 9.55 | 191 | 0 | 0 | 0 | 0 |
| verify-only | 13 / 20 | 0.6500 | 0.3709 | 9.55 | 191 | 64 | 61 | 0 | 0 |
| hint repair | 16 / 20 | 0.8000 | 0.4285 | 8.85 | 177 | 20 | 14 | 12 | 1 |

本轮 repair 相比 baseline 提升 3 / 20，即 +15 个百分点。平均步数从 9.55 降到 8.85。

## baseline 与 verify-only 一致性

成功率、平均 reward、平均步数完全一致，`action_changed_count=0`。

但逐 action 比对发现 task 0 的 action 序列不一致。首个分叉发生在 step 1：

- baseline：`click[b08k7ldm7q]`
- verify-only：`click[next >]`
- 该 step 的 `agent_prompt_sha256` 完全相同：`5bdd237fac2f3958a587ecefa93579729058506cb1d52d50f3c25e10bcce8838`

因此这个分叉不是 shadow/verifier 字段进入 prompt 导致的，而是本地 Qwen/vLLM 在同 prompt 下的生成非确定性。verify-only 没有 repair hint，也没有改写 action。

## repeated_behavior_risk 阈值核验

`repeated_behavior_risk_threshold=3` 已写入三组 `metrics.json`。

重点任务触发位置：

| task | baseline first repeated step | verify first repeated step | repair first repeated step | signature |
|---:|---:|---:|---:|---|
| 5 | 3 | 3 | 3 | `click|target=next >` |
| 15 | 3 | 3 | 3 | `click|target=next >` |
| 18 | 3 | 3 | 3 | `click|target=next >` |

这说明原来连续翻页到第 5 次才触发的问题已经修正为第 3 次触发。

## 关键任务结果

| task | baseline | verify-only | hint repair | 结论 |
|---:|---:|---:|---:|---|
| 4 | success, 12 steps | success, 12 steps | success, 12 steps | 不再被 repair 误伤 |
| 5 | fail, 15 steps | fail, 15 steps | success, 12 steps | 修复成功 |
| 7 | fail, 15 steps | fail, 15 steps | success, 15 steps | 仍然修复成功 |
| 15 | fail, 15 steps | fail, 15 steps | success, 6 steps | 修复成功 |
| 18 | fail, 15 steps | fail, 15 steps | fail, 15 steps | 有干预但未修复 |

task 7 的直接修复点是 step 14：模型在 hint 后仍重复 `click[b09npml43m]`，已有 pre-repair 机制再次用普通文本 hint 让 agent 生成了 `click[buy now]`，最终 reward=0.6667。

## repair 为什么仍失败

hint repair 组仍失败 4 条：task 0、13、14、18。

- task 0：step 3 发现连续 `click[next >]` 并生成 hint，step 4 确实转向候选商品，但后续又回到搜索/翻页循环；step 14 再次触发时已经没有剩余步数。干预能打断局部循环，但没有能力判断哪个枕头满足全部属性。
- task 13：主要是错误商品探索和尺寸/颜色/形状语义不收敛。只有一次连续翻页风险，但 verifier 没判为 error，repair 没真正介入。
- task 14：动作在搜索、商品页、features、返回之间切换，没有形成连续相同 action signature，因此通用重复规则很少触发。错误更偏语义目标匹配失败。
- task 18：step 3 打断连续翻页，step 7 又打断连续选择 `xx-large`，但 agent 转去 description/back/search 后仍没有找到满足全部约束的商品。干预强度足以阻止重复动作，不足以做目标商品验证。

结论：这版 repair 对“连续翻页/连续点同一商品”有效，对“目标语义匹配错误、候选商品选择错误、属性约束未满足”仍弱。按本次任务约束，没有新增商品-任务匹配 verifier，所以这些失败是预期边界。

## 文件索引

- baseline metrics：`reports/rule_shadow_v1_baseline_threshold3_webshop20/metrics.json`
- verify-only metrics：`reports/rule_shadow_v1_prepost_llmverify_threshold3_webshop20/metrics.json`
- hint repair metrics：`reports/rule_shadow_v1_hintrepair_threshold3_webshop20/metrics.json`
- baseline 完整轨迹：`logs/rule_shadow_v1_baseline_threshold3_webshop20/trajectories.jsonl`
- verify-only 完整轨迹：`logs/rule_shadow_v1_prepost_llmverify_threshold3_webshop20/trajectories.jsonl`
- hint repair 完整轨迹：`logs/rule_shadow_v1_hintrepair_threshold3_webshop20/trajectories.jsonl`
- verify-only pre/post 准确性：`reports/rule_shadow_v1_prepost_llmverify_threshold3_webshop20/pre_post_accuracy_zh.md`
- hint repair pre/post 准确性：`reports/rule_shadow_v1_hintrepair_threshold3_webshop20/pre_post_accuracy_zh.md`
