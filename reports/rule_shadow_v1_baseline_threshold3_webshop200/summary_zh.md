# rule-based shadow v1 trajrisk WebShop20 报告

本次是 rule-based shadow v1 的 trajectory-level risk 扩展。

- 没有使用 LLM detector。
- 没有把 shadow state 注入 agent prompt。
- 没有执行修复。
- 没有阻断、回滚或 action 改写。
- 没有加入 WebShop 颜色/尺码/option 专用规则。
- 保留 action-level signal：visible_delta、action no_progress、context cycle no_progress。
- 新增 trajectory-level signal：相同 action_signature 连续 3 次触发 repeated_behavior_risk。
- no_progress 是 action-level 局部无进展。
- repeated_behavior_risk 是 trajectory-level 风险，不要求 visible_delta=False。
- pre 仍然只检测格式是否合法、当前 action 是否将成为第 3 次重复无可见变化。
- info_gain 是兼容字段，等价于 visible_delta。

## 统计结果

- 样本数：200
- 最大步数：15
- action 数：1826
- success：129 / 200 = 0.6450
- 平均 reward：0.3458
- 平均步数：9.13
- format_invalid_count：0
- repeat_known_no_info_count：88
- visible_delta_true_count：1153
- visible_delta_false_count：673
- action_no_progress_count：96
- same_action_repeated_no_progress_count：88
- context_cycle_no_progress_count：8
- context_cycle_detected_count：19
- repeated_behavior_risk_action_count：383
- trajectory_risk_sample_count：92
- repeated_behavior_risk_sample_count：83
- failed_samples_with_any_risk：60 / 71
- failed_samples_with_repeated_behavior_risk：52
- successful_samples_with_any_risk：32 / 129
- successful_samples_with_repeated_behavior_risk：31
- failed_risk_recall：0.8451
- successful_risk_rate：0.2481
- info_gain_true_count：1153
- info_gain_false_count：673
- param_known_count：1409
- param_unknown_count：417
- state_prompt_leak_count：0
- action_changed_count：0

## 最终检查

- 运行命令：`python -m runners.run_webshop_shadow --env official --num_samples 20 --start_index 0 --max_steps 15 --model qwen3-8b --state_to_agent false --log_dir logs/rule_shadow_v1_trajrisk_webshop20 --report_dir reports/rule_shadow_v1_trajrisk_webshop20`
- 活跃 shadow 入口：`runners/run_webshop_shadow.py`。
- 活跃 shadow core：`shadow/state.py`, `shadow/parser.py`, `shadow/extractor.py`, `shadow/pre.py`, `shadow/post.py`, `shadow/repair.py`。
- `state_to_agent=false`，日志中 `state_prompt_leak_count=0`。
- `executed_action == raw_action`，日志中 `action_changed_count=0`。
- `shadow_state` 只包含 `attributes` 和 `actions` 两张表。
- `repair.enabled=false`，没有触发修复、阻断、回滚或 action 改写。
- active 逻辑中没有 hidden_state_update、selected_option 或 effect.selected_option。

## action_record 示例

### action-level no_progress

```json
{
  "step": 4,
  "raw": "click[< prev]",
  "raw_action": "click[< prev]",
  "original_parsed_action": {
    "type": "click",
    "params": {
      "target": "< prev"
    },
    "format_valid": true,
    "error": null
  },
  "original_action_signature": "click|target=< prev",
  "type": "click",
  "params": {
    "target": "< prev"
  },
  "parsed_action": {
    "type": "click",
    "params": {
      "target": "< prev"
    },
    "format_valid": true,
    "error": null
  },
  "context_before": "ctx_e2c4c185d5c3",
  "action_signature": "click|target=< prev",
  "param_checks": {
    "target": {
      "value": "< prev",
      "known": true,
      "matched_attr": "text.action_target.prev"
    }
  },
  "pre_check": {
    "format_valid": true,
    "repeat_known_no_info": false
  },
  "risk_verifications": {
    "pre": {
      "enabled": false,
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
      "enabled": false,
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
    "enabled": false,
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
    "post_hint_created": false,
    "post_hint": "",
    "post_hint_apply_to_next_step": false
  },
  "executed_action": "click[< prev]",
  "executed_parsed_action": {
    "type": "click",
    "params": {
      "target": "< prev"
    },
    "format_valid": true,
    "error": null
  },
  "action_changed": false,
  "post_check": {
    "visible_delta": false,
    "info_gain": false,
    "new_attrs": [],
    "same_action_no_visible_delta_count": 2,
    "context_cycle_detected": true,
    "same_action_signature_streak": 1,
    "repeated_behavior_risk": false,
    "repeated_behavior_reason": null,
    "no_progress": true,
    "no_progress_reason": "context_cycle_without_visible_delta",
    "context_before": "ctx_e2c4c185d5c3",
    "context_after": "ctx_e89a6280b34d",
    "context_changed": true,
    "new_context": false
  }
}
```

