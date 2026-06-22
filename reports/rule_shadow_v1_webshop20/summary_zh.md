# rule-based shadow v1 WebShop20 报告

本次实现是 rule-based shadow v1：只维护 attributes 表和 actions 表。

- 没有使用 LLM detector。
- 没有使用 LLM state proposer。
- 没有把 shadow state 注入 agent prompt。
- 没有执行修复、阻断、回滚或 action 改写。
- pre 只检测格式是否合法、是否重复执行已知 no-info action。
- post 只检测 action 后是否出现新的 attribute value。

## 统计结果

- 样本数：20
- 最大步数：15
- action 数：191
- success：13 / 20 = 0.6500
- 平均 reward：0.3709
- 平均步数：9.55
- format_invalid_count：0
- repeat_known_no_info_count：26
- info_gain_true_count：124
- info_gain_false_count：67
- param_known_count：158
- param_unknown_count：33
- state_prompt_leak_count：0
- action_changed_count：0

## 最终检查

- 运行命令：`python -m runners.run_webshop_shadow --env official --num_samples 20 --start_index 0 --max_steps 15 --model qwen3-8b --state_to_agent false --log_dir logs/rule_shadow_v1_webshop20 --report_dir reports/rule_shadow_v1_webshop20`
- 活跃 shadow 入口：`runners/run_webshop_shadow.py`。
- 活跃 shadow core：`shadow/state.py`, `shadow/parser.py`, `shadow/extractor.py`, `shadow/pre.py`, `shadow/post.py`, `shadow/repair.py`。
- 已删除旧目录：`detectors/`, `state/`, `analysis/` 以及对应旧测试。
- `state_to_agent=false`，日志中 `state_prompt_leak_count=0`。
- `executed_action == raw_action`，日志中 `action_changed_count=0`。
- `shadow_state` 只包含 `attributes` 和 `actions` 两张表。
- `repair_placeholder.enabled=false`，没有触发修复、阻断、回滚或 action 改写。

## action_record 示例

### 示例 1

```json
{
  "step": 0,
  "raw": "search[double sided machine washable decorative pillows 28x28 printing technology under 50 dollars]",
  "type": "search",
  "params": {
    "query": "double sided machine washable decorative pillows 28x28 printing technology under 50 dollars"
  },
  "parsed_action": {
    "type": "search",
    "params": {
      "query": "double sided machine washable decorative pillows 28x28 printing technology under 50 dollars"
    },
    "format_valid": true,
    "error": null
  },
  "context_before": "ctx_1310550bcc6f",
  "action_signature": "search|query=double sided machine washable decorative pillows 28x28 printing technology under 50 dollars",
  "param_checks": {
    "query": {
      "value": "double sided machine washable decorative pillows 28x28 printing technology under 50 dollars",
      "known": false,
      "matched_attr": null
    }
  },
  "pre_check": {
    "format_valid": true,
    "repeat_known_no_info": false
  },
  "repair_placeholder": {
    "enabled": false,
    "decision": null,
    "new_action": null
  },
  "executed_action": "search[double sided machine washable decorative pillows 28x28 printing technology under 50 dollars]",
  "post_check": {
    "info_gain": true,
    "new_attrs": [
      {
        "key": "context.current",
        "value": "ctx_e89a6280b34d"
      },
      {
        "key": "text.observation.e89a6280b3",
        "value": "Instruction: | Find me double sided, machine washable decorative pillows with printing technology with size: 28\" x 28\", and price lower than 50.00 dollars | Back to Search | Page 1 (Total results: 50) | Next > | B07XTK3P89 | Lunarable Oriental Storage Toy Bag Chair, Eastern Bohem Detail Ottoman Tile Work Inspired Flowers, Stuffed Animal Organizer Washable Bag, Small Size, Turquoise Marigold | $39.99 | B08K7LDM7Q | 2 Pcs Cowhide Throw Pillow Covers Decorative Pillow Cases Farm Animal Brown Cow Hi"
      },
      {
        "key": "entity.b07xtk3p89",
        "value": "b07xtk3p89"
      },
      {
        "key": "attr.b07xtk3p89.title",
        "value": "Lunarable Oriental Storage Toy Bag Chair, Eastern Bohem Detail Ottoman Tile Work Inspired Flowers, Stuffed Animal Organizer Washable Bag, Small Size, Turquoise Marigold"
      },
      {
        "key": "attr.b07xtk3p89.price",
        "value": "$18.99"
      },
      {
        "key": "entity.b08k7ldm7q",
        "value": "b08k7ldm7q"
      },
      {
        "key": "attr.b08k7ldm7q.title",
        "value": "2 Pcs Cowhide Throw Pillow Covers Decorative Pillow Cases Farm Animal Brown Cow Hide Skin Print Pillow Case 18 X 18 Inch Velvet Square Cushion Cover for Sofa Bedroom"
      },
      {
        "key": "attr.b08k7ldm7q.price",
        "value": "$17.99"
      },
      {
        "key": "entity.b08qvdnjc7",
        "value": "b08qvdnjc7"
      },
      {
        "key": "attr.b08qvdnjc7.title",
        "value": "Valentine‘s Day Love Blue Throw Pillow Covers 18x18 for Home Decor- Love Heart Flower - Modern Linen Cushion Cover Square Ho
```

