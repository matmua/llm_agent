# Tau3 Run Comparison

Note: the `predictor_soft` run below only covers tasks `12,13,14`, while
`direct` and `predictor_shadow` cover tasks `0-19`. Use this file as a current
progress index, not as a same-denominator accuracy comparison.

## Runs
| Run | Mode | Controller Version | Soft Risk Level | Soft Confidence | Success Rate | Success Count | Num Tasks | Avg Steps | Predictor Called | High Risk | Critical Risk | Revise Once | Changed By Controller | Constraint Revise | Second Check | Risk Reduced | Fallback Used | Invalid Revised Action | Executed Revised | Executed Fallback |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| retail_0_19_direct_qwen_deepseek_user_eval | direct | v2 | high | 0.6 | 0.3500 | 7 | 20 | 15.9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| retail_0_19_shadow_qwen_predictor_deepseek_user_eval | predictor_shadow | v2 | high | 0.6 | 0.4000 | 8 | 20 | 17.15 | 343 | 49 | 38 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | predictor_soft | v2 | high | 0.6 | 0.3333 | 1 | 3 | 14.0 | 42 | 5 | 0 | 5 | 5 | 5 | 5 | 5 | 0 | 0 | 5 | 0 |

## Main Observation
- predictor_shadow is observational only; it should not be interpreted as improving success rate.
- retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval: on tasks 12-14 only, success was 1/3; tasks 13 and 14 failed after 5 total controller interventions. This indicates the v2 intervention path is functioning mechanically, but the current revise policy can over-constrain or delay write actions.

## Per-task Comparison
| Task ID | Run | Success | Constraint Revise | Second Check | Risk Reduced | Fallback | Executed Revised | Executed Fallback |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 0 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 0 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 1 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 1 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 1 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | retail_0_19_direct_qwen_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 9 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 9 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 9 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 10 | retail_0_19_direct_qwen_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 10 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 10 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 11 | retail_0_19_direct_qwen_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 11 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 11 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 12 | retail_0_19_direct_qwen_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 12 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 12 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 13 | retail_0_19_direct_qwen_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 13 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 13 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | False | 4 | 4 | 4 | 0 | 4 | 0 |
| 14 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 14 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 14 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | False | 1 | 1 | 1 | 0 | 1 | 0 |
| 15 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 15 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 15 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 16 | retail_0_19_direct_qwen_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 16 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 16 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 17 | retail_0_19_direct_qwen_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 17 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | True | 0 | 0 | 0 | 0 | 0 | 0 |
| 17 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 18 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 18 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 18 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
| 19 | retail_0_19_direct_qwen_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 19 | retail_0_19_shadow_qwen_predictor_deepseek_user_eval | False | 0 | 0 | 0 | 0 | 0 | 0 |
| 19 | retail_12_14_soft_controller_v2_qwen_predictor_deepseek_user_eval | missing | 0 | 0 | 0 | 0 | 0 | 0 |
