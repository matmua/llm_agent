# WebShop200 threshold3 three-way 实验报告

## 实验设置

- 实际样本数：200
- sample range：first 200 WebShop tasks，即 task 0-199
- max_steps：15
- state_to_agent：false
- temperature：0.0
- repeated_behavior_risk threshold：3
- 本次只运行实验和离线分析，没有修改 pre/post、verifier、repair hint、agent prompt 或 WebShop 环境逻辑。

## 三组结果

| 组别 | success | success_rate | avg_reward | avg_steps | action_changed | verifier calls | verified errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 129 / 200 | 0.6450 | 0.3458 | 9.13 | 0 | 0 | 0 |
| verify-only | 130 / 200 | 0.6500 | 0.3487 | 9.12 | 0 | 491 | 423 |
| hint repair | 138 / 200 | 0.6900 | 0.3713 | 8.86 | 4 | 202 | 123 |

## 耗时

- baseline：541 秒
- verify-only：941 秒
- hint repair：705 秒
- 三组总耗时：2187 秒

## baseline vs verify-only

- verify-only action_changed_count：0
- repair_hint_enabled：False
- repair_hint_to_agent：False
- baseline 和 verify-only action 序列不一致 task 数：3
- 首个分叉处 prompt hash 不一致 task 数：0

不一致 task 列表：

- 0, 114, 147

这些不一致在首个 action 分叉处的 prompt hash 均相同，因此记录为本地 Qwen/vLLM 同 prompt 生成非确定性，而不是 shadow/verifier 字段泄漏。

## prompt leakage 检查

- baseline state_prompt_leak_count：0
- verify state_prompt_leak_count：0
- repair state_prompt_leak_count：0
- verify repair_hint_prompt_count：0
- repair repair_hint_prompt_count：104
- agent-visible history 代码路径只保留 step/raw_action/executed_action/reward/done；内部字段只进日志，不进 Recent action history。
- 结论：未发现 prompt leakage。

## hint repair 相比 baseline

- 净成功提升：9 条
- fail_to_success：13 条
- 5, 7, 15, 57, 124, 127, 129, 139, 143, 147, 168, 170, 193
- 其中有 repair 介入的 fail_to_success：12 条
- 5, 7, 15, 57, 124, 127, 129, 139, 143, 168, 170, 193
- 无 repair 介入、应视作生成非确定性的 fail_to_success：1 条
- 147
- success_to_fail：4 条
- 98, 120, 136, 182
- reward 提升：15 条
- 5, 7, 15, 57, 63, 86, 124, 127, 129, 139, 143, 147, 168, 170, 193
- reward 下降：5 条
- 89, 98, 120, 136, 182

## risk/verifier 统计

| metric | baseline | verify-only | hint repair |
|---|---:|---:|---:|
| pre_rule_risk_trigger_action_count | 0 | 76 | 58 |
| post_rule_risk_trigger_action_count | 0 | 415 | 144 |
| pre_llm_called_action_count | 0 | 76 | 58 |
| post_llm_called_action_count | 0 | 415 | 144 |
| pre_llm_is_error_action_count | 0 | 34 | 9 |
| post_llm_is_error_action_count | 0 | 389 | 114 |
| llm_parse_error_count | 0 | 0 | 0 |

## repair 统计

- pre_repair_attempt_count：9
- pre_repair_success_count：9
- pre_repair_fallback_count：0
- post_hint_created_count：114
- post_hint_applied_count：102
- repair_hint_followed_count：91
- repair_hint_ignored_count：11

## repair 成功案例