### 示例 2

```json
{
  "step": 1,
  "raw": "click[b08k7ldm7q]",
  "type": "click",
  "params": {
    "target": "b08k7ldm7q"
  },
  "parsed_action": {
    "type": "click",
    "params": {
      "target": "b08k7ldm7q"
    },
    "format_valid": true,
    "error": null
  },
  "context_before": "ctx_e89a6280b34d",
  "action_signature": "click|target=b08k7ldm7q",
  "param_checks": {
    "target": {
      "value": "b08k7ldm7q",
      "known": true,
      "matched_attr": "entity.b08k7ldm7q"
    }
  },
  "pre_check": {
    "format_valid": true,
    "repeat_known_no_info": false
  },
  "repair_placeholder": {
    "enabled": false,
    "decision": null,
    "new_action": null
  },
  "executed_action": "click[b08k7ldm7q]",
  "post_check": {
    "info_gain": true,
    "new_attrs": [
      {
        "key": "context.current",
        "value": "ctx_e2c4c185d5c3"
      },
      {
        "key": "text.observation.e2c4c185d5",
        "value": "Instruction: | Find me double sided, machine washable decorative pillows with printing technology with size: 28\" x 28\", and price lower than 50.00 dollars | Back to Search | < Prev | size | 18 x 18-inch | 20\"x20\" | 2 Pcs Cowhide Throw Pillow Covers Decorative Pillow Cases Farm Animal Brown Cow Hide Skin Print Pillow Case 18 X 18 Inch Velvet Square Cushion Cover for Sofa Bedroom | Price: $17.99 | Rating: N.A. | Description | Features | Reviews | Buy Now"
      },
      {
        "key": "entity.item_ecf9e7f0",
        "value": "item_ecf9e7f0"
      },
      {
        "key": "attr.item_ecf9e7f0.title",
        "value": "18 x 18-inch"
      },
      {
        "key": "attr.item_ecf9e7f0.size",
        "value": "18 x 18-inch"
      },
      {
        "key": "attr.item_ecf9e7f0.price",
        "value": "$17.99"
      },
      {
        "key": "attr.item_ecf9e7f0.rating",
        "value": "N.A"
      },
      {
        "key": "text.action_target.prev",
        "value": "< prev"
      },
      {
        "key": "text.action_target.description",
        "value": "description"
      },
      {
        "key": "text.action_target.features",
        "value": "features"
      },
      {
        "key": "text.action_target.reviews",
        "value": "reviews"
      },
      {
        "key": "text.action_target.buy_now",
        "value": "buy now"
      },
      {
        "key": "text.action_target.18_x_18_inch",
        "value": "18 x 18-inch"
      },
      {
        "key": "text.action_target.20_x20",
        "value": "20\"x20\""
      }
    ],
    "context_after": "ctx_e2c4c185d5c3"
  }
}
```

### 示例 3

```json
{
  "step": 2,
  "raw": "click[< prev]",
  "type": "click",
  "params": {
    "target": "< prev"
  },
  "parsed_action": {
    "type": "click",
    "params": {
      "target": "< prev"
    },
    "format_valid": true,
    "error": null
  },
  "context_before": "ctx_e2c4c185d5c3",
  "action_signature": "click|target=< prev",
  "param_checks": {
    "target": {
      "value": "< prev",
      "known": true,
      "matched_attr": "text.action_target.prev"
    }
  },
  "pre_check": {
    "format_valid": true,
    "repeat_known_no_info": false
  },
  "repair_placeholder": {
    "enabled": false,
    "decision": null,
    "new_action": null
  },
  "executed_action": "click[< prev]",
  "post_check": {
    "info_gain": false,
    "new_attrs": [],
    "context_after": "ctx_e89a6280b34d"
  }
}
```
