"""WebShop adapter for generic state proposals."""

from __future__ import annotations

import re
from typing import Any


COLORS = {
    "red",
    "blue",
    "green",
    "black",
    "white",
    "gray",
    "grey",
    "pink",
    "purple",
    "yellow",
    "orange",
    "brown",
    "silver",
    "gold",
}
SIZES = {"xs", "small", "medium", "large", "xl", "xxl", "xx-large", "x-large", "3x-large"}
NAV_CLICKABLES = {
    "next",
    "next >",
    "previous",
    "prev",
    "< prev",
    "back to search",
    "description",
    "features",
    "reviews",
    "attributes",
    "buy now",
}


class WebShopAdapter:
    domain = "webshop"

    def build_proposal(
        self,
        task_instruction: str,
        observation: str,
        available_actions: dict[str, Any],
        step_id: int,
        last_action: str = "",
    ) -> dict[str, Any]:
        page_type = infer_page_type(observation, available_actions)
        proposal: dict[str, Any] = {
            "entities": [],
            "constraints": [],
            "relations": [],
            "goals": [
                {
                    "goal_id": "webshop_goal",
                    "description": task_instruction,
                    "completion_action_type": "buy_now",
                    "status": "in_progress",
                }
            ],
            "current_observation_summary": _compact_observation(observation),
            "expected_state_changes_from_last_action": [],
            "uncertain_or_missing_information": [],
        }
        proposal["entities"].append(
            {
                "entity_id": "page:current",
                "entity_type": "page",
                "name": "current_page",
                "source": "observation",
                "confidence": "high",
                "evidence_text": observation[:300],
                "attributes": [
                    {
                        "name": "page_type",
                        "value": page_type,
                        "value_type": "string",
                        "source": "observation",
                        "confidence": "high",
                        "evidence_text": observation[:300],
                        "is_confirmed": True,
                    },
                    {
                        "name": "has_search_bar",
                        "value": bool(available_actions.get("has_search_bar")),
                        "value_type": "boolean",
                        "source": "environment",
                        "confidence": "high",
                        "evidence_text": str(available_actions)[:300],
                        "is_confirmed": True,
                    },
                ],
            }
        )
        product_type = infer_product_type(task_instruction)
        if product_type:
            proposal["constraints"].append(
                _constraint("product_type", "contains", product_type, task_instruction, "hard")
            )
        price = infer_price_constraint(task_instruction)
        if price is not None:
            proposal["constraints"].append(
                _constraint("price", "less_equal", price, task_instruction, "hard")
            )
        color = infer_named_constraint(task_instruction, "color") or infer_token_constraint(
            task_instruction, COLORS
        )
        if color:
            proposal["constraints"].append(
                _constraint("color", "equals", color, task_instruction, "hard")
            )
        size = infer_named_constraint(task_instruction, "size") or infer_token_constraint(
            task_instruction, SIZES
        )
        if size:
            proposal["constraints"].append(
                _constraint("size", "equals", size, task_instruction, "hard")
            )
        brand = infer_brand_constraint(task_instruction)
        if brand:
            proposal["constraints"].append(
                _constraint("brand", "equals", brand, task_instruction, "hard")
            )
        for token in infer_other_constraints(task_instruction):
            proposal["constraints"].append(
                _constraint("description", "contains", token, task_instruction, "soft")
            )

        visible_products = infer_visible_products(available_actions)
        current = infer_current_product(observation, available_actions, page_type)
        for product_name in visible_products:
            proposal["entities"].append(_product_entity(product_name, observation, step_id, visible=True))
        if current:
            proposal["entities"].append(_product_entity(current, observation, step_id, visible=False))
        if last_action:
            proposal["entities"].append(
                {
                    "entity_id": "action:last",
                    "entity_type": "action",
                    "name": "last_action",
                    "source": "agent_action",
                    "confidence": "high",
                    "evidence_text": last_action,
                    "attributes": [
                        {
                            "name": "action_text",
                            "value": last_action,
                            "source": "agent_action",
                            "confidence": "high",
                            "evidence_text": last_action,
                            "is_confirmed": True,
                        }
                    ],
                }
            )
        return proposal


def _constraint(
    attribute_name: str,
    operator: str,
    expected_value: Any,
    evidence: str,
    strictness: str,
) -> dict[str, Any]:
    return {
        "target_entity_type": "product",
        "attribute_name": attribute_name,
        "operator": operator,
        "expected_value": expected_value,
        "source": "user_instruction",
        "evidence_text": evidence[:500],
        "strictness": strictness,
        "status": "unknown",
    }


