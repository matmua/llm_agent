# rule-based shadow v1 LLM Risk Verifier WebShop20 报告

本次新增独立 LLM Risk Verifier 模块。

- LLM verifier 只在规则风险触发后调用。
- LLM verifier 不修改 action。
- LLM verifier 不执行修复。
- shadow state 没有注入 agent。
- `repair_hint` 和 `avoid_action` 本次只记录，不使用。
- 不确定一律判为 `is_error=false`。
- verifier 只判断四类错误：evidence_guessing、format_error、loop_or_repetition、wrong_action_or_param。
- verifier 输出只接受五个字段：is_error、error_type、confidence、repair_hint、avoid_action。

## 统计结果

- 样本数：20
- 最大步数：15
- action 数：191
- success：13 / 20 = 0.6500
- llm_risk_verify_enabled：True
- rule_risk_trigger_action_count：47
- llm_called_action_count：47
- llm_parse_error_count：0
- llm_is_error_action_count：47
- llm_error_type_counts：{"evidence_guessing": 0, "format_error": 0, "loop_or_repetition": 47, "wrong_action_or_param": 0, "none": 0}
- rule_risk_sample_count：7
- llm_verified_error_sample_count：7
- failed_samples_with_rule_risk：5 / 7
- failed_samples_with_llm_verified_error：5 / 7
- failed_llm_verified_recall：0.7143
- successful_samples_with_rule_risk：2 / 13
- successful_samples_with_llm_verified_error：2 / 13
- successful_llm_verified_rate：0.1538
- avg_first_rule_risk_step_failed：6.2
- avg_first_llm_verified_error_step_failed：6.2
- state_prompt_leak_count：0
- action_changed_count：0

## 最终检查

- 运行命令：`python -m runners.run_webshop_shadow --env official --num_samples 20 --start_index 0 --max_steps 15 --model qwen3-8b --state_to_agent false --llm_risk_verify --risk_verify_model qwen3-8b --log_dir logs/rule_shadow_v1_llmverify_webshop20 --report_dir reports/rule_shadow_v1_llmverify_webshop20`
- 活跃 verifier 模块：`intervention/risk_verifier.py`。
- 活跃 verifier prompt：`intervention/prompts.py`。
- `state_to_agent=false`，日志中 `state_prompt_leak_count=0`。
- `executed_action == raw_action`，日志中 `action_changed_count=0`。
- `repair_placeholder.enabled=false`，没有触发修复、阻断、回滚或 action 改写。

## risk_verification 示例

### is_error=true

```json
{
  "task_id": 0,
  "step": 4,
  "raw_action": "click[< prev]",
  "post_signal_summary": {
    "visible_delta": false,
    "no_progress": true,
    "no_progress_reason": "context_cycle_without_visible_delta",
    "context_cycle_detected": true,
    "same_action_signature_streak": 1,
    "repeated_behavior_risk": false
  },
  "risk_verification": {
    "enabled": true,
    "triggered": true,
    "called": true,
    "is_error": true,
    "error_type": "loop_or_repetition",
    "confidence": 0.95,
    "repair_hint": "Avoid clicking '< prev>' repeatedly without visible progress.",
    "avoid_action": "click[< prev]",
    "raw_response": "{\n  \"is_error\": true,\n  \"error_type\": \"loop_or_repetition\",\n  \"confidence\": 0.95,\n  \"repair_hint\": \"Avoid clicking '< prev>' repeatedly without visible progress.\",\n  \"avoid_action\": \"click[< prev]\"\n}",
    "parse_error": null
  }
}
```

### is_error=false

```json
{
  "task_id": 0,
  "step": 0,
  "raw_action": "search[double sided machine washable decorative pillows 28x28 printing technology under 50 dollars]",
  "post_signal_summary": {
    "visible_delta": true,
    "no_progress": false,
    "no_progress_reason": null,
    "context_cycle_detected": false,
    "same_action_signature_streak": 1,
    "repeated_behavior_risk": false
  },
  "risk_verification": {
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
}
```
