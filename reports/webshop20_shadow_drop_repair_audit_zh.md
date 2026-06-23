# WebShop20 shadow 掉分与 repair 失败审计

审计时间：2026-06-23

## 结论摘要

本轮 shadow 的 55% 不是 LLM verifier 或检测模块直接干预造成的。证据是：

- `rule_shadow_v1_baseline_rerun_webshop20` 与 `rule_shadow_v1_prepost_llmverify_rerun_webshop20` 的 20 条 action 序列完全一致。
- 两组 success/reward/step 完全一致：11/20、平均 reward 0.2717、平均 step 9.05。
- `prepost llm verify` 中 `action_changed_count=0`，`repair_hint_enabled=false`，不会改 action。

真正的 65% -> 55% 掉分来自当前 runner 相对旧版的 prompt 面发生了一个小但真实的改变：`Recent action history` 里新增了 `action_changed: false` 字段。这个字段来自 intervention/repair 记录，但即使在 shadow-only 模式也被写进了 agent prompt。

相关位置：

- 当前 agent prompt 会直接拼接 `Recent action history`：`agents/react_agent.py:83`
- 当前 runner 写入 history 时包含 `action_changed`：`runners/run_webshop_shadow.py:342-350`
- 旧版 runner 的 history 没有该字段：commit `1daac6c` 中 `runners/run_webshop_shadow.py:185-192`

因此，这一轮低 10% 更准确的说法是：不是“检测器判错后影响了 action”，而是 intervention 相关元数据进入了普通 agent history，改变了 Qwen3-8B 的后续解码路径。

## 65% 与 55% 的逐任务差异

旧版 65% 结果包括：

- `logs/rule_shadow_v1_webshop20/trajectories.jsonl`
- `logs/rule_shadow_v1_repeat_webshop20/trajectories.jsonl`
- `logs/rule_shadow_v1_trajrisk_webshop20/trajectories.jsonl`
- `logs/rule_shadow_v1_llmverify_webshop20/trajectories.jsonl`

本轮 55% 结果包括：

- `logs/rule_shadow_v1_baseline_rerun_webshop20/trajectories.jsonl`
- `logs/rule_shadow_v1_prepost_llmverify_rerun_webshop20/trajectories.jsonl`

旧版成功、本轮失败的只有两个任务：

| task | 旧版 reward | 本轮 reward | 差异原因 |
|---:|---:|---:|---|
| 3 | 1.0 | 0.0 | 本轮从 step 1 开始连续翻页，错过第一页可购买目标 |
| 16 | 1.0 | 0.0 | 本轮回到搜索页后多次输出 `click[value]`，没有选到正确商品与选项 |

### Task 3

任务：找 dual band、quad core、低于 340 美元的 streaming media player。

旧版成功轨迹：

```text
search[dual band streaming media players quad core price less than 340]
click[b09lskqf8c]
click[b09lskqf8c]
click[description]
click[back to search]
search[dual band streaming media players quad core price less than 340]
click[next >]
click[next >]
click[b09swlppvq]
click[back to search]
search[dual band streaming media players quad core under 340]
click[b09lskqf8c]
click[buy now]
```

本轮 shadow 失败轨迹：

```text
search[dual band streaming media players quad core price less than 340]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
click[next >]
```

判断：

- 正确商品 `B09LSKQF8C` 在第一页已经出现。
- 旧版 step 1 直接点了 `B09LSKQF8C`，最后回到它并购买。
- 本轮 step 1 选择 `next >`，随后陷入连续翻页。
- shadow verifier 在 step 5 之后确实把 repeated behavior 判为风险，但 shadow-only 不改 action。
- 本轮 baseline 也完全相同，所以不是 verifier 导致失败。

错误原因：agent 决策分支改变，早期没有选择明显候选商品。高概率触发因素是 prompt history 增加了 intervention 元数据字段，而不是检测器本身。

### Task 16

任务：找绿色、xx-large、低于 40 美元的 slim fit/straight leg 男裤。

旧版成功轨迹：