- task 5：first risk step=3, risk type=repeated_behavior_risk, repair hint step=3; hint 后下一步 `click[b07fd13lp1]`；最终 reward 0.0000 -> 0.2857，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 7：first risk step=12, risk type=repeated_behavior_risk, repair hint step=12; hint 后下一步 `click[b09npml43m]`；最终 reward 0.0000 -> 0.6667，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 15：first risk step=3, risk type=repeated_behavior_risk, repair hint step=3; hint 后下一步 `click[b07f2g93bj]`；最终 reward 0.0000 -> 0.2000，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 57：first risk step=3, risk type=repeated_behavior_risk, repair hint step=3; hint 后下一步 `click[b07f2g93bj]`；最终 reward 0.0000 -> 0.1667，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 124：first risk step=3, risk type=repeated_behavior_risk, repair hint step=3; hint 后下一步 `click[b09m63b87v]`；最终 reward 0.0000 -> 0.2000，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 127：first risk step=6, risk type=repeated_behavior_risk, repair hint step=6; hint 后下一步 `click[b09kxchwgd]`；最终 reward 0.0000 -> 0.2857，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 129：first risk step=3, risk type=repeated_behavior_risk, repair hint step=3; hint 后下一步 `click[b07f2g93bj]`；最终 reward 0.0000 -> 1.0000，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 139：first risk step=3, risk type=repeated_behavior_risk, repair hint step=3; hint 后下一步 `click[b09m63b87v]`；最终 reward 0.0000 -> 0.4167，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 143：first risk step=3, risk type=repeated_behavior_risk, repair hint step=3; hint 后下一步 `click[b09m63b87v]`；最终 reward 0.0000 -> 0.4167，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 147：没有触发 rule risk、LLM verified error 或 repair hint；baseline 与 repair 首个分叉 step=8，reward 0.0000 -> 0.5714。这条不应归因为 repair，更像本地 Qwen/vLLM 同 prompt 生成非确定性带来的自然成功。
- task 168：first risk step=3, risk type=repeated_behavior_risk, repair hint step=3; hint 后下一步 `click[b07jvvdj6l]`；最终 reward 0.0000 -> 0.5714，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 170：first risk step=4, risk type=repeated_behavior_risk, repair hint step=4; hint 后下一步 `click[buy now]`；最终 reward 0.0000 -> 0.7500，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。
- task 193：first risk step=3, risk type=repeated_behavior_risk, repair hint step=3; hint 后下一步 `click[buy now]`；最终 reward 0.0000 -> 0.7143，主要因为 hint 打断了重复探索或触发 pre-repair 推进到可提交动作。

## repair 伤害案例

- task 98：first risk step=3, hint=`Risk-control hint for this action: The previous behavior was verified as repeated exploration. Do not continue the same action or strategy. Avoid repeating this action: click[next `；hint 后下一步 `click[b099wh1rtm]`；reward 0.6000 -> 0.0000。可能原因：hint 打断了原本会成功的局部重复/选项确认路径，或把 agent 推向了较差候选。
- task 120：first risk step=5, hint=`Risk-control hint for this action: The previous behavior was verified as repeated exploration. Do not continue the same action or strategy. Avoid repeating this action: click["20''`；hint 后下一步 `click["20''x20''"]`；reward 0.8000 -> 0.0000。可能原因：hint 打断了原本会成功的局部重复/选项确认路径，或把 agent 推向了较差候选。
- task 136：first risk step=6, hint=`Risk-control hint for this action: The previous behavior was verified as repeated exploration. Do not continue the same action or strategy. Avoid repeating this action: click[xx-la`；hint 后下一步 `click[description]`；reward 0.3000 -> 0.0000。可能原因：hint 打断了原本会成功的局部重复/选项确认路径，或把 agent 推向了较差候选。
- task 182：first risk step=3, hint=`Risk-control hint for this action: The previous behavior was verified as repeated exploration. Do not continue the same action or strategy. Avoid repeating this action: click[b09q5`；hint 后下一步 `click[back to search]`；reward 0.3750 -> 0.0000。可能原因：hint 打断了原本会成功的局部重复/选项确认路径，或把 agent 推向了较差候选。

## 未修复失败案例

