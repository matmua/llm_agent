# Run Analysis: smoke_mock_soft_qwen_predictor

## Setting
- Domain: mock
- Task IDs: ['create_task_1']
- Mode: predictor_soft
- Agent: qwen3-8b
- User simulator: qwen3-8b
- Evaluator: qwen3-8b
- Predictor: qwen3-8b

## Main Results
| Metric | Value |
|---|---:|
| success_rate | 1.0000 |
| avg_steps | 2.0000 |
| predictor_called | 2 |
| high_risk_count | 0 |
| critical_risk_count | 0 |
| had_high_risk_warning_count | 0 |
| had_critical_risk_warning_count | 0 |
| failed_tasks_with_high_or_critical_warning | 0 |
| success_tasks_with_high_or_critical_warning | 0 |
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
| Failed tasks without high/critical warning | 0 |
| Successful tasks with high/critical warning | 0 |
| Successful tasks without high/critical warning | 1 |

## First High Risk Step Distribution
| Step | Count |
|---|---:|
| none | 0 |

## Per-task Summary
| Task ID | Success | Steps | High Risk | Critical Risk | First High Risk Step | First Critical Risk Step | Revise Once |
|---|---:|---:|---:|---:|---:|---:|---:|
| create_task_1 | True | 2 | 0 | 0 | None | None | 0 |

## Notes
- Do not claim improvement from predictor_shadow because it does not intervene.
- Compare predictor_soft only against direct under the same user simulator and evaluator.
