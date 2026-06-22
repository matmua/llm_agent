# rule-based shadow v1 repeat WebShop20 报告

本次是 rule-based shadow v1 的通用重复/循环无进展检测版本。

- 没有使用 LLM detector。
- 没有使用 LLM state proposer。
- 没有把 shadow state 注入 agent prompt。
- 没有执行修复、阻断、回滚或 action 改写。
- 没有加入 WebShop 颜色/尺码/option 专用规则。
- pre 只检测格式是否合法、当前 action 是否将成为第 3 次重复无可见变化。
- post 将 visible_delta 和 no_progress 分离。
- visible_delta=False 不直接等于 no_progress。
- no_progress 只由 same action + same params 第 3 次无可见变化，或 context A-B-A-B 循环且无可见变化触发。
- info_gain 是兼容字段，等价于 visible_delta，不再等价于 no_progress。

## 统计结果

- 样本数：20
- 最大步数：15
- action 数：191
- success：13 / 20 = 0.6500
- 平均 reward：0.3709
- 平均步数：9.55
- format_invalid_count：0
- repeat_known_no_info_count：15
- visible_delta_true_count：124
- visible_delta_false_count：67
- no_progress_count：17
- same_action_repeated_no_progress_count：15
- context_cycle_no_progress_count：2
- context_cycle_detected_count：11
- info_gain_true_count：124
- info_gain_false_count：67
- param_known_count：158
- param_unknown_count：33
- state_prompt_leak_count：0
- action_changed_count：0

## 最终检查

- 运行命令：`python -m runners.run_webshop_shadow --env official --num_samples 20 --start_index 0 --max_steps 15 --model qwen3-8b --state_to_agent false --log_dir logs/rule_shadow_v1_repeat_webshop20 --report_dir reports/rule_shadow_v1_repeat_webshop20`
- 活跃 shadow 入口：`runners/run_webshop_shadow.py`。
- 活跃 shadow core：`shadow/state.py`, `shadow/parser.py`, `shadow/extractor.py`, `shadow/pre.py`, `shadow/post.py`, `shadow/repair.py`。
- 已删除旧目录：`detectors/`, `state/`, `analysis/` 以及对应旧测试。
- `state_to_agent=false`，日志中 `state_prompt_leak_count=0`。
- `executed_action == raw_action`，日志中 `action_changed_count=0`。
- `shadow_state` 只包含 `attributes` 和 `actions` 两张表。
- `repair_placeholder.enabled=false`，没有触发修复、阻断、回滚或 action 改写。
- active 逻辑中没有 hidden_state_update、selected_option 或 effect.selected_option。

## action_record 示例

### visible_delta=False 但 no_progress=False

```json
{
  "step": 2,
  "raw": "click[< prev]",
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
  "repair_placeholder": {
    "enabled": false,
    "decision": null,
    "new_action": null
  },
  "executed_action": "click[< prev]",
  "post_check": {
    "visible_delta": false,
    "info_gain": false,
    "new_attrs": [],
    "same_action_no_visible_delta_count": 1,
    "context_cycle_detected": false,
    "no_progress": false,
    "no_progress_reason": null,
    "context_before": "ctx_e2c4c185d5c3",
    "context_after": "ctx_e89a6280b34d",
    "context_changed": true,
    "new_context": false
  }
}
```

### context_cycle_without_visible_delta

```json
{
  "step": 4,
  "raw": "click[< prev]",
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
  "repair_placeholder": {
    "enabled": false,
    "decision": null,
    "new_action": null
  },
  "executed_action": "click[< prev]",
  "post_check": {
    "visible_delta": false,
    "info_gain": false,
    "new_attrs": [],
    "same_action_no_visible_delta_count": 2,
    "context_cycle_detected": true,
    "no_progress": true,
    "no_progress_reason": "context_cycle_without_visible_delta",
    "context_before": "ctx_e2c4c185d5c3",
    "context_after": "ctx_e89a6280b34d",
    "context_changed": true,
    "new_context": false
  }
}
```

### same_action_repeated_without_visible_delta

```json
{
  "step": 6,
  "raw": "click[< prev]",
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
    "repeat_known_no_info": true
  },
  "repair_placeholder": {
    "enabled": false,
    "decision": null,
    "new_action": null
  },
  "executed_action": "click[< prev]",
  "post_check": {
    "visible_delta": false,
    "info_gain": false,
    "new_attrs": [],
    "same_action_no_visible_delta_count": 3,
    "context_cycle_detected": true,
    "no_progress": true,
    "no_progress_reason": "same_action_repeated_without_visible_delta",
    "context_before": "ctx_e2c4c185d5c3",
    "context_after": "ctx_e89a6280b34d",
    "context_changed": true,
    "new_context": false
  }
}
```