```text
search[slim fit straight leg men's pants elastic waist long sleeve relaxed fit everyday wear color green size xx-large price lower than 40.00 dollars]
click[next >]
click[b09q5zhrvm]
click[back to search]
search[slim fit straight leg men's pants elastic waist long sleeve relaxed fit everyday wear color green size xx-large price lower than 40.00 dollars]
click[b099231v35]
click[green]
click[xx-large]
click[buy now]
```

本轮 shadow 失败轨迹：

```text
search[slim fit straight leg men's pants elastic waist long sleeve relaxed fit everyday wear color green size xx-large price lower than 40.00 dollars]
click[next >]
click[b09q5zhrvm]
click[back to search]
click[value]
click[value]
click[value]
search[slim fit straight leg men's pants elastic waist long sleeve relaxed fit everyday wear green xx-large under 40.00]
click[next >]
click[b09q5zhrvm]
click[value]
click[value]
click[value]
click[back to search]
search[slim fit straight leg men's pants elastic waist long sleeve relaxed fit everyday wear green xx-large under 40.00]
```

判断：

- 旧版在第二次搜索后选择了 `B099231V35`，并正确点了 `green`、`xx-large`、`buy now`。
- 本轮反复回到 `B09Q5ZHRVM`，并多次输出无效/泛化的 `click[value]`。
- shadow 在 step 6、12 检测到 no-progress/repetition，但没有干预。
- 本轮 baseline 与 shadow 相同，所以不是 verifier 干预导致。

错误原因：agent 没有把 option value 具体化为 `green` 或 `xx-large`，而是输出占位式 `value`。这属于 action 生成质量问题；检测器识别到了重复 no-op，但 shadow-only 不会修正。

## repair 为什么只提高 5%

本轮 repair 从 11/20 提到 12/20，只净增 1 条成功，即 +5%。核心原因有四个：

1. repair 不是直接改 action，而是把 hint 放进下一步 prompt；它依赖同一个 Qwen agent 自己理解和执行。
2. post hint 内容过于通用，主要是 “avoid repeating this action / choose a different valid action”，没有给出候选商品、选项名、或者具体下一步。
3. 风险触发偏晚。许多任务在连续翻页 5 次后才触发，已经消耗大量步数。
4. 当前没有 semantic verifier。买错商品、选错 option、点错候选，很多情况下不会触发 repair。

repair 总体计数：

| 指标 | 数值 |
|---|---:|
| success | 12/20 |
| post_hint_created | 11 |
| post_hint_applied | 10 |
| repair_hint_followed | 10 |
| action_changed_count | 0 |
| pre_repair_attempt_count | 0 |

也就是说，agent 基本“形式上遵守”了 hint，但遵守 hint 不等于完成任务。

## repair 未成功任务逐条分析

repair 失败任务共有 8 条：task 0、3、5、13、14、15、16、18。

### Task 0

结果：失败，reward 0，15 step。

行为摘要：

- 先点 `B08K7LDM7Q`，该商品 size 是 `18 x 18-inch`，不符合任务要求的 `28" x 28"`。
- 后续翻页、点另一个商品、回搜，但没有找到并购买正确商品。
- 没有触发任何 hint。

失败原因：

- 这是 semantic mismatch：候选商品属性不满足要求，但当前规则主要看重复、no-progress、format，不会判断“商品属性与任务目标不匹配”。
- 因为没有 risk，被 repair 完全跳过。

### Task 3

结果：失败，reward 0，15 step。

行为摘要：

- step 0-5 连续翻页，step 5 触发 repeated-behavior risk。
- step 6 根据 hint 回到 search。
- step 8 找到 `B09LSKQF8C`，但没有点击 `buy now`；之后回搜、再点同一商品，并在商品页重复 `click[b09lskqf8c]`。
- 最后一步才再次触发 hint，已经没有下一步可以应用。

失败原因：

- repair 成功打断了翻页循环，但没有引导 agent 执行商品页上的关键动作 `click[buy now]`。
- hint 太泛化，只避免了 `next >`，没有利用状态里已经看到的正确候选。

### Task 5

结果：失败，reward 0，15 step。

行为摘要：

- step 0-5 连续翻页，step 5 触发 repeated-behavior risk。
- step 6 根据 hint 回到 search。
- step 8 输出 `click[value]`，这是无效/占位式动作。
- 后续点 `B09QQP3356`、回搜、继续翻页，没有购买。

