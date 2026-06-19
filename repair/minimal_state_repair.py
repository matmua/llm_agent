"""Minimal post-action repair for WebShop intervention mode."""

from __future__ import annotations

from typing import Any

from policies.completion_policy import build_requirement_query, first_clickable_product
from policies.shadow_policy import RepairDecision
from repair.checkpoint_manager import CheckpointManager
from state.entity_state import StateManager


class MinimalStateRepair:
    """Repair only contaminated entity attributes and optionally queue one action."""

    def repair_after_action(
        self,
        post_action_report: Any,
        state_manager: StateManager,
        checkpoint_manager: CheckpointManager,
        checkpoint_id: str,
        available_actions: dict[str, Any],
        action_history: list[dict[str, Any]],
        done: bool,
    ) -> RepairDecision:
        categories = list(getattr(post_action_report, "error_categories", []))
        contaminated = list(getattr(post_action_report, "potential_contaminated_slots", []))
        if not categories:
            return RepairDecision(
                repair_needed=False,
                repair_executed=False,
                reason="No post-action error detected.",
                metadata={"checkpoint_id": checkpoint_id},
            )

        repaired_slots = state_manager.repair_candidate_slots(contaminated, step_id=len(action_history))
        repair_action = ""
        repair_reason = "state_slots_repaired"

        if not done:
            repair_action, repair_reason = self._choose_repair_action(
                categories=categories,
                state_manager=state_manager,
                available_actions=available_actions,
                action_history=action_history,
            )

        checkpoint = checkpoint_manager.get(checkpoint_id)
        return RepairDecision(
            repair_needed=True,
            repair_executed=bool(repair_action),
            reason=(
                f"Minimal repair considered categories={categories}; "
                f"action_reason={repair_reason}."
            ),
            hypothetical_repair_plan=str(getattr(post_action_report, "hypothetical_repair_plan", "")),
            repair_action=repair_action,
            contaminated_slots=contaminated,
            repaired_slots=repaired_slots,
            checkpoint_id=checkpoint_id,
            metadata={
                "checkpoint_found": checkpoint is not None,
                "repair_reason": repair_reason,
                "done": done,
            },
        )

    def _choose_repair_action(
        self,
        categories: list[str],
        state_manager: StateManager,
        available_actions: dict[str, Any],
        action_history: list[dict[str, Any]],
    ) -> tuple[str, str]:
        clickables = {str(item).lower() for item in available_actions.get("clickables", [])}
        if "action_no_effect" in categories or "unexpected_transition" in categories:
            if "< prev" in clickables:
                return "click[< prev]", "return_to_product_after_unexpected_transition"
            if available_actions.get("has_search_bar"):
                return f"search[{build_requirement_query(state_manager)}]", "retry_search_after_no_effect"
            product = first_clickable_product(available_actions)
            if product:
                return f"click[{product}]", "retry_with_visible_product"
        if "constraint_conflict" in categories or "potential_preventable_failure" in categories:
            if "< prev" in clickables:
                return "click[< prev]", "return_to_product_after_constraint_conflict"
            if "back to search" in clickables:
                return "click[back to search]", "back_to_search_after_constraint_conflict"
            if available_actions.get("has_search_bar"):
                return f"search[{build_requirement_query(state_manager)}]", "search_after_constraint_conflict"
        for detail in ("description", "features", "reviews"):
            if detail in clickables and not _history_has(action_history, f"click[{detail}]"):
                return f"click[{detail}]", f"inspect_{detail}_after_error"
        return "", "no_repair_action_available"


def _history_has(action_history: list[dict[str, Any]], action: str) -> bool:
    target = action.lower()
    for item in action_history:
        if str(item.get("executed_action") or item.get("action") or "").lower() == target:
            return True
    return False
