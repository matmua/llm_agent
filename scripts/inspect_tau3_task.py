#!/usr/bin/env python3
"""Print a readable view of a tau3 retail task and related DB records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETAIL_DATA_ROOT = PROJECT_ROOT / "external" / "tau2-bench" / "data" / "tau2" / "domains" / "retail"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def heading(text: str, level: int = 2) -> None:
    print(f"{'#' * level} {text}\n")


def bullet(label: str, value: Any) -> None:
    if value is not None:
        print(f"- {label}: {value}")


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def find_task(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any]:
    for task in tasks:
        if str(task.get("id")) == task_id:
            return task
    raise SystemExit(f"Task {task_id!r} not found")


def collect_ids(actions: list[dict[str, Any]]) -> dict[str, set[str]]:
    ids = {"user_ids": set(), "order_ids": set(), "product_ids": set(), "item_ids": set()}
    for action in actions:
        args = action.get("arguments") or {}
        for key, value in args.items():
            values = value if isinstance(value, list) else [value]
            for item in values:
                if not isinstance(item, str):
                    continue
                if key == "user_id":
                    ids["user_ids"].add(item)
                elif key == "order_id":
                    ids["order_ids"].add(item)
                elif key == "product_id":
                    ids["product_ids"].add(item)
                elif key in {"item_id", "variant_id"} or key.endswith("item_ids"):
                    ids["item_ids"].add(item)
    return ids


def print_order(order: dict[str, Any]) -> None:
    bullet("order_id", order.get("order_id"))
    bullet("user_id", order.get("user_id"))
    bullet("status", order.get("status"))
    payment_ids = [p.get("payment_method_id") for p in order.get("payment_history", [])]
    bullet("payment_methods", ", ".join(payment_ids))
    print("- items:")
    for item in order.get("items", []):
        print(
            "  - "
            f"{item.get('name')} | product_id={item.get('product_id')} "
            f"| item_id={item.get('item_id')} | price={item.get('price')} "
            f"| options={item.get('options')}"
        )


def print_product(product: dict[str, Any], highlight_items: set[str]) -> None:
    bullet("name", product.get("name"))
    bullet("product_id", product.get("product_id"))
    print("- variants:")
    for item_id, variant in product.get("variants", {}).items():
        mark = " *" if item_id in highlight_items else ""
        print(
            f"  - {item_id}{mark} | available={variant.get('available')} "
            f"| price={variant.get('price')} | options={variant.get('options')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id", help="Retail task id, for example 0")
    parser.add_argument("--data-root", type=Path, default=RETAIL_DATA_ROOT)
    args = parser.parse_args()

    tasks = load_json(args.data_root / "tasks.json")
    db = load_json(args.data_root / "db.json")
    task = find_task(tasks, args.task_id)
    criteria = task.get("evaluation_criteria") or {}
    actions = criteria.get("actions") or []
    ids = collect_ids(actions)

    heading(f"Tau3 Retail Task {task['id']}", 1)

    heading("用户模拟器设定")
    instructions = (task.get("user_scenario") or {}).get("instructions") or {}
    for key in ["task_instructions", "reason_for_call", "known_info", "unknown_info"]:
        bullet(key, instructions.get(key))
    print()

    heading("评分动作")
    for action in actions:
        print(
            f"- {action.get('action_id')}: `{action.get('name')}` "
            f"{compact_json(action.get('arguments') or {})}"
        )
    reward_basis = criteria.get("reward_basis")
    if reward_basis:
        print(f"\n- reward_basis: {reward_basis}")
    nl_assertions = criteria.get("nl_assertions")
    if nl_assertions:
        print(f"- nl_assertions: {compact_json(nl_assertions)}")
    print()

    heading("相关数据库记录")
    for user_id in sorted(ids["user_ids"]):
        user = db["users"].get(user_id)
        if user:
            heading(f"User {user_id}", 3)
            print(compact_json(user))
            print()

    for order_id in sorted(ids["order_ids"]):
        order = db["orders"].get(order_id)
        if order:
            heading(f"Order {order_id}", 3)
            print_order(order)
            print()
            ids["user_ids"].add(order.get("user_id", ""))
            for item in order.get("items", []):
                ids["product_ids"].add(item.get("product_id", ""))
                ids["item_ids"].add(item.get("item_id", ""))

    for product_id in sorted(item for item in ids["product_ids"] if item):
        product = db["products"].get(product_id)
        if product:
            heading(f"Product {product_id}", 3)
            print_product(product, ids["item_ids"])
            print()

    heading("原始文件位置")
    print(f"- tasks: `{args.data_root / 'tasks.json'}`")
    print(f"- database: `{args.data_root / 'db.json'}`")
    print(f"- policy: `{args.data_root / 'policy.md'}`")
    print(f"- splits: `{args.data_root / 'split_tasks.json'}`")


if __name__ == "__main__":
    main()
