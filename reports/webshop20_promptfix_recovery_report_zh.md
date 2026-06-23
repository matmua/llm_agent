# WebShop20 prompt 恢复修复报告

运行时间：2026-06-23

## 修复内容

这次只做恢复性修复：把 agent prompt 中泄漏的内部字段移除，恢复旧版 agent-visible history。

修改点：

- `agents/react_agent.py`
  - 在拼接 `Recent action history` 前做白名单过滤。
  - agent-visible history 只保留 `step`、`raw_action`、`executed_action`、`reward`、`done`。
  - 增加 `prompt_sha256` 到 `last_trace`，只用于日志审计，不进入 prompt。
- `runners/run_webshop_shadow.py`
  - 传给 agent 的 `history` 去掉 `action_changed`。
  - step 日志新增 `agent_prompt_sha256`，只用于验证 prompt 是否一致。
  - `action_record` 中仍保留 `action_changed`、`pre_check`、`post_check`、`risk_verifications`、`repair` 等完整 shadow 日志字段。
- `intervention/repair_hint.py`
  - repair hint 可见文本改为普通自然语言块：`Risk-control hint for this action:`。
  - 不把 `repair_hint`、`error_type`、`confidence`、`risk_verifications` 等结构化字段暴露给 agent。
- `tests/test_rule_shadow_v1.py`、`tests/test_repair_hint.py`
  - 新增 prompt history 白名单测试。
  - 新增 baseline 与 verify-only prompt 一致性测试。
  - 新增 repair hint 只作为普通文本块出现的测试。

## Agent-visible prompt 结构

当前 agent 每步看到的 prompt 结构是：

```text
Task instruction:
{任务目标}

Observation:
{当前 WebShop 页面文本}

Available actions:
has_search_bar: true/false
clickables: [...]

{可选：state summary，目前 state_to_agent=false 时不存在}

{可选：repair hint，只有 repair 模式触发时才存在}

Recent action history:
{最近 6 步 agent-visible history}

Output exactly one line in one of these forms:
Action: search[keywords]
Action: click[value]
```

## Recent action history 白名单

agent-visible history 现在只包含：

```python
{
    "step": step,
    "raw_action": raw_action,
    "executed_action": executed_action,
    "reward": reward,
    "done": done,
}
```

以下字段只允许出现在日志中，不进入 prompt：

- `action_changed`
- `pre_check`
- `post_check`
- `risk_verification`
- `risk_verifications`
- `repair`
- `repair_hint`
- `repair_hint_created`
- `repair_hint_applied`
- `visible_delta`
- `no_progress`
- `repeated_behavior_risk`
- `confidence`
- `is_error`

## Repair hint 进入方式

repair 模式下，hint 只作为普通文本块插入 prompt：

```text
Risk-control hint for this action:
The previous behavior was verified as repetitive. Avoid repeating click[next >]. Choose a different valid action based on the current observation.
```

它不是 JSON，不是 history 字段，也不会暴露 verifier 的结构化输出。

## 测试

单元测试：

```text
21 passed
```

## WebShop20 重跑结果

三组均使用：

- `env=official`
- `num_samples=20`
- `start_index=0`
- `max_steps=15`
- `model=qwen3-8b`
- `state_to_agent=false`

| 组别 | 成功数 | 成功率 | 平均 reward | 平均 step | action 数 | state_to_agent | repair hint prompt |
|---|---:|---:|---:|---:|---:|:---:|---:|
| baseline | 13/20 | 0.6500 | 0.3709 | 9.55 | 191 | false | 0 |
| verify-only | 13/20 | 0.6500 | 0.3709 | 9.55 | 191 | false | 0 |
| hint repair | 13/20 | 0.6500 | 0.3698 | 9.60 | 192 | false | 8 |

## Baseline vs verify-only 一致性

修复后，baseline 与 verify-only：

- action 序列一致：20/20
- prompt hash 序列一致：20/20
- success/reward/steps 一致：20/20
- `action_changed_count=0`
- `state_prompt_leak_count=0`
- `repair_hint_prompt_count=0`

这说明 verify-only 模式没有改变 agent-visible prompt，也没有改变轨迹。

## Artifact 索引

- baseline 轨迹：`logs/rule_shadow_v1_baseline_promptfix_webshop20/trajectories.jsonl`
- baseline 报告：`reports/rule_shadow_v1_baseline_promptfix_webshop20/`
- verify-only 轨迹：`logs/rule_shadow_v1_prepost_llmverify_promptfix_webshop20/trajectories.jsonl`
- verify-only 报告：`reports/rule_shadow_v1_prepost_llmverify_promptfix_webshop20/`
- hint repair 轨迹：`logs/rule_shadow_v1_hintrepair_promptfix_webshop20/trajectories.jsonl`
- hint repair 报告：`reports/rule_shadow_v1_hintrepair_promptfix_webshop20/`

## 结论

本次恢复性修复成功：baseline 和 verify-only 从上一轮的 11/20 恢复到 13/20，并且二者 prompt/action/outcome 完全一致。内部 shadow/verifier/repair 字段仍完整记录在日志里，但不再泄漏进 agent prompt。