def _product_entity(product_name: str, observation: str, step_id: int, visible: bool) -> dict[str, Any]:
    attrs: list[dict[str, Any]] = [
        {
            "name": "name",
            "value": product_name,
            "source": "observation",
            "confidence": "high",
            "evidence_text": product_name,
            "is_confirmed": True,
        },
        {
            "name": "visible",
            "value": visible,
            "value_type": "boolean",
            "source": "environment",
            "confidence": "high",
            "evidence_text": product_name,
            "is_confirmed": True,
        },
    ]
    price = infer_price_near_product(observation, product_name) or infer_price_constraint(observation)
    if price is not None:
        attrs.append(
            {
                "name": "price",
                "value": price,
                "value_type": "number",
                "source": "observation",
                "confidence": "medium",
                "evidence_text": observation[:500],
                "is_confirmed": True,
            }
        )
    for attr_name, options in (("color", COLORS), ("size", SIZES)):
        explicit = infer_named_constraint(observation, attr_name)
        value = explicit or infer_token_constraint(_window(observation, product_name), options)
        if value:
            attrs.append(
                {
                    "name": attr_name,
                    "value": value,
                    "source": "observation",
                    "confidence": "medium",
                    "evidence_text": observation[:500],
                    "is_confirmed": bool(explicit),
                }
            )
    brand = infer_brand_constraint(observation)
    if brand:
        attrs.append(
            {
                "name": "brand",
                "value": brand,
                "source": "observation",
                "confidence": "medium",
                "evidence_text": observation[:500],
                "is_confirmed": True,
            }
        )
    return {
        "entity_id": f"product:{product_name}",
        "entity_type": "product",
        "name": product_name,
        "source": "observation",
        "confidence": "medium",
        "evidence_text": product_name,
        "attributes": attrs,
        "updated_at_step": step_id,
    }


def infer_product_type(text: str) -> str:
    lowered = text.lower()
    patterns = [
        r"(?:find|buy|purchase|search for|get)\s+(?:me\s+)?(?:a|an|the)?\s*([a-z0-9 -]{2,120})",
        r"looking for\s+(?:a|an|the)?\s*([a-z0-9 -]{2,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            phrase = re.split(
                r"\b(?:under|below|less than|price|with|that|for|and)\b",
                match.group(1),
            )[0]
            return " ".join(phrase.split()[:5]).strip()
    return ""


def infer_price_constraint(text: str) -> float | None:
    lowered = text.lower()
    match = re.search(
        r"(?:under|below|less than|lower than|up to|max(?:imum)?|price lower than)\s*\$?\s*(\d+(?:\.\d+)?)",
        lowered,
    )
    if not match:
        match = re.search(r"\$\s*(\d+(?:\.\d+)?)", lowered)
    return float(match.group(1)) if match else None


def infer_price_near_product(text: str, product_name: str) -> float | None:
    window = _window(text, product_name)
    return infer_price_constraint(window)


def infer_token_constraint(text: str, options: set[str]) -> str:
    lowered = text.lower()
    for token in sorted(options, key=len, reverse=True):
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return token
    return ""


def infer_named_constraint(text: str, name: str) -> str:
    match = re.search(rf"{re.escape(name)}\s*:\s*([^,\[\]\n]+)", text.lower())
    if match:
        return match.group(1).strip(" .")
    return ""


def infer_brand_constraint(text: str) -> str:
    lowered = text.lower()
    match = re.search(r"(?:brand|by|from)\s+([a-z][a-z0-9-]{2,})", lowered)
    return match.group(1) if match else ""


def infer_other_constraints(text: str) -> list[str]:
    lowered = text.lower()
    markers = ["waterproof", "organic", "wireless", "rechargeable", "stainless", "cotton"]
    return [marker for marker in markers if marker in lowered]


def infer_page_type(observation: str, available_actions: dict[str, Any]) -> str:
    lowered = observation.lower()
    clickables = {str(item).lower() for item in available_actions.get("clickables", [])}
    if "score" in lowered and "done" in lowered:
        return "done_page"
    if "buy now" in clickables:
        return "product_page"
    if "description" in clickables or "features" in clickables or "reviews" in clickables:
        return "product_page"
    if "< prev" in clickables and clickables.issubset(NAV_CLICKABLES):
        return "detail_page"
    if clickables and any(item not in NAV_CLICKABLES for item in clickables):
        return "results_page"
    if available_actions.get("has_search_bar"):
        return "search_page"
    return "unknown"


def infer_visible_products(available_actions: dict[str, Any]) -> list[str]:
    products = []
    for item in available_actions.get("clickables", []):
        text = str(item).strip()
        if text and text.lower() not in NAV_CLICKABLES:
            products.append(text)
    return products


def infer_current_product(observation: str, available_actions: dict[str, Any], page_type: str) -> str:
    if page_type != "product_page":
        return ""
    lines = [line.strip(" []") for line in re.split(r"\[SEP\]|\n", observation) if line.strip()]
    skip = {"instruction", "price", "brand", "color", "size", "description", "features", "reviews"}
    for line in lines:
        lowered = line.lower()
        if lowered in skip or lowered in NAV_CLICKABLES or lowered.startswith("instruction"):
            continue
        if len(line) >= 3 and not lowered.startswith("button"):
            return line[:120]
    return ""


def _window(text: str, needle: str) -> str:
    index = text.lower().find(needle.lower())
    return text[index : index + 500] if index >= 0 else text[:500]


def _compact_observation(observation: str) -> str:
    return re.sub(r"\s+", " ", observation or "").strip()[:500]
