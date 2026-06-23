# WebShop20 verify / repair 逐轨迹审计

审计对象：最新 `promptfix` 版本。

使用的日志：

- verify-only：`logs/rule_shadow_v1_prepost_llmverify_promptfix_webshop20/trajectories.jsonl`
- hint repair：`logs/rule_shadow_v1_hintrepair_promptfix_webshop20/trajectories.jsonl`
- baseline：`logs/rule_shadow_v1_baseline_promptfix_webshop20/trajectories.jsonl`

## 1. 验证阶段检测准确率

这里采用 trajectory-level 口径：

- 最终失败轨迹 = 正类，应该至少检测到一次风险。
- 最终成功轨迹 = 负类，不应该触发风险。
- 只要轨迹中任一 pre/post verifier 判 `is_error=true`，就算该轨迹被检测到风险。

verify-only 总体：

| 指标 | 数值 |
|---|---:|
| TP | 5 |
| FP | 2 |
| FN | 2 |
| TN | 11 |
| Accuracy | 0.8000 |
| Precision | 0.7143 |
| Recall / failed-risk recall | 0.7143 |
| FPR / successful-risk rate | 0.1538 |
| FNR | 0.2857 |

对应任务：

- TP：0、5、7、15、18
- FP：4、11
- FN：13、14
- TN：1、2、3、6、8、9、10、12、16、17、19

注意：FP 是按“最终成功轨迹不该报错”的严格轨迹口径。task 4 和 task 11 都存在局部重复行为，所以它们也可以被理解为 benign/recovered risk；但一旦进入 repair，task 4 的这个局部风险会造成有害干预。

Action-level 计数不能直接当作准确率，因为每个 action 没有人工真值标签：

| 指标 | 数值 |
|---|---:|
| pre verifier calls | 6 |
| pre verifier is_error | 4 |
| post verifier calls | 46 |
| post verifier is_error | 46 |
| total verifier calls | 52 |
| total is_error | 50 |

这说明 post verifier 对规则触发非常激进：被 post rule 触发后 46/46 都判为 error。

## 2. Verify-only 逐轨迹表

| task | 最终结果 | verifier 风险 | 轨迹标签 | 人工说明 |
|---:|:---:|:---:|:---:|---|
| 0 | fail | yes | TP | 连续 `click[next >]`，step 5 后反复翻页，检测正确 |
| 1 | success | no | TN | 3 步成功，无明显风险 |
| 2 | success | no | TN | 5 步成功，无明显风险 |
| 3 | success | no | TN | 13 步成功，无明显风险 |
| 4 | success | yes | FP / recovered | `click[x-large]` 重复被报 risk，但 baseline 下一步 `buy now` 成功 |
| 5 | fail | yes | TP | 连续 `click[next >]` 翻页，检测正确 |
| 6 | success | no | TN | 成功，无风险 |
| 7 | fail | yes | TP | 后段重复 `click[b09npml43m]`，检测正确 |
| 8 | success | no | TN | 成功，无风险 |
| 9 | success | no | TN | 成功，无风险 |
| 10 | success | no | TN | 成功，无风险 |
| 11 | success | yes | FP / recovered | 重复 `click[b09qqp3356]` 被报 risk，但原轨迹仍 `buy now` 成功 |
| 12 | success | no | TN | 成功，无风险 |
| 13 | fail | no | FN | 语义失败：反复选择错误/不匹配的家具尺寸，但没有明显 no-progress/loop |
| 14 | fail | no | FN | 语义失败：浏览多个容器候选但没有形成循环风险，也没有 buy 前语义校验 |
| 15 | fail | yes | TP | 连续 `click[next >]`，检测正确 |
| 16 | success | no | TN | 成功，无风险 |
| 17 | success | no | TN | 成功，无风险 |
| 18 | fail | yes | TP | 连续 `click[next >]`，检测正确 |
| 19 | success | no | TN | 成功，无风险 |

## 3. Repair 阶段总体效果

baseline 与 repair：

| 组别 | success | avg reward | avg step |
|---|---:|---:|---:|
| baseline | 13/20 | 0.3709 | 9.55 |
| repair | 13/20 | 0.3698 | 9.60 |

repair 并不是完全没作用，而是正负抵消：

- task 7：fail -> success，repair 有正作用。
- task 11：success -> success，reward 0.6 -> 0.8，pre repair 有正作用。
- task 4：success -> fail，repair 有害。
- task 0、5、15、18：触发 hint，但仍失败。
- task 13、14：没有触发风险，因此 repair 没机会介入。

Repair 计数：

| 指标 | 数值 |
|---|---:|
| post_hint_created | 8 |
| post_hint_applied | 7 |
| repair_hint_followed | 7 |
| repair_hint_ignored | 0 |
| pre_repair_attempt_count | 1 |
| pre_repair_success_count | 1 |
| action_changed_count | 1 |