### trajectory-level repeated_behavior_risk

```json
{
  "step": 3,
  "raw": "click[b08nxthm2w]",
  "raw_action": "click[b08nxthm2w]",
  "original_parsed_action": {
    "type": "click",
    "params": {
      "target": "b08nxthm2w"
    },
    "format_valid": true,
    "error": null
  },
  "original_action_signature": "click|target=b08nxthm2w",
  "type": "click",
  "params": {
    "target": "b08nxthm2w"
  },
  "parsed_action": {
    "type": "click",
    "params": {
      "target": "b08nxthm2w"
    },
    "format_valid": true,
    "error": null
  },
  "context_before": "ctx_8f6f1653b817",
  "action_signature": "click|target=b08nxthm2w",
  "param_checks": {
    "target": {
      "value": "b08nxthm2w",
      "known": true,
      "matched_attr": "entity.b08nxthm2w"
    }
  },
  "pre_check": {
    "format_valid": true,
    "repeat_known_no_info": false
  },
  "risk_verifications": {
    "pre": {
      "enabled": false,
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
      "enabled": false,
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
    "enabled": false,
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
    "post_hint_created": false,
    "post_hint": "",
    "post_hint_apply_to_next_step": false
  },
  "executed_action": "click[b08nxthm2w]",
  "executed_parsed_action": {
    "type": "click",
    "params": {
      "target": "b08nxthm2w"
    },
    "format_valid": true,
    "error": null
  },
  "action_changed": false,
  "post_check": {
    "visible_delta": false,
    "info_gain": false,
    "new_attrs": [],
    "same_action_no_visible_delta_count": 2,
    "context_cycle_detected": false,
    "same_action_signature_streak": 3,
    "repeated_behavior_risk": true,
    "repeated_behavior_reason": "same_action_signature_streak",
    "no_progress": false,
    "no_progress_reason": null,
    "context_before": "ctx_8f6f1653b817",
    "context_after": "ctx_8f6f1653b817",
    "context_changed": false,
    "new_context": false
  }
}
```

### 成功轨迹中的局部 no_progress

```json
{
  "step": 10,
  "raw": "click[x-large]",
  "raw_action": "click[x-large]",
  "original_parsed_action": {
    "type": "click",
    "params": {
      "target": "x-large"
    },
    "format_valid": true,
    "error": null
  },
  "original_action_signature": "click|target=x-large",
  "type": "click",
  "params": {
    "target": "x-large"
  },
  "parsed_action": {
    "type": "click",
    "params": {
      "target": "x-large"
    },
    "format_valid": true,
    "error": null
  },
  "context_before": "ctx_8c2070eb0f4c",
  "action_signature": "click|target=x-large",
  "param_checks": {
    "target": {
      "value": "x-large",
      "known": true,
      "matched_attr": "attr.b09m63b87v.size"
    }
  },
  "pre_check": {
    "format_valid": true,
    "repeat_known_no_info": true
  },
  "risk_verifications": {
    "pre": {
      "enabled": false,
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
      "enabled": false,
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
    "enabled": false,
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
    "post_hint_created": false,
    "post_hint": "",
    "post_hint_apply_to_next_step": false
  },
  "executed_action": "click[x-large]",
  "executed_parsed_action": {
    "type": "click",
    "params": {
      "target": "x-large"
    },
    "format_valid": true,
    "error": null
  },
  "action_changed": false,
  "post_check": {
    "visible_delta": false,
    "info_gain": false,
    "new_attrs": [],
    "same_action_no_visible_delta_count": 3,
    "context_cycle_detected": false,
    "same_action_signature_streak": 3,
    "repeated_behavior_risk": true,
    "repeated_behavior_reason": "same_action_signature_streak",
    "no_progress": true,
    "no_progress_reason": "same_action_repeated_without_visible_delta",
    "context_before": "ctx_8c2070eb0f4c",
    "context_after": "ctx_8c2070eb0f4c",
    "context_changed": false,
    "new_context": false
  }
}
```
