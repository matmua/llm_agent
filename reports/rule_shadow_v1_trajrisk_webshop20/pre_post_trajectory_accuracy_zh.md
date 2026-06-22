# pre/post 与轨迹级风险统计

统计对象：`logs/rule_shadow_v1_trajrisk_webshop20/trajectories.jsonl`

样本数 20，step/action 数 191，成功 13 条，失败 7 条，成功率 0.6500。

## Step 级 pre/post 准确率

这里统计的是 detector 自身的可审计目标，不等于最终任务成功率。

### pre

- `pre.format_valid` 对 parser 的机械准确率：1.0000
- `pre.repeat_known_no_info` 对当前规则真值的准确率：1.0000
- pre repeat flag 数：15
- pre repeat strict TP/FP/FN/TN 不按最终成功定义；当前规则真值完全一致，strict disagreement 为 0
- 用可观察效果审计时，pre repeat TP/FP/FN/TN：6 / 9 / 0 / 176
- pre repeat 可观察误报率 FDR：0.6000

说明：pre 的当前规则是同一 context、同一 action_signature 已经出现过 2 次 `post.info_gain=false`，当前动作会成为第 3 次重复 no-info 时触发。

### post

把 `post.info_gain=false` 当作 no-effect 预测，并用 `observable_no_effect = context_before == context_after and done=false and reward=0` 做启发式标签：

- post no-effect TP/FP/FN/TN：33 / 34 / 0 / 124
- post no-effect observable accuracy：0.8220
- post no-effect FDR：0.5075
- post no-effect FPR：0.2152
- post no-effect FNR：0.0000

说明：这个 post 口径比较苛刻。返回已访问页面、切到已知页面时，`info_gain=false` 可能被算作 FP，因为它没有新属性，但确实发生了导航。

## 轨迹级正确率与误报率

这里用最终失败作为正类：失败轨迹中触发 risk 算 TP，成功轨迹中触发 risk 算 FP。

### pre_repeat_any

- TP/FP/FN/TN：2 / 2 / 5 / 11
- 轨迹级准确率：0.6500
- 信号正确率 precision：0.5000
- 失败覆盖率 recall：0.2857
- 成功轨迹误报率 FPR：0.1538
- 信号误报占比 FDR：0.5000

### post_action_no_progress_any

- TP/FP/FN/TN：2 / 2 / 5 / 11
- 轨迹级准确率：0.6500
- 信号正确率 precision：0.5000
- 失败覆盖率 recall：0.2857
- 成功轨迹误报率 FPR：0.1538
- 信号误报占比 FDR：0.5000

### post_repeated_behavior_any

- TP/FP/FN/TN：4 / 1 / 3 / 12
- 轨迹级准确率：0.8000
- 信号正确率 precision：0.8000
- 失败覆盖率 recall：0.5714
- 成功轨迹误报率 FPR：0.0769
- 信号误报占比 FDR：0.2000

### post_any_risk

- TP/FP/FN/TN：5 / 2 / 2 / 11
- 轨迹级准确率：0.8000
- 信号正确率 precision：0.7143
- 失败覆盖率 recall：0.7143
- 成功轨迹误报率 FPR：0.1538
- 信号误报占比 FDR：0.2857

## Event 级按最终成败粗分

这不是严格 step 真值，只看 signal 是否落在最终失败轨迹里。

- pre_repeat_known_no_info：15 次触发，其中 12 次在失败轨迹，3 次在成功轨迹；按最终失败粗分的信号正确率 0.8000，误报占比 0.2000
- post_no_progress：17 次触发，其中 14 次在失败轨迹，3 次在成功轨迹；按最终失败粗分的信号正确率 0.8235，误报占比 0.1765
- post_repeated_behavior_risk：32 次触发，其中 31 次在失败轨迹，1 次在成功轨迹；按最终失败粗分的信号正确率 0.9688，误报占比 0.0312

## 读数结论

单看 action-level `no_progress`，轨迹召回偏低，只覆盖 2 / 7 条失败轨迹。

新增的 `repeated_behavior_risk` 明显提高了失败覆盖，单独覆盖 4 / 7 条失败轨迹，并且只有 1 条成功轨迹误报。

合并后的 `post_any_risk` 覆盖 5 / 7 条失败轨迹，轨迹级准确率 0.8000；仍漏掉 task 13 / task 14，这两条不是简单重复，而更像语义目标不收敛或错误商品探索。
