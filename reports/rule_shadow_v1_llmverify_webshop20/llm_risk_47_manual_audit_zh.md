# LLM risk verifier 47 个风险人工核验

数据来源：

- 轨迹：`logs/rule_shadow_v1_llmverify_webshop20/trajectories.jsonl`
- 指标：`reports/rule_shadow_v1_llmverify_webshop20/metrics.json`
- 样本数：20
- LLM risk verifier 被调用并判定 `is_error=true` 的 action 数：47

## 总结

按 action-level risk event 统计：

| 类别 | 数量 | 占比 | 说明 |
| --- | ---: | ---: | --- |
| failure-related risk | 44 | 93.62% | 出现在失败轨迹，且人工看确实应该触发干预或后续修复 |
| benign/recovered risk | 3 | 6.38% | 出现在成功轨迹，局部重复/无效，但最终 agent 自行恢复或仍获得正 reward |
| questionable risk | 0 | 0.00% | 未发现 LLM 判 true 但人工看完全不该干预的事件 |

按 trajectory-level 统计：

| 类别 | 轨迹数 | task_id |
| --- | ---: | --- |
| failure-related risk | 5 | 0, 5, 7, 15, 18 |
| benign/recovered risk | 2 | 4, 11 |
| questionable risk | 0 | 无 |

注意：47 是 action 级事件数，不是 47 条独立轨迹。同一条卡住轨迹会连续贡献多个风险事件。如果 intervention 在第一个可靠风险处生效，后续很多重复风险不会再发生。

## 逐轨迹核验

### task 0：failure-related，11 个风险

- 最终结果：失败，reward=0.0，15 steps 到上限。
- 风险动作：step 4-14。
- 行为模式：在商品 `b08k7ldm7q` 页面和 `< prev>` 搜索页之间反复切换。
- 人工判断：应该干预。
- 理由：从 step 4 开始已经形成两状态循环，后续持续 `click[< prev]` / `click[b08k7ldm7q]`，没有选择符合目标的商品，也没有修改搜索或购买。

### task 4：benign/recovered，1 个风险

- 最终结果：成功，reward=0.8888888888888888，12 steps。
- 风险动作：step 10 `click[x-large]`。
- 行为模式：连续三次点击同一个 size 选项 `x-large`。
- 人工判断：局部动作确实多余，但不属于导致失败的风险。
- replay 核验：
  - 原始轨迹三次 `click[x-large]` 后购买：reward=0.8888888888888888，options=`{"size": "x-large"}`。
  - 只点击一次 `x-large` 后购买：reward 仍为 0.8888888888888888，options 相同。
  - 完全不点 `x-large`：reward 降到 0.7777777777777778，options=`{}`。
  - 如果补选颜色 `xnj-tshirt334-gray` 再选 `x-large`：reward=1.0。
- 结论：第一次 `x-large` 有意义；第三次被标记的重复点击确实多余。它是 benign/recovered，不是 questionable。

### task 5：failure-related，10 个风险

- 最终结果：失败，reward=0.0，15 steps 到上限。
- 风险动作：step 5-14，均为 `click[next >]`。
- 行为模式：搜索后连续翻页，从第 5 次连续 `next >` 开始触发 repeated behavior。
- 人工判断：应该干预。
- 理由：后续一直翻页，没有进入商品、选择属性或购买。尤其 step 5 以后页面继续变化但策略没有变化，最终耗尽 step。
- 备注：step 5 更适合作为“停止继续翻页/触发下一步修复”的 post-action 信号；若做严格 pre-action blocking，step 6 以后证据更强。

### task 7：failure-related，3 个风险

- 最终结果：失败，reward=0.0，15 steps 到上限。
- 风险动作：step 12-14，均为 `click[b09npml43m]`。
- 行为模式：agent 已在商品页，先选了 `b17-wine red` 和 `large`，随后反复点击商品 id `b09npml43m`。
- 人工判断：应该干预。
- 理由：商品页上的重复商品 id 点击没有改变页面、没有增加信息、没有购买；后续一直原地无效重复直到 step 上限。

### task 11：benign/recovered，2 个风险

- 最终结果：成功，reward=0.6，7 steps。
- 风险动作：step 4-5，均为 `click[b09qqp3356]`。
- 行为模式：第一次点击 `b09qqp3356` 进入商品页后，又重复点击同一个商品 id。
- 人工判断：局部动作确实无效，但最终恢复到 `click[buy now]`，因此归为 benign/recovered。
- replay 核验：
  - 原始多次重复后购买：reward=0.6，options=`{}`。
  - 只点击一次商品后直接购买：reward 仍为 0.6，options=`{}`。
  - 商品页后补选 `3x-large` 再购买：reward=0.8。
- 结论：重复商品 id 点击不是隐藏选择，确实多余；但最终仍买到了部分匹配商品，所以不是 failure-related。

### task 15：failure-related，10 个风险

- 最终结果：失败，reward=0.0，15 steps 到上限。
- 风险动作：step 5-14，均为 `click[next >]`。
- 行为模式：搜索后连续翻页，没有进入商品详情、选择属性或购买。
- 人工判断：应该干预。
- 理由：与 task 5 类似，页面虽然变化，但策略层面没有朝任务完成推进，最终耗尽 step。

### task 18：failure-related，10 个风险

- 最终结果：失败，reward=0.0，15 steps 到上限。
- 风险动作：step 5-14，均为 `click[next >]`。
- 行为模式：搜索后连续翻页，没有进入商品详情、选择属性或购买。
- 人工判断：应该干预。
- 理由：与 task 5/task 15 同类，属于页面变化掩盖下的策略停滞。

## 对 intervention 的含义

这 47 个风险里没有发现“完全不该干预”的 questionable risk，但有 3 个成功轨迹中的 benign/recovered risk。它们说明：

1. 对失败轨迹中的循环/重复，干预方向是合理的。
2. 对成功轨迹中的局部重复，不应直接判整条任务失败；更适合做轻量修复，例如跳过重复动作、提示选择缺失属性、或降低重复动作优先级。
3. 对连续翻页类风险，第一次触发时应视为 post-action warning；如果下一步仍然继续同类动作，再升级为强干预。

