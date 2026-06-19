# WebShop Shadow Detection Summary

This report is for Phase 1 shadow mode only. The detector logs risk, but it does not alter actions.

## Run Config

- run_id: `20260619_172708_webshop_shadow`
- env: `mock_webshop`
- requested_env: `mock`
- model: `mock`
- num_tasks: `3`
- max_steps: `6`

## Key Metrics

- total_episodes: 3
- total_steps: 9
- success_rate: 1.0000
- avg_reward: 1.0000
- pre_warning_step_rate: 0.2222
- pre_high_risk_step_rate: 0.0000
- failed_episode_pre_warning_recall: 0.0000
- successful_episode_pre_warning_rate: 0.6667
- post_error_step_rate: 0.0000
- failed_episode_post_error_recall: 0.0000
- explicit_conflict_count: 0
- missing_evidence_count: 0
- preventable_failure_count: 0
- llm_state_parse_success_rate: 1.0000
- fallback_rate: 0.0000

## Risk Categories

Pre-action risk counts:

```json
{
  "insufficient_evidence": 2
}
```

Post-action error counts:

```json
{}
```

## Pre/Post Correlation

- pre_warning_before_post_error_rate: 0.0000
- avg_lead_time_pre_to_post: 0.0000
- post_error_after_high_risk_rate: 0.0000
- pre_high_risk_next_step_post_error_rate: 0.0000
- pre_high_risk_before_post_error_episode_count: 0
- avg_first_high_risk_lead_time: 0.0000
- high_risk_and_post_error_same_step_count: 0

## State Proposal Quality

- avg_entities_per_step: 4.3333
- avg_constraints_per_step: 3.6667
- conflicts_per_episode: 7.3333
- unsupported_high_confidence_update_count: 0

## Representative Failed Cases

No failed case with a suspicious action was found.
## Interpretation Guardrail

Shadow mode does not improve success rate by design. Treat these metrics as detection and correlation evidence only.
The detector may produce missing_evidence warnings that are not counted as hard post_action errors.
