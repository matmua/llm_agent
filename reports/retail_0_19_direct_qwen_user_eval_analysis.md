# Run Analysis: retail_0_19_direct_qwen_user_eval

## Setting
- Domain: retail
- Task IDs: ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19']
- Mode: direct
- Agent: qwen3-8b
- User simulator: qwen3-8b
- Evaluator: qwen3-8b
- Predictor: None

## Soft Intervention Setting
- soft_risk_level: critical
- soft_confidence_threshold: 0.7

## Main Results
| Metric | Value |
|---|---:|
| success_rate | 0.1000 |
| avg_steps | 13.0500 |
| predictor_called | 0 |
| high_risk_count | 0 |
| critical_risk_count | 0 |
| had_high_risk_warning | 0 |
| had_critical_risk_warning | 0 |
| had_high_risk_warning_count | 0 |
| had_critical_risk_warning_count | 0 |
| failed_tasks_with_high_or_critical_warning | 0 |
| success_tasks_with_high_or_critical_warning | 0 |
| revise_once_count | 0 |
| changed_by_controller_count | 0 |
| soft_risk_level | critical |
| soft_confidence_threshold | 0.7000 |

## Intervention Summary
| Metric | Value |
|---|---:|
| revise_once_count | 0 |
| changed_by_controller_count | 0 |

## Predictor Warning Distribution
| Risk Level | Count |
|---|---:|
| none | 0 |

## Warning vs Final Outcome
| Group | Count |
|---|---:|
| Failed tasks with high/critical warning | 0 |
| Failed tasks without high/critical warning | 18 |
| Successful tasks with high/critical warning | 0 |
| Successful tasks without high/critical warning | 2 |

## First High Risk Step Distribution
| Step | Count |
|---|---:|
| none | 0 |

## Per-task Summary
| Task ID | Success | Steps | High Risk | Critical Risk | First High Risk Step | First Critical Risk Step | Revise Once |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | True | 7 | 0 | 0 | None | None | 0 |
| 1 | False | 16 | 0 | 0 | None | None | 0 |
| 2 | False | 13 | 0 | 0 | None | None | 0 |
| 3 | False | 12 | 0 | 0 | None | None | 0 |
| 4 | False | 20 | 0 | 0 | None | None | 0 |
| 5 | False | 19 | 0 | 0 | None | None | 0 |
| 6 | False | 16 | 0 | 0 | None | None | 0 |
| 7 | False | 20 | 0 | 0 | None | None | 0 |
| 8 | False | 18 | 0 | 0 | None | None | 0 |
| 9 | False | 9 | 0 | 0 | None | None | 0 |
| 10 | False | 14 | 0 | 0 | None | None | 0 |
| 11 | False | 8 | 0 | 0 | None | None | 0 |
| 12 | True | 13 | 0 | 0 | None | None | 0 |
| 13 | False | 10 | 0 | 0 | None | None | 0 |
| 14 | False | 13 | 0 | 0 | None | None | 0 |
| 15 | False | 11 | 0 | 0 | None | None | 0 |
| 16 | False | 10 | 0 | 0 | None | None | 0 |
| 17 | False | 6 | 0 | 0 | None | None | 0 |
| 18 | False | 6 | 0 | 0 | None | None | 0 |
| 19 | False | 20 | 0 | 0 | None | None | 0 |

## Notes
- Do not claim improvement from predictor_shadow because it does not intervene.
- Compare predictor_soft only against direct under the same user simulator and evaluator.
