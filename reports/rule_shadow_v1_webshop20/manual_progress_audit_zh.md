# rule-based shadow v1 人工进展标签复核

这份复核是在读取 `logs/rule_shadow_v1_webshop20/trajectories.jsonl` 后做的人工二次标注。

上一份 `pre_post_accuracy_zh.md` 的问题是：把 `context_before != context_after` 视为 observable effect，因此已经访问过的页面来回跳会被当成“有意义”。这对 WebShop 不够准确。

## 人工标签标准

本次把每一步标为：

- `progress`：动作推进了购买流程，或提供了新的可用信息，或完成了必要的隐藏状态选择。
- `no_progress`：动作只是在已知页面之间循环、无效点击、重复点击同一商品/选项、明显错误选项，或返回已知状态而没有产生后续价值。

特别处理：

- 选择颜色/尺码后 observation 可能不变，但如果它是目标选项并服务于后续购买，标为 `progress`。
- 回到已访问页面不自动算 progress；只有它是后续继续搜索/购买的必要过渡时才算 progress。
- 连续翻到新结果页仍算局部信息 progress；它说明 post 的 info-gain 判断没错，但不能说明 agent 策略好。

## 总体结论

人工标注后，191 个 action 中：

- `progress`: 140
- `no_progress`: 51

### pre 检测实际效果

这里把 `pre.repeat_known_no_info=true` 或 `format_valid=false` 当作“预测 no_progress”。

| metric | value |
|---|---:|
| TP | 25 |
| FP | 1 |
| TN | 139 |
| FN | 26 |
| accuracy | 0.8586 |
| precision | 0.9615 |
| recall | 0.4902 |
| false discovery rate | 0.0385 |
| false positive rate | 0.0071 |
| false negative rate | 0.5098 |

解释：pre 很保守，误报很少，但漏报很多。它只抓住了 25/51 个 no_progress action，漏掉 26 个。

唯一明显误报是 task 14 step 8：重复搜索被 pre 标记为 repeat no-info，但这一步回到结果页后继续打开了另一个商品，因此按人工任务进展标签算 progress。

主要漏报类型：

- 第一次进入已知页面循环：task 0 step 2/3。
- 无效或无意义点击：`click[value]`，重复点击当前商品 id。
- 错误选项或重复选项：例如重复点击尺码、点击不匹配的选项。
- 返回已知 search/product 状态但没有产生后续价值。

### post 检测实际效果

这里把 `post.info_gain=false` 当作“预测 no_progress”。

| metric | value |
|---|---:|
| TP | 51 |
| FP | 16 |
| TN | 124 |
| FN | 0 |
| accuracy | 0.9162 |
| precision | 0.7612 |
| recall | 1.0000 |
| false discovery rate | 0.2388 |
| false positive rate | 0.1143 |
| false negative rate | 0.0000 |

解释：post 对 no_progress 的召回很好，这 51 个人工标注 no_progress 都被 `info_gain=false` 覆盖到了。真正的问题是 16 个 false positive：它们没有新可见属性，但实际上推进了任务。

false positive 主要有两类：

1. 隐藏状态变化：选择目标颜色/尺码后 observation 不变，但 WebShop 内部状态变化了。
   - task 4 step 8: `click[x-large]`
   - task 6 step 3: `click[#2 navy]`
   - task 7 step 9: `click[large]`
   - task 9 step 3: `click[xx-large]`
   - task 16 step 6/7: `click[green]`, `click[xx-large]`
   - task 19 step 2/3: `click[black]`, `click[7]`

2. 必要的已知状态跳转：页面内容已经见过，因此没有新属性，但这一步把 agent 带回到可继续购买/搜索的位置。
   - task 3 step 11: `click[b09lskqf8c]`
   - task 4 step 6: repeated search to known results before selecting another product
   - task 7 step 6: repeated search to known results before selecting another product
   - task 13 step 5: repeated search to known results before exploring later pages
   - task 14 step 4/8/11: repeated search / return from detail page used as transition
   - task 16 step 4: repeated search to known results before selecting the successful product

