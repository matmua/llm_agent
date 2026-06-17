# Run Analysis: retail_0_4_shadow_qwen_predictor_qwen_user_eval

## Setting
- Domain: retail
- Task IDs: ['0', '1', '2', '3', '4']
- Mode: predictor_shadow
- Agent: qwen3-8b
- User simulator: qwen3-8b
- Evaluator: qwen3-8b
- Predictor: qwen3-8b

## Main Results
| Metric | Value |
|---|---:|
| success_rate | 0.2000 |
| avg_steps | 14.6000 |
| predictor_called | 73 |
| high_risk_count | 11 |
| critical_risk_count | 0 |
| had_high_risk_warning_count | 4 |
| had_critical_risk_warning_count | 0 |
| failed_tasks_with_high_or_critical_warning | 3 |
| success_tasks_with_high_or_critical_warning | 1 |
| revise_once_count | 0 |
| changed_by_controller_count | 0 |

## Predictor Warning Distribution
| Risk Level | Count |
|---|---:|
| high | 11 |

## Warning vs Final Outcome
| Group | Count |
|---|---:|
| Failed tasks with high/critical warning | 3 |
| Failed tasks without high/critical warning | 1 |
| Successful tasks with high/critical warning | 1 |
| Successful tasks without high/critical warning | 0 |

## First High Risk Step Distribution
| Step | Count |
|---|---:|
| 3 | 2 |
| 5 | 1 |
| 6 | 1 |

## Per-task Summary
| Task ID | Success | Steps | High Risk | Critical Risk | First High Risk Step | First Critical Risk Step | Revise Once |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | True | 7 | 1 | 0 | 5 | None | 0 |
| 1 | False | 13 | 4 | 0 | 6 | None | 0 |
| 2 | False | 13 | 0 | 0 | None | None | 0 |
| 3 | False | 20 | 4 | 0 | 3 | None | 0 |
| 4 | False | 20 | 2 | 0 | 3 | None | 0 |

## Notes
- Do not claim improvement from predictor_shadow because it does not intervene.
- Compare predictor_soft only against direct under the same user simulator and evaluator.
