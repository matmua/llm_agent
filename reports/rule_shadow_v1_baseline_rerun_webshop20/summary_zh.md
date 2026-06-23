# rule-based shadow v1 trajrisk WebShop20 报告

本次是 rule-based shadow v1 的 trajectory-level risk 扩展。

- 没有使用 LLM detector。
- 没有把 shadow state 注入 agent prompt。
- 没有执行修复。
- 没有阻断、回滚或 action 改写。
- 没有加入 WebShop 颜色/尺码/option 专用规则。
- 保留 action-level signal：visible_delta、action no_progress、context cycle no_progress。
- 新增 trajectory-level signal：相同 action_signature 连续 5 次触发 repeated_behavior_risk。
- no_progress 是 action-level 局部无进展。
- repeated_behavior_risk 是 trajectory-level 风险，不要求 visible_delta=False。
- pre 仍然只检测格式是否合法、当前 action 是否将成为第 3 次重复无可见变化。
- info_gain 是兼容字段，等价于 visible_delta。

## 统计结果

- 样本数：20
- 最大步数：15
- action 数：181
- success：11 / 20 = 0.5500
- 平均 reward：0.2717
- 平均步数：9.05
- format_invalid_count：0
- repeat_known_no_info_count：3
- visible_delta_true_count：149
- visible_delta_false_count：32
- action_no_progress_count：3
- same_action_repeated_no_progress_count：3
- context_cycle_no_progress_count：0
- context_cycle_detected_count：0
- repeated_behavior_risk_action_count：55
- trajectory_risk_sample_count：8
- repeated_behavior_risk_sample_count：6
- failed_samples_with_any_risk：7 / 9
- failed_samples_with_repeated_behavior_risk：6
- successful_samples_with_any_risk：1 / 11
- successful_samples_with_repeated_behavior_risk：0
- failed_risk_recall：0.7778
- successful_risk_rate：0.0909
- info_gain_true_count：149
- info_gain_false_count：32
- param_known_count：144
- param_unknown_count：37
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
  "step": 6,
  "raw": "click[value]",
  "raw_action": "click[value]",
  "original_parsed_action": {
    "type": "click",
    "params": {
      "target": "value"
    },
    "format_valid": true,
    "error": null
  },
  "original_action_signature": "click|target=value",
  "type": "click",
  "params": {
    "target": "value"
  },
  "parsed_action": {
    "type": "click",
    "params": {
      "target": "value"
    },
    "format_valid": true,
    "error": null
  },
  "context_before": "ctx_afec81ece3d3",
  "action_signature": "click|target=value",
  "param_checks": {
    "target": {
      "value": "value",
      "known": false,
      "matched_attr": null
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
  "executed_action": "click[value]",
  "executed_parsed_action": {
    "type": "click",
    "params": {
      "target": "value"
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
    "repeated_behavior_risk": false,
    "repeated_behavior_reason": null,
    "no_progress": true,
    "no_progress_reason": "same_action_repeated_without_visible_delta",
    "context_before": "ctx_afec81ece3d3",
    "context_after": "ctx_afec81ece3d3",
    "context_changed": false,
    "new_context": false
  }
}
```

### trajectory-level repeated_behavior_risk

```json
{
  "step": 5,
  "raw": "click[next >]",
  "raw_action": "click[next >]",
  "original_parsed_action": {
    "type": "click",
    "params": {
      "target": "next >"
    },
    "format_valid": true,
    "error": null
  },
  "original_action_signature": "click|target=next >",
  "type": "click",
  "params": {
    "target": "next >"
  },
  "parsed_action": {
    "type": "click",
    "params": {
      "target": "next >"
    },
    "format_valid": true,
    "error": null
  },
  "context_before": "ctx_1d283aa8dbd7",
  "action_signature": "click|target=next >",
  "param_checks": {
    "target": {
      "value": "next >",
      "known": true,
      "matched_attr": "text.action_target.next"
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
  "executed_action": "click[next >]",
  "executed_parsed_action": {
    "type": "click",
    "params": {
      "target": "next >"
    },
    "format_valid": true,
    "error": null
  },
  "action_changed": false,
  "post_check": {
    "visible_delta": true,
    "info_gain": true,
    "new_attrs": [
      {
        "key": "context.current",
        "value": "ctx_f8709b6af463"
      },
      {
        "key": "text.observation.f8709b6af4",
        "value": "Instruction: | Find me dual band streaming media players with quad core, and price lower than 340.00 dollars | Back to Search | Page 6 (Total results: 50) | < Prev | Next >"
      },
      {
        "key": "entity.item_7858841d",
        "value": "item_7858841d"
      },
      {
        "key": "attr.item_7858841d.title",
        "value": "Page 6 (Total results: 50)"
      }
    ],
    "same_action_no_visible_delta_count": 0,
    "context_cycle_detected": false,
    "same_action_signature_streak": 5,
    "repeated_behavior_risk": true,
    "repeated_behavior_reason": "same_action_signature_streak",
    "no_progress": fal
```

### 成功轨迹中的局部 no_progress

```json
{
  "step": 6,
  "raw": "click[value]",
  "raw_action": "click[value]",
  "original_parsed_action": {
    "type": "click",
    "params": {
      "target": "value"
    },
    "format_valid": true,
    "error": null
  },
  "original_action_signature": "click|target=value",
  "type": "click",
  "params": {
    "target": "value"
  },
  "parsed_action": {
    "type": "click",
    "params": {
      "target": "value"
    },
    "format_valid": true,
    "error": null
  },
  "context_before": "ctx_afec81ece3d3",
  "action_signature": "click|target=value",
  "param_checks": {
    "target": {
      "value": "value",
      "known": false,
      "matched_attr": null
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
  "executed_action": "click[value]",
  "executed_parsed_action": {
    "type": "click",
    "params": {
      "target": "value"
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
    "repeated_behavior_risk": false,
    "repeated_behavior_reason": null,
    "no_progress": true,
    "no_progress_reason": "same_action_repeated_without_visible_delta",
    "context_before": "ctx_afec81ece3d3",
    "context_after": "ctx_afec81ece3d3",
    "context_changed": false,
    "new_context": false
  }
}
```
