"""Attribute completion actions for WebShop intervention mode."""

from __future__ import annotations

import re
from typing import Any

from state.entity_state import StateManager


DETAIL_ACTIONS = ("description", "features", "reviews")
NAV_ACTIONS = {"search", "next", "next >", "previous", "< prev", "back to search"}


class CompletionPolicy:
    """Generate an action that gathers missing evidence before final actions."""

    def choose_completion_action(
        self,
        pre_action_report: Any,
        state_manager: StateManager,
        available_actions: dict[str, Any],
        action_history: list[dict[str, Any]],
        observation: str,
    ) -> tuple[str, str]:
        clickables = _clickables(available_actions)
        if _page_type(state_manager) == "product_page":
            for action in DETAIL_ACTIONS:
                if action in clickables and not _history_has(action_history, f"click[{action}]"):
                    return f"click[{action}]", f"inspect_{action}_for_missing_attributes"
            return "", "completion_exhausted_on_product_page"

        if available_actions.get("has_search_bar"):
            return f"search[{build_requirement_query(state_manager)}]", "search_with_known_requirements"

        candidate = first_clickable_product(available_actions)
        if candidate:
            return f"click[{candidate}]", "inspect_visible_candidate"

        if "< prev" in clickables:
            return "click[< prev]", "return_to_product_after_detail_inspection"

        if "back to search" in clickables:
            return "click[back to search]", "return_to_search_for_completion"

        return "", "no_completion_action_available"


def build_requirement_query(state_manager: StateManager) -> str:
    req = state_manager.graph.task_requirement
    pieces: list[str] = []
    for key in ("product_type", "brand_constraint", "color_constraint", "size_constraint"):
        record = req.get(key)
        if record and record.value not in (None, "", []):
            pieces.extend(re.findall(r"[a-z0-9]+", str(record.value).lower()))
    for key in ("other_constraints", "required_attributes"):
        record = req.get(key)
        if record and isinstance(record.value, list):
            for item in record.value:
                pieces.extend(re.findall(r"[a-z0-9]+", str(item).lower()))
    stop = {"instruction", "find", "me", "for", "with", "and", "price", "lower", "than"}
    compact: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        if piece and piece not in stop and piece not in seen:
            seen.add(piece)
            compact.append(piece)
    return " ".join(compact[:8]) or "product"


def first_clickable_product(available_actions: dict[str, Any]) -> str:
    for item in available_actions.get("clickables", []):
        text = str(item).strip()
        if text and text.lower() not in NAV_ACTIONS | set(DETAIL_ACTIONS) | {"buy now"}:
            return text
    return ""


def _clickables(available_actions: dict[str, Any]) -> set[str]:
    return {str(item).strip().lower() for item in available_actions.get("clickables", [])}


def _history_has(action_history: list[dict[str, Any]], action: str) -> bool:
    target = action.lower()
    for item in action_history:
        if str(item.get("executed_action") or item.get("action") or "").lower() == target:
            return True
    return False


def _page_type(state_manager: StateManager) -> str:
    if state_manager.graph.page_state is None:
        return "unknown"
    return str(state_manager.graph.page_state.page_type.value)
