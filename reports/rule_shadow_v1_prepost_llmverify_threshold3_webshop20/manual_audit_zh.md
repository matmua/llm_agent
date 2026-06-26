# rule-based shadow v1 trajrisk 人工审计摘要

## Action-level signals

- visible_delta_false_count：54
- action_no_progress_count：6
- same_action_repeated_no_progress_count：6
- context_cycle_no_progress_count：0

## Trajectory-level signals

- repeated_behavior_risk：连续相同 action_signature 达到 3 次后触发。
- 该信号不要求 visible_delta=False，用来捕捉翻页等看似有页面变化但行为策略已经卡住的轨迹。
- repeated_behavior_risk_action_count：58
- repeated_behavior_risk_sample_count：10
- failed_samples_with_repeated_behavior_risk：6
- successful_samples_with_repeated_behavior_risk：4

## 重点样例

- task 5：success=False, steps=15, first_repeated_behavior_risk_step=3, action_signature=click|target=next >, streak=3
- task 15：success=False, steps=15, first_repeated_behavior_risk_step=3, action_signature=click|target=next >, streak=3
- task 18：success=False, steps=15, first_repeated_behavior_risk_step=3, action_signature=click|target=next >, streak=3

task 5 / task 15 / task 18 均被 repeated_behavior_risk 捕获，主要模式是搜索后连续 `click[next >]`，页面持续变化但决策没有转向商品选择或购买。

## 未覆盖失败样例

task 13 / task 14 没有触发当前通用重复行为规则。它们的动作不是连续同一 action_signature，而是在搜索、商品页、返回、详情页和不同商品之间移动；这类错误更像语义目标不收敛或错误商品探索，仅靠通用重复行为规则不一定能捕获，后续需要 LLM risk detector 或目标约束检测。