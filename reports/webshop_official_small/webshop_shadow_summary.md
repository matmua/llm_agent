# WebShop Shadow Detection Summary

This report is for Phase 1 shadow mode only. The detector logs risk, but it does not alter actions.

## Run Config

- run_id: `20260619_144740_webshop_shadow`
- env: `OfficialWebShopEnv`
- requested_env: `official`
- model: `mock`
- num_tasks: `20`
- max_steps: `8`

## Key Metrics

- total_episodes: 20
- total_steps: 60
- success_rate: 0.6500
- avg_reward: 0.2662
- failed_episode_warning_recall: 0.7143
- successful_episode_warning_rate: 0.8462
- post_error_step_rate: 0.2500
- potential_preventable_failure_count: 5

## Risk Categories

Pre-action risk counts:

```json
{
  "missing_attribute": 16,
  "premature_buy": 16,
  "insufficient_evidence": 4
}
```

Post-action error counts:

```json
{
  "constraint_conflict": 10,
  "potential_preventable_failure": 5
}
```

## Pre/Post Correlation

- pre_high_risk_next_step_post_error_rate: 0.0000
- pre_high_risk_before_post_error_episode_count: 3
- avg_first_high_risk_lead_time: 0.0000
- high_risk_and_post_error_same_step_count: 5

## Representative Failed Cases

### Task 0

- instruction: Instruction: Find me double sided, machine washable decorative pillows with printing technology with size: 28" x 28", and price lower than 30.00 dollars
- first suspicious action: none detected; excerpt starts at step 0
- pre-action reason: No rule-based risk detected.
- post-action reason: No post-action delta error detected.
- Phase 2 opportunity: The case is useful as a baseline trajectory for future intervention comparison.

```json
[
  {
    "step_id": 0,
    "raw_action": "search[double sided machine washable]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 1,
    "raw_action": "click[b096mm7xm4]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 2,
    "raw_action": "click[buy now]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": true
  }
]
```

### Task 13

- instruction: Instruction: Find me home office furniture sets for dining room, living room with color: blue | gray, and item shape: runner, and size: 21 in x 35 in, and price lower than 70.00 dollars
- first suspicious action: step 0 `search[home office furniture sets]`
- pre-action reason: No rule-based risk detected.
- post-action reason: categories=['constraint_conflict']
- Phase 2 opportunity: Post-action repair or rollback could respond after a no-effect or unexpected transition.

```json
[
  {
    "step_id": 0,
    "raw_action": "search[home office furniture sets]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": true,
    "post_categories": [
      "constraint_conflict"
    ],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 1,
    "raw_action": "click[b09688c4xm]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": true,
    "post_categories": [
      "constraint_conflict"
    ],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 2,
    "raw_action": "click[buy now]",
    "pre_risk_level": "high",
    "pre_categories": [
      "missing_attribute",
      "premature_buy"
    ],
    "post_error": true,
    "post_categories": [
      "potential_preventable_failure"
    ],
    "reward": 0.0,
    "done": true
  }
]
```

### Task 15

- instruction: Instruction: Find me machine wash men's dress shirts with polyester heathers, heathers cotton, cotton heather, needle sleeve, classic fit with color: purple, and fit type: men, and size: large, and price lower than 50.00 dollars
- first suspicious action: step 2 `click[buy now]`
- pre-action reason: categories=['missing_attribute', 'premature_buy', 'insufficient_evidence']; missing=['size_constraint']; unsupported=['fine_grained_attributes_not_verified']
- post-action reason: categories=['potential_preventable_failure']
- Phase 2 opportunity: Attribute completion could verify missing constraints before executing the risky action.

```json
[
  {
    "step_id": 0,
    "raw_action": "search[machine wash men dress]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 1,
    "raw_action": "click[b09nd8p2qr]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 2,
    "raw_action": "click[buy now]",
    "pre_risk_level": "high",
    "pre_categories": [
      "missing_attribute",
      "premature_buy",
      "insufficient_evidence"
    ],
    "post_error": true,
    "post_categories": [
      "potential_preventable_failure"
    ],
    "reward": 0.0,
    "done": true
  }
]
```

### Task 16

