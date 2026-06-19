# WebShop Shadow 分析报告

## 设置状态

- 后续默认最大步数已确认/保持为 `15`：`runners/run_webshop_shadow.py` 的 `--max_steps` 默认值是 `15`，README official run 示例也是 `--max_steps 15`。
- 未继续重跑完整 max15 版本；刚才误启动的半截 `resume14_max15` 产物已删除。
- 当前可用 20 条 Qwen 样本仍是已有 mixed 结果：task0-13 为 max15，task14-19 为 max8。它用于分析已有现象，不冒充全 max15 benchmark。

## 为什么之前平均 3 步不代表真的好

之前 `webshop_shadow_clean_20` 是 `model=mock`、`state_builder=llm_hybrid`，每条固定 3 步左右，本质是启发式快速购买。

- 成功率：13/20 = 65.0%
- 平均步数：3.00
- 平均 reward：0.2662
- reward=0：7/20
- 低分成功 `0 < reward < 0.3`：6/20
- 满分：1/20

结论：3 步版本很多只是很快给出购买动作，不代表商品匹配充分；平均 reward 只有 0.2662。

## 当前 Qwen3-8B 可用 20 条样本

- 成功率：13/20 = 65.0%
- 平均步数：9.40
- 平均 reward：0.3615
- reward=0：7/20
- 低分成功 `0 < reward < 0.3`：3/20
- 满分：3/20

Qwen 步数更长，因为它会真实搜索、翻页、返回、重复选择属性；但平均 reward 高于 mock baseline。

## Pre/Post 错误识别

按最终 `reward=0` 作为失败正例：

| 检测口径 | TP 正判 | FP 误报 | TN | FN 漏报 | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| pre 任意 warning | 7 | 13 | 0 | 0 | 35.0% | 100.0% |
| pre high only | 2 | 5 | 8 | 5 | 28.6% | 28.6% |
| post error | 7 | 10 | 3 | 0 | 41.2% | 100.0% |

按 `reward < 0.3` 作为质量失败正例：

| 检测口径 | TP 正判 | FP 误报 | TN | FN 漏报 | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| pre 任意 warning | 10 | 10 | 0 | 0 | 50.0% | 100.0% |
| pre high only | 3 | 4 | 6 | 7 | 42.9% | 30.0% |
| post error | 10 | 7 | 3 | 0 | 58.8% | 100.0% |

Step 级别计数：

- total_steps：188
- pre 任意 warning steps：44
- pre high steps：10
- post error steps：104
- pre categories：`{"missing_evidence": 34, "invalid_action": 10, "insufficient_evidence": 1}`
- post categories：`{"unexpected_transition": 67, "no_effect": 47, "action_no_effect": 47}`

## 结论

- `pre 任意 warning` 召回高但过宽，误报多。
- `pre high only` 太窄，漏掉很多最终失败。
- `post error` 对最终失败/低质量结果的召回高，但会把中途出错、后续恢复成功的任务记为误报。
- 现在的检测信号能定位局部错误，但还不能直接等价为最终失败预测；下一步需要把“局部可恢复错误”和“不可恢复失败风险”分开。
