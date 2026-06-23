# rule-based shadow v1 lightweight repair hint WebShop20 报告

本次是轻量 repair hint 模式。

- pre verified error 会尝试当前 step 重新生成一次 action。
- post verified error 会创建下一步一次性 repair hint。
- 不做回滚。
- 不做多轮重试。
- 不把完整 state 给 agent。
- `state_to_agent=false`，但 `repair_hint_to_agent=true`。

## 统计结果

- 样本数：20
- 最大步数：15
- action 数：60
- success：13 / 20 = 0.6500
- 平均 reward：0.2662
- 平均步数：3.00
- pre_rule_risk_trigger_action_count：0
- post_rule_risk_trigger_action_count：0
- pre_llm_is_error_action_count：0
- post_llm_is_error_action_count：0
- pre_repair_attempt_count：0
- pre_repair_success_count：0
- pre_repair_fallback_count：0
- post_hint_created_count：0
- post_hint_applied_count：0
- repair_hint_followed_count：0
- repair_hint_ignored_count：0
- action_changed_count：0
- state_prompt_leak_count：0
- repair_hint_prompt_count：0

## 示例

### pre repair 示例

本次没有出现该类事件。

### post hint 创建示例

本次没有出现该类事件。

### hint followed/ignored 示例

本次没有出现该类事件。