- instruction: Instruction: Find me slim fit, straight leg men's pants with elastic waist, long sleeve, relaxed fit for everyday wear with color: green, and size: xx-large, and price lower than 50.00 dollars
- first suspicious action: step 0 `search[slim fit straight leg]`
- pre-action reason: No rule-based risk detected.
- post-action reason: categories=['constraint_conflict']
- Phase 2 opportunity: Post-action repair or rollback could respond after a no-effect or unexpected transition.

```json
[
  {
    "step_id": 0,
    "raw_action": "search[slim fit straight leg]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": true,
    "post_categories": [
      "constraint_conflict"
    ],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 1,
    "raw_action": "click[b01msp2b0i]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": true,
    "post_categories": [
      "constraint_conflict"
    ],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 2,
    "raw_action": "click[buy now]",
    "pre_risk_level": "high",
    "pre_categories": [
      "missing_attribute",
      "premature_buy"
    ],
    "post_error": true,
    "post_categories": [
      "potential_preventable_failure"
    ],
    "reward": 0.0,
    "done": true
  }
]
```

### Task 17

- instruction: Instruction: Find me machine wash, wash cold women's fashion hoodies & sweatshirts for dry clean, tumble dry with color: heather grey, and size: large, and price lower than 60.00 dollars
- first suspicious action: step 2 `click[buy now]`
- pre-action reason: categories=['missing_attribute', 'premature_buy']; missing=['color_constraint', 'size_constraint']
- post-action reason: categories=['potential_preventable_failure']
- Phase 2 opportunity: Attribute completion could verify missing constraints before executing the risky action.

```json
[
  {
    "step_id": 0,
    "raw_action": "search[machine wash wash cold]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 1,
    "raw_action": "click[b09m63b87v]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 2,
    "raw_action": "click[buy now]",
    "pre_risk_level": "high",
    "pre_categories": [
      "missing_attribute",
      "premature_buy"
    ],
    "post_error": true,
    "post_categories": [
      "potential_preventable_failure"
    ],
    "reward": 0.0,
    "done": true
  }
]
```

### Task 18

- instruction: Instruction: Find me machine wash men's dress shirts with polyester heathers, heathers cotton, cotton heather, needle sleeve, classic fit with color: red, and fit type: youth, and size: xx-large, and price lower than 50.00 dollars
- first suspicious action: step 2 `click[buy now]`
- pre-action reason: categories=['missing_attribute', 'premature_buy', 'insufficient_evidence']; missing=['size_constraint']; unsupported=['fine_grained_attributes_not_verified']
- post-action reason: categories=['potential_preventable_failure']
- Phase 2 opportunity: Attribute completion could verify missing constraints before executing the risky action.

```json
[
  {
    "step_id": 0,
    "raw_action": "search[machine wash men dress]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 1,
    "raw_action": "click[b09nd8p2qr]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 2,
    "raw_action": "click[buy now]",
    "pre_risk_level": "high",
    "pre_categories": [
      "missing_attribute",
      "premature_buy",
      "insufficient_evidence"
    ],
    "post_error": true,
    "post_categories": [
      "potential_preventable_failure"
    ],
    "reward": 0.0,
    "done": true
  }
]
```

### Task 19

- instruction: Instruction: Find me women's pumps with closed toe, rubber sole with color: black, and size: 7, and price lower than 80.00 dollars
- first suspicious action: step 0 `search[women pumps closed toe]`
- pre-action reason: No rule-based risk detected.
- post-action reason: categories=['constraint_conflict']
- Phase 2 opportunity: Post-action repair or rollback could respond after a no-effect or unexpected transition.

```json
[
  {
    "step_id": 0,
    "raw_action": "search[women pumps closed toe]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": true,
    "post_categories": [
      "constraint_conflict"
    ],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 1,
    "raw_action": "click[b09qpx97vw]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": true,
    "post_categories": [
      "constraint_conflict"
    ],
    "reward": 0.0,
    "done": false
  },
  {
    "step_id": 2,
    "raw_action": "click[buy now]",
    "pre_risk_level": "low",
    "pre_categories": [],
    "post_error": false,
    "post_categories": [],
    "reward": 0.0,
    "done": true
  }
]
```

## Interpretation Guardrail

Shadow mode does not improve success rate by design. Treat these metrics as detection and correlation evidence only.