## 逐样例表

`post` 表格里的 TP/FP/TN/FN 以 `info_gain=true` 预测 progress 计算。
`pre` 表格里的 TP/FP/TN/FN 以 pre 预测 no_progress 计算。

| task | success | reward | steps | no_progress | post TP/FP/TN/FN | post_acc | pre TP/FP/TN/FN | pre_acc |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | false | 0.000 | 15 | 13 | 2/0/13/0 | 1.000 | 11/0/2/2 | 0.867 |
| 1 | true | 0.429 | 3 | 0 | 3/0/0/0 | 1.000 | 0/0/3/0 | 1.000 |
| 2 | true | 0.333 | 5 | 2 | 3/0/2/0 | 1.000 | 1/0/3/1 | 0.800 |
| 3 | true | 1.000 | 13 | 4 | 8/0/4/1 | 0.923 | 0/0/9/4 | 0.692 |
| 4 | true | 0.889 | 12 | 4 | 6/0/4/2 | 0.833 | 2/0/8/2 | 0.833 |
| 5 | false | 0.000 | 15 | 0 | 15/0/0/0 | 1.000 | 0/0/15/0 | 1.000 |
| 6 | true | 0.571 | 7 | 3 | 3/0/3/1 | 0.857 | 1/0/4/2 | 0.714 |
| 7 | false | 0.000 | 15 | 8 | 5/0/8/2 | 0.867 | 4/0/7/4 | 0.733 |
| 8 | true | 0.091 | 5 | 0 | 5/0/0/0 | 1.000 | 0/0/5/0 | 1.000 |
| 9 | true | 0.429 | 6 | 1 | 4/0/1/1 | 0.833 | 1/0/5/0 | 1.000 |
| 10 | true | 0.600 | 3 | 0 | 3/0/0/0 | 1.000 | 0/0/3/0 | 1.000 |
| 11 | true | 0.600 | 7 | 4 | 3/0/4/0 | 1.000 | 3/0/3/1 | 0.857 |
| 12 | true | 0.333 | 5 | 0 | 5/0/0/0 | 1.000 | 0/0/5/0 | 1.000 |
| 13 | false | 0.000 | 15 | 7 | 7/0/7/1 | 0.933 | 2/0/8/5 | 0.667 |
| 14 | false | 0.000 | 15 | 4 | 8/0/4/3 | 0.800 | 0/1/10/4 | 0.667 |
| 15 | false | 0.000 | 15 | 0 | 15/0/0/0 | 1.000 | 0/0/15/0 | 1.000 |
| 16 | true | 1.000 | 9 | 1 | 5/0/1/3 | 0.667 | 0/0/8/1 | 0.889 |
| 17 | true | 0.143 | 6 | 0 | 6/0/0/0 | 1.000 | 0/0/6/0 | 1.000 |
| 18 | false | 0.000 | 15 | 0 | 15/0/0/0 | 1.000 | 0/0/15/0 | 1.000 |
| 19 | true | 1.000 | 5 | 0 | 3/0/0/2 | 0.600 | 0/0/5/0 | 1.000 |

## 对旧报告的修正

旧报告里的 post observable FDR 是 0.5075，这个偏高，因为它把“跳到已访问但有用的位置”与“跳到已访问且无用的位置”混在了一起。

按本次人工进展标签，post 的 no_progress false discovery rate 更合理地估计为 0.2388。

pre 的问题则相反：旧报告强调误报不多是对的，但没有突出漏报。人工标签下 pre recall 只有 0.4902，说明当前 pre 只能作为高置信重复 no-info 提示，不能作为完整循环检测器。

## 重要限制

这不是官方 benchmark label，而是基于 20 条轨迹的人工作业级复核。它比纯 context/hash 统计更接近实际任务进展，但仍带有判断成分。

如果要更严格地评估“语义上是否朝正确商品推进”，需要 WebShop 的目标商品/目标属性和内部 selected options 暴露出来。当前日志没有完整保存这些内部标签，所以这里没有把“连续翻新页面但不买”全部标成错误。
