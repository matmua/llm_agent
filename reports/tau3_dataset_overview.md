# Tau3 Retail 数据集/环境说明

这个 benchmark 不是传统静态 QA 数据集。更准确地说，它是一个交互式客服环境，并且默认会涉及不止一个 LLM 角色：

1. **agent model**：被测试的客服 agent。
2. **user simulator model**：根据隐藏任务设定扮演用户，持续生成用户消息。
3. **NL assertion evaluator model**：对自然语言要求做裁判，例如“agent 是否告诉用户有 10 个 T-shirt 选项”。

我们这次为了不依赖外部 API，把这三个角色都接到了本地 vLLM 的 Qwen3-8B，而不是调用 OpenAI/Anthropic 等外部大模型 API。

整体结构如下：

1. `tasks.json` 定义用户目标和评分标准。
2. `db.json` 是一个假的零售后台数据库。
3. `policy.md` 是客服必须遵守的业务规则。
4. `tools.py` 定义 agent 能调用的后台工具。
5. `environment.py` 把数据库、工具和 policy 组装成可交互环境。
6. 运行后，轨迹会保存每一轮用户、agent、工具调用、工具返回和最终评分。

## 数据在哪里

Retail domain 的数据目录：

```text
external/tau2-bench/data/tau2/domains/retail/
```

主要文件：

| 文件 | 作用 |
|---|---|
| `tasks.json` | 114 条 retail 任务。每条任务包含用户设定、任务目标、期望工具动作、评分依据。 |
| `split_tasks.json` | 任务划分：`train` 74 条，`test` 40 条，`base` 114 条。 |
| `db.json` | 零售后台数据库：50 类商品、500 个用户、1000 个订单。 |
| `policy.md` | 客服规则，比如必须认证用户、写操作前要确认、不能编造信息。 |
| `tasks_voice.json` | 语音版任务。当前实验没用它。 |
| `audio_difficulty.json` | 语音难度信息。当前实验没用它。 |

环境代码目录：

```text
external/tau2-bench/src/tau2/domains/retail/
```

主要文件：

| 文件 | 作用 |
|---|---|
| `tools.py` | 工具实现，例如查用户、查订单、查商品、换货、退货、修改订单。 |
| `environment.py` | 加载 `db.json`、`policy.md`，创建 retail 环境。 |
| `data_model.py` | User、Order、Product、Variant 等数据结构。 |
| `utils.py` | 数据路径等辅助函数。 |

## 数据长什么样

### task

一条 task 不是“问题 + 答案”，而是类似这样：

- 用户身份：Yusuf Rossi，zip 19122。
- 用户目标：收到订单 `#W2378156`，想换机械键盘和智能温控器。
- 用户不知道的信息：不记得 email。
- 评分标准：agent 是否调用了正确工具、是否把数据库改成期望状态、是否满足自然语言断言。

task 0 的原始定义在：

```text
external/tau2-bench/data/tau2/domains/retail/tasks.json
```

也可以看我整理过的版本：

```text
reports/task0_case_study.md
```

### database

`db.json` 顶层有三块：

| key | 数量 | 内容 |
|---|---:|---|
| `products` | 50 | 商品类型和所有 variant item。 |
| `users` | 500 | 用户资料、地址、支付方式、订单列表。 |
| `orders` | 1000 | 订单状态、商品 item、付款记录、履约信息。 |

一个订单里会有：

- `order_id`
- `user_id`
- `items`
- `status`
- `payment_history`
- `fulfillments`
- 以及换货/退货/取消后产生的新状态字段。

## 它是环境吗

是。运行时发生的是：

1. user simulator 根据 task 生成用户消息。
2. agent 读消息，然后决定回复用户或调用一个工具。
3. environment 接收工具调用，在 `db.json` 的拷贝上查询或修改状态。
4. 工具返回结果进入对话历史。
5. 重复多轮，直到用户 `###STOP###`、转人工、达到最大步数或错误过多。
6. evaluator 检查轨迹和最终数据库状态，给 reward。

所以 agent 不是在预测一个固定答案，而是在一个小型零售后台里执行操作。

## 这次实验用的是哪个模型

这次本地 run 的三个 LLM 角色全部是：

```text
openai/qwen3-8b
api_base=http://127.0.0.1:8000/v1
api_key=EMPTY
```

也就是说：

| 角色 | 我们这次使用 |
|---|---|
| agent | 本地 Qwen3-8B |
| user simulator | 本地 Qwen3-8B |
| NL assertion evaluator | 本地 Qwen3-8B |
| plan-first 私有计划 | 本地 Qwen3-8B |

这让实验可以完全在服务器本地跑通，但也带来一个重要限制：结果不能直接对齐官方 leaderboard。官方配置通常会使用更强的外部 API 模型作为 user simulator 和/或 evaluator，本地 Qwen3-8B 用户模拟器会改变用户行为、对话难度和评估稳定性。

具体配置可以看：

```text
trajectories/20260611_tau3_retail_qwen3_8b_subset5_local_eval/run_meta.json
trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first_v2/run_meta.json
```

## 我们的运行轨迹在哪里

baseline direct run：

```text
trajectories/20260611_tau3_retail_qwen3_8b_subset5_local_eval/
```

plan-first V2 run：

```text
trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first_v2/
```

每个 run 里主要看：

| 文件/目录 | 作用 |
|---|---|
| `results.json` | benchmark 保存的完整结果对象。 |
| `analysis.json` | 我们整理过的失败类型、工具调用轨迹和错误摘要。 |
| `run_meta.json` | 本次运行配置。 |
| `artifacts/task_X/.../task.log` | 最直观的逐步日志：用户说了什么、agent 调了什么工具、工具返回什么。 |
| `artifacts/task_X/.../llm_debug/*.json` | 每次 LLM 请求/响应的原始 debug 文件。 |

## 怎么直观看一个任务

我加了一个小脚本：

```bash
./no_proxy_run.sh .venv-tau2/bin/python scripts/inspect_tau3_task.py 0
```

它会打印：

- 用户模拟器设定；
- 评分动作；
- 相关订单；
- 相关商品 variants；
- 原始文件位置。

例如 task 0 的完整案例也可以直接看：

```text
reports/task0_case_study.md
```
