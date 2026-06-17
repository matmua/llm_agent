# Run Analysis: retail_0_19_shadow_qwen_predictor_qwen_user_eval

## Setting
- Domain: retail
- Task IDs: ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19']
- Mode: predictor_shadow
- Agent: qwen3-8b
- User simulator: qwen3-8b
- Evaluator: qwen3-8b
- Predictor: qwen3-8b

## Soft Intervention Setting
- soft_risk_level: critical
- soft_confidence_threshold: 0.7

## Main Results
| Metric | Value |
|---|---:|
| success_rate | 0.1500 |
| avg_steps | 13.0500 |
| predictor_called | 261 |
| high_risk_count | 49 |
| critical_risk_count | 4 |
| had_high_risk_warning | 19 |
| had_critical_risk_warning | 4 |
| had_high_risk_warning_count | 19 |
| had_critical_risk_warning_count | 4 |
| failed_tasks_with_high_or_critical_warning | 16 |
| success_tasks_with_high_or_critical_warning | 3 |
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
| critical | 4 |
| high | 49 |

## Warning vs Final Outcome
| Group | Count |
|---|---:|
| Failed tasks with high/critical warning | 16 |
| Failed tasks without high/critical warning | 1 |
| Successful tasks with high/critical warning | 3 |
| Successful tasks without high/critical warning | 0 |

## First High Risk Step Distribution
| Step | Count |
|---|---:|
| 1 | 14 |
| 2 | 3 |
| 3 | 1 |
| 6 | 1 |

## Per-task Summary
| Task ID | Success | Steps | High Risk | Critical Risk | First High Risk Step | First Critical Risk Step | Revise Once |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | True | 7 | 1 | 0 | 1 | None | 0 |
| 1 | True | 8 | 1 | 0 | 6 | None | 0 |
| 2 | False | 13 | 0 | 0 | None | None | 0 |
| 3 | False | 12 | 3 | 0 | 3 | None | 0 |
| 4 | False | 20 | 5 | 1 | 1 | 19 | 0 |
| 5 | False | 19 | 7 | 0 | 1 | None | 0 |
| 6 | False | 16 | 3 | 0 | 1 | None | 0 |
| 7 | False | 20 | 2 | 0 | 1 | None | 0 |
| 8 | False | 20 | 2 | 0 | 1 | None | 0 |
| 9 | False | 10 | 1 | 1 | 2 | 1 | 0 |
| 10 | False | 14 | 4 | 0 | 1 | None | 0 |
| 11 | False | 8 | 2 | 0 | 1 | None | 0 |
| 12 | True | 13 | 1 | 0 | 1 | None | 0 |
| 13 | False | 10 | 2 | 1 | 2 | 1 | 0 |
| 14 | False | 13 | 3 | 0 | 1 | None | 0 |
| 15 | False | 16 | 2 | 1 | 2 | 1 | 0 |
| 16 | False | 10 | 5 | 0 | 1 | None | 0 |
| 17 | False | 6 | 1 | 0 | 1 | None | 0 |
| 18 | False | 6 | 2 | 0 | 1 | None | 0 |
| 19 | False | 20 | 2 | 0 | 1 | None | 0 |

## Notes
- Do not claim improvement from predictor_shadow because it does not intervene.
- Compare predictor_soft only against direct under the same user simulator and evaluator.
