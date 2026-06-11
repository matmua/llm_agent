# Task 0 案例拆解

这个文件把 tau3 retail task 0 拆成一个可以直接阅读的例子：任务是什么、正确路径是什么、plan-first 为什么失败。

## 任务设定

用户身份：

- 姓名：Yusuf Rossi
- Zip：19122
- 用户不记得自己的 email

用户目标：

- 用户收到订单 `#W2378156`。
- 想把订单里的 Mechanical Keyboard 换成 clicky switches。
- 如果没有 `clicky + RGB backlight + full size` 的键盘，可以接受 `clicky + no backlight + full size`。
- 还想把 Smart Thermostat 从 Apple HomeKit 兼容版本换成 Google Home / Google Assistant 兼容版本。

benchmark 期望的关键工具动作：

| 顺序 | 工具 | 关键参数 |
|---:|---|---|
| 1 | `find_user_id_by_name_zip` | Yusuf Rossi, 19122 |
| 2 | `get_order_details` | `#W2378156` |
| 3 | `get_product_details` | keyboard product `1656367028` |
| 4 | `get_product_details` | thermostat product `4896585277` |
| 5 | `exchange_delivered_order_items` | old items `1151293680`, `4983901480`; new items `7706410293`, `7747408585`; payment `credit_card_9513926` |

注：baseline 成功轨迹没有显式调用 `find_user_id_by_name_zip`，因为用户直接给了可用订单号，agent 直接 `get_order_details("#W2378156")` 也拿到了足够信息。

## 订单里的真实信息

`get_order_details("#W2378156")` 返回的关键内容：

| 商品 | product_id | 当前 item_id | 当前配置 |
|---|---|---|---|
| Mechanical Keyboard | `1656367028` | `1151293680` | linear, RGB, full size |
| Smart Thermostat | `4896585277` | `4983901480` | Apple HomeKit, black |

支付方式：

- `credit_card_9513926`

## 正确换货选择

键盘 product `1656367028` 里：

- 用户最想要的 `clicky + RGB + full size` 是 `9025753381`，但不可用。
- fallback `clicky + no backlight + full size` 是 `7706410293`，可用。

温控器 product `4896585277` 里：

- `Google Assistant + black` 是 `7747408585`，可用。

因此正确写操作是：

```json
{
  "tool": "exchange_delivered_order_items",
  "arguments": {
    "order_id": "#W2378156",
    "item_ids": ["1151293680", "4983901480"],
    "new_item_ids": ["7706410293", "7747408585"],
    "payment_method_id": "credit_card_9513926"
  }
}
```

baseline direct agent 就是这样完成的，最终 reward 为 `1.0`。

## Baseline 成功轨迹

轨迹位置：

- `trajectories/20260611_tau3_retail_qwen3_8b_subset5_local_eval/artifacts/task_0/sim_ece9cbe0-5c9a-444c-acc0-374f8d66413b/task.log`

工具调用摘要：

| turn | 工具 | 参数摘要 | 结果 |
|---:|---|---|---|
| 2 | `get_order_details` | `#W2378156` | 拿到订单、商品、payment method |
| 4 | `get_item_details` | `1151293680` | 确认当前键盘配置 |
| 6 | `get_product_details` | `1656367028` | 找到可用键盘 fallback `7706410293` |
| 8 | `get_item_details` | `4983901480` | 确认当前温控器配置 |
| 10 | `get_product_details` | `4896585277` | 找到可用温控器 `7747408585` |
| 12 | `exchange_delivered_order_items` | old `1151293680`, `4983901480`; new `7706410293`, `7747408585` | 换货成功 |

最终状态：

- 订单状态变成 `exchange requested`。
- `exchange_items`: `["1151293680", "4983901480"]`
- `exchange_new_items`: `["7706410293", "7747408585"]`
- `exchange_price_difference`: `-16.63`
- 用户模拟器回复 `###STOP###`

## Plan-First V2 失败轨迹

轨迹位置：

- `trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first_v2/artifacts/task_0/sim_80c5fe18-4db1-4a01-8893-24323efc3511/task.log`

失败工具调用摘要：

| turn | 工具 | 参数 | 结果 |
|---:|---|---|---|
| 2 | `get_product_details` | `mechanical_keyboard_id` | `Product not found` |
| 6 | `get_product_details` | `KB-4567` | `Product not found` |
| 8 | `get_product_details` | `TH-8901` | `Product not found` |
| 10 | `get_product_details` | `KB-4567` | `Product not found` |
| 12 | `get_product_details` | `KB-4567` | `Product not found` |

失败原因：

- 第一步没有先查订单 `#W2378156`。
- 模型生成了占位符式 ID：`mechanical_keyboard_id`。
- 失败后 assistant 让用户提供 product IDs。
- 用户模拟器给出了猜测 ID：`KB-4567` 和 `TH-8901`。
- agent 没有识别这些 ID 缺乏工具证据，反而继续查询并重复失败。
- 连续 5 次 `Product not found` 后触发 `too_many_errors`。

## 这个例子说明了什么

task 0 本身并不复杂，关键是先从订单中拿真实 ID，而不是让模型或用户猜 ID。

direct baseline 做对了：

1. 用订单号拿真实 item/product/payment IDs。
2. 查 product variants。
3. 选择可用 fallback。
4. 调换货工具。

plan-first V2 做错了：

1. 先猜 product ID。
2. 工具报错后继续围绕错误 ID 打转。
3. 相信用户模拟器给出的伪 ID。
4. 没有回到订单查询路径。

所以这里的下一步改进不应该是“让模型写更长计划”，而是代码层阻止猜 ID 和重复失败工具调用。