- task 0：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 13：risk detected but verifier did not confirm；first_rule_risk=8, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 14：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 18：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 22：risk detected but hint ineffective；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 25：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 26：risk detected but verifier did not confirm；first_rule_risk=13, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 28：risk detected but hint ineffective; step budget exhausted；first_rule_risk=7, first_verified_error=8, first_hint=8, reward 0.0000 -> 0.0000。
- task 30：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 32：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 33：risk detected but verifier did not confirm；first_rule_risk=12, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 36：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 37：risk detected but hint ineffective；first_rule_risk=8, first_verified_error=8, first_hint=8, reward 0.0000 -> 0.0000。
- task 39：risk detected but hint ineffective; step budget exhausted；first_rule_risk=10, first_verified_error=10, first_hint=10, reward 0.0000 -> 0.0000。
- task 42：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 44：risk detected but hint ineffective; step budget exhausted；first_rule_risk=13, first_verified_error=13, first_hint=13, reward 0.0000 -> 0.0000。
- task 45：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 46：risk detected but hint ineffective; step budget exhausted；first_rule_risk=7, first_verified_error=8, first_hint=8, reward 0.0000 -> 0.0000。
- task 47：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 49：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 50：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 60：risk detected but hint ineffective; step budget exhausted；first_rule_risk=12, first_verified_error=14, first_hint=14, reward 0.0000 -> 0.0000。
- task 65：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 66：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 72：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 76：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 80：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 81：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 94：risk detected but hint ineffective; step budget exhausted；first_rule_risk=6, first_verified_error=6, first_hint=6, reward 0.0000 -> 0.0000。
- task 96：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 110：risk detected but verifier did not confirm；first_rule_risk=14, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 114：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 115：risk detected but hint ineffective; step budget exhausted；first_rule_risk=11, first_verified_error=13, first_hint=13, reward 0.0000 -> 0.0000。
- task 119：risk detected but verifier did not confirm；first_rule_risk=14, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 121：risk detected but verifier did not confirm；first_rule_risk=12, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 122：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 128：risk detected but verifier did not confirm；first_rule_risk=14, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 130：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 131：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 134：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 138：risk detected but hint ineffective; step budget exhausted；first_rule_risk=5, first_verified_error=5, first_hint=5, reward 0.0000 -> 0.0000。
- task 140：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 150：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 154：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 155：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 156：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 162：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 163：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 166：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 167：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 169：risk not detected；first_rule_risk=, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 172：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 173：risk detected but hint ineffective; step budget exhausted；first_rule_risk=4, first_verified_error=4, first_hint=4, reward 0.0000 -> 0.0000。
- task 183：risk detected but hint ineffective；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 184：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。
- task 185：risk detected but verifier did not confirm；first_rule_risk=13, first_verified_error=, first_hint=, reward 0.0000 -> 0.0000。
- task 186：risk detected but hint ineffective; step budget exhausted；first_rule_risk=6, first_verified_error=6, first_hint=6, reward 0.0000 -> 0.0000。
- task 187：risk detected but hint ineffective; step budget exhausted；first_rule_risk=3, first_verified_error=3, first_hint=3, reward 0.0000 -> 0.0000。

## 文件索引

- 三组汇总 JSON：`reports/webshop200_threshold3_threeway_metrics.json`
- 逐 task 对比 CSV：`reports/webshop200_threshold3_threeway_task_compare.csv`
- baseline 轨迹：`logs/rule_shadow_v1_baseline_threshold3_webshop200/trajectories.jsonl`
- verify-only 轨迹：`logs/rule_shadow_v1_prepost_llmverify_threshold3_webshop200/trajectories.jsonl`
- hint repair 轨迹：`logs/rule_shadow_v1_hintrepair_threshold3_webshop200/trajectories.jsonl`

## 结论

在 WebShop 前 200 条上，hint repair 相比 baseline 是提升：success 从 129 / 200 到 138 / 200，净变化 9 条。
