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
- action 数：177
- success：16 / 20 = 0.8000
- 平均 reward：0.4285
- 平均步数：8.85
- pre_rule_risk_trigger_action_count：5
- post_rule_risk_trigger_action_count：15
- pre_llm_is_error_action_count：2
- post_llm_is_error_action_count：12
- pre_repair_attempt_count：2
- pre_repair_success_count：2
- pre_repair_fallback_count：0
- post_hint_created_count：12
- post_hint_applied_count：11
- repair_hint_followed_count：9
- repair_hint_ignored_count：2
- action_changed_count：1
- state_prompt_leak_count：0
- repair_hint_prompt_count：11

## 示例

### pre repair 示例

```json
{
  "task_id": 7,
  "step": 13,
  "raw_action": "click[b09npml43m]",
  "executed_action": "click[b09npml43m]",
  "action_changed": false,
  "risk_verifications": {
    "pre": {
      "enabled": true,
      "triggered": true,
      "called": true,
      "is_error": true,
      "error_type": "loop_or_repetition",
      "confidence": 0.95,
      "repair_hint": "Avoid repeating the same action without visible progress.",
      "avoid_action": "click[b09npml43m]",
      "raw_response": "{\"is_error\": true, \"error_type\": \"loop_or_repetition\", \"confidence\": 0.95, \"repair_hint\": \"Avoid repeating the same action without visible progress.\", \"avoid_action\": \"click[b09npml43m]\"}",
      "parse_error": null
    },
    "post": {
      "enabled": true,
      "triggered": true,
      "called": true,
      "is_error": true,
      "error_type": "loop_or_repetition",
      "confidence": 0.95,
      "repair_hint": "Avoid repeatedly clicking the same target without visible progress.",
      "avoid_action": "click[b09npml43m]",
      "raw_response": "{\n  \"is_error\": true,\n  \"error_type\": \"loop_or_repetition\",\n  \"confidence\": 0.95,\n  \"repair_hint\": \"Avoid repeatedly clicking the same target without visible progress.\",\n  \"avoid_action\": \"click[b09npml43m]\"\n}",
      "parse_error": null
    }
  },
  "repair": {
    "enabled": true,
    "hint_applied_from_previous_step": {
      "applied": true,
      "source_step": 12,
      "error_type": "loop_or_repetition",
      "hint": "Risk-control hint for this action:\nThe previous behavior was verified as repeated exploration.\nDo not continue the same action or strategy.\nAvoid repeating this action: click[b09npml43m].\nUse the current observation to choose a concrete useful action that moves toward completing the task.\nIf a suitable candidate or completion action is available, act on it instead of continuing navigation.\nOutput only the action in the required format.",
      "avoid_action": "click[b09npml43m]",
      "followed": false
    },
    "pre_repair_attempted": true,
    "pre_repair_hint": "Risk-control hint for this action:\nThe previous behavior was verified as repeated exploration.\nDo not continue the same action or strategy.\nAvoid repeating this action: click[b09npml43m].\nUse the current observation to choose a concrete useful action that moves toward completing the task.\nOutput only the action in the required format.",
    "pre_repair_original_action": "click[b09npml43m]",
    "pre_repair_repaired_action": "click[b09npml43m]",
    "pre_repair_success": true,
    "pre_repair_failed_reason": null,
    "post_hint_created": true,
    "post_hint": "Risk-control hint for this action:\nThe previous behavior was verified as repeated exploration.\nDo not continue the same action or strategy.\nAvoid repeating this action: click[b09npml43m].\nUse the current observation to choose a concrete useful action that moves toward completing the task.\nIf a suitable candidate or completion action is available, act on it instead of continuing navigation.\nOutput only the action in the required format.",
    "post_hint_apply_to_next_step": true
  }
}
```

### post hint 创建示例

```json
{
  "task_id": 0,
  "step": 3,
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
      "repair_hint": "Consider navigating to a different page or refining the search criteria to avoid repetitive behavior.",
      "avoid_action": "click[next >]",
      "raw_response": "{\n  \"is_error\": true,\n  \"error_type\": \"loop_or_repetition\",\n  \"confidence\": 0.95,\n  \"repair_hint\": \"Consider navigating to a different page or refining the search criteria to avoid repetitive behavior.\",\n  \"avoid_action\": \"click[next >]\"\n}",
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
    "post_hint": "Risk-control hint for this action:\nThe previous behavior was verified as repeated exploration.\nDo not continue the same action or strategy.\nAvoid repeating this action: click[next >].\nUse the current observation to choose a concrete useful action that moves toward completing the task.\nIf a suitable candidate or completion action is available, act on it instead of continuing navigation.\nOutput only the action in the required format.",
    "post_hint_apply_to_next_step": true
  }
}
```

### hint followed/ignored 示例

```json
{
  "task_id": 0,
  "step": 4,
  "raw_action": "click[b07bb1fjv8]",
  "executed_action": "click[b07bb1fjv8]",
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
      "source_step": 3,
      "error_type": "loop_or_repetition",
      "hint": "Risk-control hint for this action:\nThe previous behavior was verified as repeated exploration.\nDo not continue the same action or strategy.\nAvoid repeating this action: click[next >].\nUse the current observation to choose a concrete useful action that moves toward completing the task.\nIf a suitable candidate or completion action is available, act on it instead of continuing navigation.\nOutput only the action in the required format.",
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
