# Run Analysis: retail_0_19_shadow_qwen_predictor_deepseek_user_eval

## Setting
- Domain: retail
- Task IDs: ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19']
- Mode: predictor_shadow
- Controller version: v2
- Agent: qwen3-8b
- User simulator: deepseek-v4-pro
- Evaluator: deepseek-v4-pro
- Predictor: qwen3-8b

## Soft Intervention Setting
- soft_risk_level: high
- soft_confidence_threshold: 0.6
- soft_intervention_confidence_threshold: 0.6

## Main Results
| Metric | Value |
|---|---:|
| success_rate | 0.4000 |
| avg_steps | 17.1500 |
| predictor_called | 343 |
| high_risk_count | 49 |
| critical_risk_count | 38 |
| had_high_risk_warning | 16 |
| had_critical_risk_warning | 16 |
| had_high_risk_warning_count | 16 |
| had_critical_risk_warning_count | 16 |
| failed_tasks_with_high_or_critical_warning | 12 |
| success_tasks_with_high_or_critical_warning | 6 |
| revise_once_count | 0 |
| changed_by_controller_count | 0 |
| soft_risk_level | high |
| soft_confidence_threshold | 0.6000 |
| soft_intervention_confidence_threshold | 0.6000 |
| controller_version | v2 |
| constraint_guided_revise_count | 0 |
| second_check_count | 0 |
| risk_reduced_after_revision_count | 0 |
| fallback_used_count | 0 |
| invalid_revised_action_count | 0 |
| executed_original_count | 343 |
| executed_revised_count | 0 |
| executed_fallback_count | 0 |
| risk_reduction_rate | 0.0000 |
| fallback_rate | 0.0000 |

## Intervention Summary
| Metric | Value |
|---|---:|
| revise_once_count | 0 |
| changed_by_controller_count | 0 |

## Controller v2 Summary
| Metric | Value |
|---|---:|
| Constraint-guided revise count | 0 |
| Second check count | 0 |
| Risk reduced after revision | 0 |
| Risk reduction rate | 0.0000 |
| Invalid revised action count | 0 |
| Fallback used count | 0 |
| Fallback rate | 0.0000 |
| Executed original | 343 |
| Executed revised | 0 |
| Executed fallback | 0 |

## Predictor Warning Distribution
| Risk Level | Count |
|---|---:|
| critical | 38 |
| high | 49 |

## Warning vs Final Outcome
| Group | Count |
|---|---:|
| Failed tasks with high/critical warning | 12 |
| Failed tasks without high/critical warning | 0 |
| Successful tasks with high/critical warning | 6 |
| Successful tasks without high/critical warning | 2 |

## First High Risk Step Distribution
| Step | Count |
|---|---:|
| 1 | 4 |
| 3 | 5 |
| 8 | 1 |
| 9 | 1 |
| 13 | 1 |
| 14 | 1 |
| 15 | 1 |
| 19 | 2 |

## Per-task Summary
| Task ID | Success | Steps | High Risk | Critical Risk | First High Risk Step | First Critical Risk Step | Revise Once | Constraint Revise | Second Check | Fallback | Executed Revised |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | False | 20 | 5 | 0 | 1 | None | 0 | 0 | 0 | 0 | 0 |
| 1 | False | 20 | 7 | 2 | 3 | 5 | 0 | 0 | 0 | 0 | 0 |
| 2 | False | 20 | 0 | 1 | None | 5 | 0 | 0 | 0 | 0 | 0 |
| 3 | False | 20 | 6 | 1 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 4 | False | 20 | 2 | 3 | 3 | 5 | 0 | 0 | 0 | 0 | 0 |
| 5 | False | 20 | 2 | 2 | 19 | 1 | 0 | 0 | 0 | 0 | 0 |
| 6 | True | 16 | 1 | 1 | 15 | 1 | 0 | 0 | 0 | 0 | 0 |
| 7 | False | 20 | 1 | 2 | 9 | 1 | 0 | 0 | 0 | 0 | 0 |
| 8 | False | 20 | 4 | 1 | 1 | 2 | 0 | 0 | 0 | 0 | 0 |
| 9 | False | 20 | 1 | 3 | 19 | 1 | 0 | 0 | 0 | 0 | 0 |
| 10 | True | 13 | 1 | 4 | 3 | 1 | 0 | 0 | 0 | 0 | 0 |
| 11 | True | 17 | 7 | 2 | 1 | 2 | 0 | 0 | 0 | 0 | 0 |
| 12 | True | 12 | 0 | 0 | None | None | 0 | 0 | 0 | 0 | 0 |
| 13 | True | 13 | 1 | 0 | 8 | None | 0 | 0 | 0 | 0 | 0 |
| 14 | True | 16 | 1 | 3 | 14 | 1 | 0 | 0 | 0 | 0 | 0 |
| 15 | True | 16 | 0 | 4 | None | 1 | 0 | 0 | 0 | 0 | 0 |
| 16 | False | 15 | 1 | 3 | 13 | 1 | 0 | 0 | 0 | 0 | 0 |
| 17 | True | 5 | 0 | 0 | None | None | 0 | 0 | 0 | 0 | 0 |
| 18 | False | 20 | 3 | 3 | 3 | 1 | 0 | 0 | 0 | 0 | 0 |
| 19 | False | 20 | 6 | 3 | 3 | 1 | 0 | 0 | 0 | 0 | 0 |

## Notes
- Do not claim improvement from predictor_shadow because it does not intervene.
- Compare predictor_soft only against direct under the same user simulator and evaluator.
