# WebShop Shadow Detection Summary

This report is for Phase 1 shadow mode only. The detector logs risk, but it does not alter actions.

## Run Config

- run_id: `20260619_144806_webshop_shadow`
- env: `mock_webshop`
- requested_env: `mock`
- model: `mock`
- num_tasks: `20`
- max_steps: `8`

## Key Metrics

- total_episodes: 20
- total_steps: 60
- success_rate: 1.0000
- avg_reward: 1.0000
- failed_episode_warning_recall: 0.0000
- successful_episode_warning_rate: 0.5000
- post_error_step_rate: 0.0000
- potential_preventable_failure_count: 0

## Risk Categories

Pre-action risk counts:

```json
{
  "missing_attribute": 10,
  "premature_buy": 10,
  "insufficient_evidence": 8
}
```

Post-action error counts:

```json
{}
```

## Pre/Post Correlation

- pre_high_risk_next_step_post_error_rate: 0.0000
- pre_high_risk_before_post_error_episode_count: 0
- avg_first_high_risk_lead_time: 0.0000
- high_risk_and_post_error_same_step_count: 0

## Representative Failed Cases

No failed case with a suspicious action was found.
## Interpretation Guardrail

Shadow mode does not improve success rate by design. Treat these metrics as detection and correlation evidence only.
