# WebShop20 重新运行对照报告

运行时间：2026-06-23

## 运行设置

- 环境：official WebShop text env
- 任务：前 20 条，`start_index=0`，`num_samples=20`
- 模型：`qwen3-8b`
- 最大步数：`max_steps=15`
- 状态泄露：`state_to_agent=false`
- 网络：通过 `./no_proxy_run.sh` 执行项目命令，未走本地代理

## 三组主结果

| 组别 | 成功数 | 成功率 | 平均 reward | 平均 step | action 数 | 说明 |
|---|---:|---:|---:|---:|---:|---|
| baseline | 11/20 | 0.5500 | 0.2717 | 9.05 | 181 | 原始 ReAct，不开 LLM 风险校验 |
| prepost llm verify | 11/20 | 0.5500 | 0.2717 | 9.05 | 181 | shadow 校验，不修复、不改 action |
| hint repair | 12/20 | 0.6000 | 0.2734 | 9.00 | 180 | shadow 校验 + post hint 给下一步 agent |

baseline 与 prepost llm verify 的 20 条 action 序列完全一致，成功率、reward、step 也完全一致。因此这次验证里，纯 shadow LLM 校验没有改变 agent 行为。

hint repair 与 baseline 有 6 条轨迹出现 action 差异，其中 task 7 从失败变为成功；其他 5 条仍失败。

## 轨迹层风险命中

这里把最终失败轨迹视为“应该检测到风险”的正类，把最终成功轨迹视为负类。

| 组别 | TP | FP | FN | TN | 准确率 | 失败轨迹召回 | 成功轨迹误报率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 7 | 1 | 2 | 10 | 0.8500 | 0.7778 | 0.0909 |
| prepost llm verify | 7 | 1 | 2 | 10 | 0.8500 | 0.7778 | 0.0909 |
| hint repair | 6 | 2 | 2 | 10 | 0.8000 | 0.7500 | 0.1667 |

注意：baseline 虽然不开 verifier，但 runner 仍会在轨迹中计算 trajectory-level rule risk；只是不会触发 LLM verifier 调用。

## Action 层 verifier 和修复

| 组别 | pre 规则触发 | post 规则触发 | pre LLM 判错 | post LLM 判错 | hint 创建 | hint 应用 | action 改写 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| prepost llm verify | 3 | 58 | 0 | 58 | 0 | 0 | 0 |
| hint repair | 4 | 11 | 0 | 11 | 11 | 10 | 0 |

pre verifier 这次仍然偏保守：被规则触发后，Qwen 没有把 pre risk 判为 error。post verifier 更激进：被 post 规则触发的样本全部判为 error。

## 离线 pre/post action 审计

这个审计不调用模型，只按可观察效果复核：

- `pre_repeat`：重复同一 action 且已知无新信息。
- `post_no_effect`：把 `post.info_gain=false` 当作 no-effect 预测，再和 `context_before == context_after and done=false and reward=0` 比较。

| 组别 | pre repeat flag | pre repeat FP | post TP/FP/FN/TN | post 准确率 | post FPR |
|---|---:|---:|---|---:|---:|
| baseline | 3 | 0 | 16/16/0/149 | 0.9116 | 0.0970 |
| prepost llm verify | 3 | 0 | 16/16/0/149 | 0.9116 | 0.0970 |
| hint repair | 4 | 0 | 25/49/0/106 | 0.7278 | 0.3161 |

hint repair 的 post action 审计下降，不等于 shadow 本身破坏了准确率；它改变了后续 prompt 和轨迹分布，所以后续页面跳转、返回已访问页面、无新属性页面更多。这里的 post 口径也比较苛刻：`info_gain=false` 是“没有新属性”，不严格等于“动作无效”。

## 文件索引

- baseline 原始轨迹：`logs/rule_shadow_v1_baseline_rerun_webshop20/trajectories.jsonl`
- baseline 状态快照：`logs/rule_shadow_v1_baseline_rerun_webshop20/state_snapshots_compact.jsonl`
- baseline 报告：`reports/rule_shadow_v1_baseline_rerun_webshop20/`
- prepost llm verify 原始轨迹：`logs/rule_shadow_v1_prepost_llmverify_rerun_webshop20/trajectories.jsonl`
- prepost llm verify 状态快照：`logs/rule_shadow_v1_prepost_llmverify_rerun_webshop20/state_snapshots_compact.jsonl`
- prepost llm verify 报告：`reports/rule_shadow_v1_prepost_llmverify_rerun_webshop20/`
- hint repair 原始轨迹：`logs/rule_shadow_v1_hintrepair_rerun_webshop20/trajectories.jsonl`
- hint repair 状态快照：`logs/rule_shadow_v1_hintrepair_rerun_webshop20/state_snapshots_compact.jsonl`
- hint repair 报告：`reports/rule_shadow_v1_hintrepair_rerun_webshop20/`

## 结论

1. 纯 shadow verifier 本身不影响 agent 成功率和轨迹，这次 20/20 action 序列与 baseline 完全一致。
2. hint repair 有小幅成功率提升：11/20 到 12/20，但提升很有限，平均 reward 几乎不变。
3. 当前 post verifier 在被规则触发时仍然过于激进，尤其是把所有 post 触发都判成 error；后续如果做 intervention，需要先做置信度校准，否则误干预风险高。
4. 不同“准确率”不要混用：轨迹层风险命中准确率是 0.85/0.80；离线 action 层 post no-effect 审计是 0.9116/0.7278。
