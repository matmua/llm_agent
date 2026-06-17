# Run Analysis: retail_0_4_shadow_qwen_predictor_deepseek_user_eval

## Setting
- Domain: retail
- Task IDs: ['0', '1', '2', '3', '4']
- Mode: predictor_shadow
- Agent: qwen3-8b
- User simulator: deepseek-v4-pro
- Evaluator: deepseek-v4-pro
- Predictor: qwen3-8b

## Main Results
| Metric | Value |
|---|---:|
| success_rate | 0.0000 |
| avg_steps | 12.2000 |
| predictor_called | 61 |
| high_risk_count | 5 |
| critical_risk_count | 0 |
| had_high_risk_warning_count | 3 |
| had_critical_risk_warning_count | 0 |
| failed_tasks_with_high_or_critical_warning | 3 |
| success_tasks_with_high_or_critical_warning | 0 |
| revise_once_count | 0 |
| changed_by_controller_count | 0 |

## Predictor Warning Distribution
| Risk Level | Count |
|---|---:|
| high | 5 |

## Warning vs Final Outcome
| Group | Count |
|---|---:|
| Failed tasks with high/critical warning | 3 |
| Failed tasks without high/critical warning | 2 |
| Successful tasks with high/critical warning | 0 |
| Successful tasks without high/critical warning | 0 |

## First High Risk Step Distribution
| Step | Count |
|---|---:|
| 2 | 1 |
| 3 | 1 |
| 13 | 1 |

## Per-task Summary
| Task ID | Success | Steps | High Risk | Critical Risk | First High Risk Step | First Critical Risk Step | Revise Once |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | False | 0 | 0 | 0 | None | None | 0 |
| 1 | False | 6 | 0 | 0 | None | None | 0 |
| 2 | False | 19 | 1 | 0 | 2 | None | 0 |
| 3 | False | 19 | 3 | 0 | 13 | None | 0 |
| 4 | False | 17 | 1 | 0 | 3 | None | 0 |

## Notes
- Do not claim improvement from predictor_shadow because it does not intervene.
- Compare predictor_soft only against direct under the same user simulator and evaluator.
