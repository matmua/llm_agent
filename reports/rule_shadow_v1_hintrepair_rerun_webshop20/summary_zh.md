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
- action 数：180
- success：12 / 20 = 0.6000
- 平均 reward：0.2734
- 平均步数：9.00
- pre_rule_risk_trigger_action_count：4
- post_rule_risk_trigger_action_count：11
- pre_llm_is_error_action_count：0
- post_llm_is_error_action_count：11
- pre_repair_attempt_count：0
- pre_repair_success_count：0
- pre_repair_fallback_count：0
- post_hint_created_count：11
- post_hint_applied_count：10
- repair_hint_followed_count：10
- repair_hint_ignored_count：0
- action_changed_count：0
- state_prompt_leak_count：0
- repair_hint_prompt_count：10

## 示例

### pre repair 示例

本次没有出现该类事件。

### post hint 创建示例

```json
{
  "task_id": 3,
  "step": 5,
  "raw_action": "click[next >]",
  "executed_action": "click[next >]",
  "action_changed": false,
  "risk_verifications": {
    "pre": {
      "enabled": true,
      "triggered": false,
      "called": false,
      "is_error": false,
      "error_type": "none",
      "confidence": 0.0,
      "repair_hint": "",
      "avoid_action": null,
      "raw_response": null,
      "parse_error": null
    },
    "post": {
      "enabled": true,
      "triggered": true,
      "called": true,
      "is_error": true,
      "error_type": "loop_or_repetition",
      "confidence": 0.95,
      "repair_hint": "Consider changing the action to navigate to a different page or refine the search query.",
      "avoid_action": "click[next >]",
      "raw_response": "{\n  \"is_error\": true,\n  \"error_type\": \"loop_or_repetition\",\n  \"confidence\": 0.95,\n  \"repair_hint\": \"Consider changing the action to navigate to a different page or refine the search query.\",\n  \"avoid_action\": \"click[next >]\"\n}",
      "parse_error": null
    }
  },
  "repair": {
    "enabled": true,
    "hint_applied_from_previous_step": {
      "applied": false,
      "source_step": null,
      "error_type": null,
      "hint": "",
      "avoid_action": null,
      "followed": null
    },
    "pre_repair_attempted": false,
    "pre_repair_hint": "",
    "pre_repair_original_action": null,
    "pre_repair_repaired_action": null,
    "pre_repair_success": false,
    "pre_repair_failed_reason": null,
    "post_hint_created": true,
    "post_hint": "[Risk-control hint for the next action only]\nA repeated-behavior risk was verified.\nAvoid repeating this action: click[next >].\nChoose a different valid action based on the current observation.\nOutput only the action in the required format.",
    "post_hint_apply_to_next_step": true
  }
}
```

### hint followed/ignored 示例

```json
{
  "task_id": 3,
  "step": 6,
  "raw_action": "click[back to search]",
  "executed_action": "click[back to search]",
  "action_changed": false,
  "risk_verifications": {
    "pre": {
      "enabled": true,
      "triggered": false,
      "called": false,
      "is_error": false,
      "error_type": "none",
      "confidence": 0.0,
      "repair_hint": "",
      "avoid_action": null,
      "raw_response": null,
      "parse_error": null
    },
    "post": {
      "enabled": true,
      "triggered": false,
      "called": false,
      "is_error": false,
      "error_type": "none",
      "confidence": 0.0,
      "repair_hint": "",
      "avoid_action": null,
      "raw_response": null,
      "parse_error": null
    }
  },
  "repair": {
    "enabled": true,
    "hint_applied_from_previous_step": {
      "applied": true,
      "source_step": 5,
      "error_type": "loop_or_repetition",
      "hint": "[Risk-control hint for the next action only]\nA repeated-behavior risk was verified.\nAvoid repeating this action: click[next >].\nChoose a different valid action based on the current observation.\nOutput only the action in the required format.",
      "avoid_action": "click[next >]",
      "followed": true
    },
    "pre_repair_attempted": false,
    "pre_repair_hint": "",
    "pre_repair_original_action": null,
    "pre_repair_repaired_action": null,
    "pre_repair_success": false,
    "pre_repair_failed_reason": null,
    "post_hint_created": false,
    "post_hint": "",
    "post_hint_apply_to_next_step": false
  }
}
```