## 4. Repair 逐轨迹分析

| task | baseline -> repair | repair 行为 | 结果原因 |
|---:|---|---|---|
| 0 | fail -> fail | step 5 检测连续翻页，step 6 根据 hint 回到 search | 干预只打断翻页，没有给出新搜索策略或目标候选；后续仍重复查询/翻页 |
| 1 | success -> success | 无 hint | 不需要修复 |
| 2 | success -> success | 无 hint | 不需要修复 |
| 3 | success -> success | 无 hint | 不需要修复 |
| 4 | success -> fail | step 10 把重复 `click[x-large]` 判为 risk，step 11 hint 后改点 `description` | 有害干预。baseline step 11 会 `buy now` 成功；hint 打断了临门一脚 |
| 5 | fail -> fail | step 5 检测连续翻页，step 6 回 search | 干预太弱。后续出现 `click[value]` 占位动作和错误商品，没有 option completion |
| 6 | success -> success | 无 hint | 不需要修复 |
| 7 | fail -> success | step 12 重复商品点击被判 risk，step 13 hint 后转为 `buy now` | 有效干预。hint 让 agent 停止重复商品点击，转向购买 |
| 8 | success -> success | 无 hint | 不需要修复 |
| 9 | success -> success | 无 hint | 不需要修复 |
| 10 | success -> success | 无 hint | 不需要修复 |
| 11 | success -> success | pre repair 将 step 4 `click[b09qqp3356]` 改成 `click[3x-large]` | 有效但不是新增成功；reward 从 0.6 提到 0.8 |
| 12 | success -> success | 无 hint | 不需要修复 |
| 13 | fail -> fail | 无 hint | 漏检。错误是语义选择/尺寸不匹配，不是规则能抓的 loop/no-progress |
| 14 | fail -> fail | 无 hint | 漏检。探索多个商品但没有 buy 前语义校验，repair 没机会介入 |
| 15 | fail -> fail | step 5 检测翻页循环，后续又出现 option/查询循环 | hint 只让它暂时离开循环，无法生成候选选择策略 |
| 16 | success -> success | 无 hint | 不需要修复 |
| 17 | success -> success | 无 hint | 不需要修复 |
| 18 | fail -> fail | step 5 和 step 12 两次检测翻页循环，两次回 search | 干预太弱，只重置到 search，不会改写 query 或选具体候选 |
| 19 | success -> success | 无 hint | 不需要修复 |

## 5. 为什么 repair 净效果为 0

是的，主要原因是干预太弱，但不是唯一原因。

### 5.1 干预内容太弱

当前 post repair 主要是自然语言 hint：

```text
Risk-control hint for this action:
A repeated-behavior risk was verified. Avoid repeating this action...
```

这只能告诉 agent “别重复这个动作”，不能告诉它：

- 应该点哪个商品；
- 应该选择哪个 option；
- 之前哪个商品/选项组合已经失败；
- 当前是否应该 `buy now`；
- 是否应该改写 query。

所以 task 0、5、15、18 大多只是从 “一直 next” 变成 “back to search 后重新搜索/继续探索”，没有真正修复任务状态。

### 5.2 触发太晚

`repeated_behavior_risk` 通常要同一 action signature 连续 5 次才触发。到触发时，episode 已经消耗很多 step。比如 task 0、5、15、18 都在 step 5 之后才第一次提示，剩余预算不足以系统性重找候选。

### 5.3 检测覆盖不了语义错误

task 13、14 失败但没有风险命中。它们的问题不是“重复动作”，而是：

- 商品/尺寸/属性语义不匹配；
- 多次探索但没有形成规则层面的 no-progress；
- 缺少 buy 前目标属性核验。

这类错误需要 semantic guard 或 task-product matching verifier，现有规则抓不到。

### 5.4 有 benign risk，修复会误伤

task 4 是最关键的负例。baseline 在重复 `click[x-large]` 后下一步 `buy now` 成功；repair 把重复选项判为风险并提示 agent 换动作，结果 agent 点了 `description`，错过购买，最终失败。

因此，风险检测对“观察到重复”是敏感的，但对“重复是否真的需要干预”还不够准。

## 6. 下一步建议

1. 将风险分成 detect 和 intervene 两级：检测到风险不等于立刻干预。
2. post repeated risk 需要加 gate：如果当前页面有 `buy now` 且已选 option，不要简单提示“换动作”，应优先建议 `buy now` 或做 buy 前语义校验。
3. 对 `click[value]` 增加 option completion：从当前 clickables 中补成具体选项，而不是只提示换动作。
4. 对 task 13/14 增加 semantic verifier：检查当前商品/选项是否满足任务约束，尤其是尺寸、颜色、价格。
5. 对失败商品/选项组合加入 negative memory，避免 repair 后回到同一个错误候选。