失败原因：

- hint 只让它停止翻页，但没有给出“从可点击候选中选哪个商品/哪个 option”。
- agent 的 action 生成出现占位符 `value`，当前 repair 没有对这种 action 做强制重写。

### Task 13

结果：失败，reward 0，15 step。

行为摘要：

- 先点 `B09CQ45ZRB`，选择 `19.7x31.5in+19.7x47.2in`，看 description 后回搜。
- step 6-10 连续翻页，step 10 触发 repeated-behavior risk。
- step 11 根据 hint 回到 search。
- step 12 再搜索，step 13 又回到 `B09CQ45ZRB`，step 14 再选同一个错误 size。

失败原因：

- repair 只打断了翻页，没有阻止 agent 回到已失败的商品/选项组合。
- 当前没有“污染实体/属性”的负记忆：`B09CQ45ZRB + 19.7x31.5in+19.7x47.2in` 应该被标记为已验证不匹配，但 repair hint 没有表达这一点。

### Task 14

结果：失败，done=true 但 reward 0，9 step。

行为摘要：

- 最后购买 `B09R8RN6S5`，但 reward 是 0，说明买错。
- 全程没有触发 hint。

失败原因：

- 这是典型的“错误购买”而不是循环/no-progress。
- 当前检测器没有 pre-buy semantic guard：在 `click[buy now]` 前没有核对商品是否满足 leak proof、bpa free、easy clean、5 packs、价格等约束。
- 因为没有风险触发，repair 没机会工作。

### Task 15

结果：失败，reward 0，15 step。

行为摘要：

- step 0-5 连续翻页，触发 hint。
- step 6 回到 search，step 7 重复相同查询。
- step 8-12 再次连续翻页，第二次触发 hint。
- step 13 回到 search，step 14 又重复相同查询。

失败原因：

- repair 只把循环从“翻页”变成“回搜后再次翻页”，没有产生新的搜索策略或候选验证。
- 任务约束很长，agent 没有建立候选筛选计划；hint 不包含任务约束分解。

### Task 16

结果：失败，reward 0，15 step。

行为摘要：

- 先点 `B09Q5ZHRVM` 后回搜。
- step 4-6 反复 `click[value]`，触发 no-progress/repetition。
- step 7 根据 hint 改成重新 search。
- 后续再次点 `B09Q5ZHRVM`，再次反复 `click[value]`，第二次触发 hint。
- 没有回到旧版成功用到的 `B099231V35`，也没有选择 `green`、`xx-large`。

失败原因：

- repair 能发现 `click[value]` 是坏动作，但只能提示“换个动作”，没有把占位符修成具体 option。
- 当前没有 option completion policy：从页面可点击项里选择 `green`、`xx-large` 的能力没有被 repair 模块接管。

### Task 18

结果：失败，reward 0，15 step。

行为摘要：

- step 0-5 连续翻页，触发 hint。
- step 6 回到 search。
- step 9 进入 `B07JVVDJ6L`，step 10 选 `youth`，step 11 选 `xx-large`。
- 但随后点 description、`click[value]`、back to search，没有 buy。

失败原因：

- repair 打断了翻页，并且 agent 找到了某个可配置商品，但没有完成购买。
- 当前 post repair 不会在“已选 option 后但未购买”阶段生成 goal-directed hint，例如“如果商品满足约束并选项已选，点击 buy now”。

## 需要修的方向

1. 先把 agent prompt history 恢复为纯行为历史，不把 `action_changed` 等 intervention 元数据传给 agent。元数据可以保留在日志里，但不要进 prompt。
2. repair hint 要从“避免重复动作”升级为“最小可执行修复动作”。例如：
   - no-op `click[value]`：从当前 clickables 中补全成具体 option。
   - repeated `next >`：推荐回到最近有候选商品的页面或重写 query。
   - buy 前：检查当前商品属性/选项是否满足任务约束，不满足就阻止或提示返回。
3. 增加 semantic guard，尤其是 `click[buy now]` 前的商品-任务匹配校验。
4. 对已验证失败的商品/选项组合加入负记忆，避免 repair 后又回到同一个坑。

