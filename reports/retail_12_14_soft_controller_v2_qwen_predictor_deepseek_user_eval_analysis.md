# Run Analysis: retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval

## Setting
- Domain: retail
- Task IDs: ['12', '13', '14']
- Mode: predictor_soft
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
| success_rate | 0.3333 |
| avg_steps | 14.0000 |
| predictor_called | 42 |
| high_risk_count | 5 |
| critical_risk_count | 0 |
| had_high_risk_warning | 2 |
| had_critical_risk_warning | 0 |
| had_high_risk_warning_count | 2 |
| had_critical_risk_warning_count | 0 |
| failed_tasks_with_high_or_critical_warning | 2 |
| success_tasks_with_high_or_critical_warning | 0 |
| revise_once_count | 5 |
| changed_by_controller_count | 5 |
| soft_risk_level | high |
| soft_confidence_threshold | 0.6000 |
| soft_intervention_confidence_threshold | 0.6000 |
| controller_version | v2 |
| constraint_guided_revise_count | 5 |
| second_check_count | 5 |
| risk_reduced_after_revision_count | 5 |
| fallback_used_count | 0 |
| invalid_revised_action_count | 0 |
| executed_original_count | 37 |
| executed_revised_count | 5 |
| executed_fallback_count | 0 |
| risk_reduction_rate | 1.0000 |
| fallback_rate | 0.0000 |

## Intervention Summary
| Metric | Value |
|---|---:|
| revise_once_count | 5 |
| changed_by_controller_count | 5 |

## Controller v2 Summary
| Metric | Value |
|---|---:|
| Constraint-guided revise count | 5 |
| Second check count | 5 |
| Risk reduced after revision | 5 |
| Risk reduction rate | 1.0000 |
| Invalid revised action count | 0 |
| Fallback used count | 0 |
| Fallback rate | 0.0000 |
| Executed original | 37 |
| Executed revised | 5 |
| Executed fallback | 0 |

## Predictor Warning Distribution
| Risk Level | Count |
|---|---:|
| high | 5 |

## Warning vs Final Outcome
| Group | Count |
|---|---:|
| Failed tasks with high/critical warning | 2 |
| Failed tasks without high/critical warning | 0 |
| Successful tasks with high/critical warning | 0 |
| Successful tasks without high/critical warning | 1 |

## First High Risk Step Distribution
| Step | Count |
|---|---:|
| 4 | 1 |
| 11 | 1 |

## Per-task Summary
| Task ID | Success | Steps | High Risk | Critical Risk | First High Risk Step | First Critical Risk Step | Revise Once | Constraint Revise | Second Check | Fallback | Executed Revised |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 12 | True | 11 | 0 | 0 | None | None | 0 | 0 | 0 | 0 | 0 |
| 13 | False | 20 | 4 | 0 | 11 | None | 4 | 4 | 4 | 0 | 4 |
| 14 | False | 11 | 1 | 0 | 4 | None | 1 | 1 | 1 | 0 | 1 |

## Notes
- Do not claim improvement from predictor_shadow because it does not intervene.
- Compare predictor_soft only against direct under the same user simulator and evaluator.
