# rule-based shadow v1 pre/post LLM Risk Verifier WebShop20 报告

本次是 pre/post 双接口 LLM risk verification。

- pre 和 post 规则本身没有改。
- verifier 只在规则风险触发后调用。
- verifier 不修改 action。
- verifier 不执行修复。
- state 没有注入 agent。
- 方案 B 已完成：`is_error=false` 时允许 confidence 为 `[0,1]`。
- verifier 只判断四类错误：evidence_guessing、format_error、loop_or_repetition、wrong_action_or_param。
- verifier 输出只接受五个字段：is_error、error_type、confidence、repair_hint、avoid_action。

## 统计结果

- 样本数：20
- 最大步数：15
- action 数：60
- success：13 / 20 = 0.6500
- llm_risk_verify_enabled：True
- repair_hint_enabled：False
- repair_hint_to_agent：False
- pre_rule_risk_trigger_action_count：0
- post_rule_risk_trigger_action_count：0
- pre_llm_called_action_count：0
- post_llm_called_action_count：0
- pre_llm_parse_error_count：0
- post_llm_parse_error_count：0
- pre_llm_is_error_action_count：0
- post_llm_is_error_action_count：0
- rule_risk_trigger_action_count：0
- llm_called_action_count：0
- llm_parse_error_count：0
- llm_is_error_action_count：0
- llm_error_type_counts：{"evidence_guessing": 0, "format_error": 0, "loop_or_repetition": 0, "wrong_action_or_param": 0, "none": 0}
- rule_risk_sample_count：0
- llm_verified_error_sample_count：0
- failed_samples_with_rule_risk：0 / 7
- failed_samples_with_llm_verified_error：0 / 7
- failed_llm_verified_recall：0.0000
- successful_samples_with_rule_risk：0 / 13
- successful_samples_with_llm_verified_error：0 / 13
- successful_llm_verified_rate：0.0000
- avg_first_rule_risk_step_failed：None
- avg_first_llm_verified_error_step_failed：None
- state_prompt_leak_count：0
- action_changed_count：0

## 最终检查

- 运行命令：`python -m runners.run_webshop_shadow --env official --num_samples 20 --start_index 0 --max_steps 15 --model qwen3-8b --state_to_agent false --llm_risk_verify --risk_verify_model qwen3-8b --repair_hint_enabled false --log_dir logs/rule_shadow_v1_prepost_llmverify_webshop20 --report_dir reports/rule_shadow_v1_prepost_llmverify_webshop20`
- 活跃 verifier 模块：`intervention/risk_verifier.py`。
- 活跃 verifier prompt：`intervention/prompts.py`。
- `state_to_agent=false`，日志中 `state_prompt_leak_count=0`。
- `executed_action == raw_action`，日志中 `action_changed_count=0`。
- `repair_hint_enabled=false`，没有触发修复、阻断、回滚或 action 改写。

## risk_verifications 示例

### pre verification 示例

本次 20 条轨迹没有触发 pre verifier。

### post verification 示例

本次 20 条轨迹没有触发 post verifier。
