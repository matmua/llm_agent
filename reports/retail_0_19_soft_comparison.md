# Retail 0-19 Soft Intervention Comparison

## Runs
| Run | Mode | Soft Risk Level | Soft Confidence | Success Rate | Success Count | Num Tasks | Avg Steps | Predictor Called | High Risk | Critical Risk | Revise Once | Changed By Controller |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| retail_0_19_direct_qwen_user_eval | direct | critical | 0.7 | 0.1000 | 2 | 20 | 13.05 | 0 | 0 | 0 | 0 | 0 |
| retail_0_19_shadow_qwen_predictor_qwen_user_eval | predictor_shadow | critical | 0.7 | 0.1500 | 3 | 20 | 13.05 | 261 | 49 | 4 | 0 | 0 |
| retail_0_19_soft_high06_qwen_predictor_qwen_user_eval | predictor_soft | high | 0.6 | 0.1000 | 2 | 20 | 12.4 | 248 | 48 | 4 | 18 | 14 |
| retail_0_19_soft_high07_qwen_predictor_qwen_user_eval | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |

## Missing Runs
| Run | Reason |
|---|---|
| retail_0_19_soft_high07_qwen_predictor_qwen_user_eval | summary.json missing |

## Main Observation
- predictor_shadow is observational only; it should not be interpreted as improving success rate.
- retail_0_19_soft_high06_qwen_predictor_qwen_user_eval: success rate did not improve vs direct by +0.0000 absolute; revise_once_count=18, changed_by_controller_count=14.

## Per-task Comparison
| Task ID | Direct Success | Shadow Success | Soft 0.6 Success | Soft 0.7 Success | Soft 0.6 Revised | Soft 0.7 Revised |
|---|---:|---:|---:|---:|---:|---:|
| 0 | True | True | True | missing | 0 | missing |
| 1 | False | True | False | missing | 1 | missing |
| 2 | False | False | False | missing | 0 | missing |
| 3 | False | False | False | missing | 0 | missing |
| 4 | False | False | False | missing | 2 | missing |
| 5 | False | False | False | missing | 1 | missing |
| 6 | False | False | False | missing | 2 | missing |
| 7 | False | False | False | missing | 1 | missing |
| 8 | False | False | False | missing | 1 | missing |
| 9 | False | False | False | missing | 1 | missing |
| 10 | False | False | False | missing | 2 | missing |
| 11 | False | False | False | missing | 0 | missing |
| 12 | True | True | True | missing | 0 | missing |
| 13 | False | False | False | missing | 1 | missing |
| 14 | False | False | False | missing | 3 | missing |
| 15 | False | False | False | missing | 2 | missing |
| 16 | False | False | False | missing | 0 | missing |
| 17 | False | False | False | missing | 0 | missing |
| 18 | False | False | False | missing | 1 | missing |
| 19 | False | False | False | missing | 0 | missing |
