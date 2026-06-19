"""Risk-aware action routing for WebShop intervention mode."""

from __future__ import annotations

from typing import Any

from detectors.action_parser import parse_webshop_action
from policies.completion_policy import CompletionPolicy, build_requirement_query, first_clickable_product
from policies.shadow_policy import InterventionDecision
from state.entity_state import StateManager


class RiskAwareActionRouter:
    """Choose the executed action when intervention mode is enabled."""

    def __init__(self, completion_policy: CompletionPolicy | None = None):
        self.completion_policy = completion_policy or CompletionPolicy()

    def decide_before_action(
        self,
        pre_action_report: Any,
        state_manager: StateManager,
        raw_action: str,
        available_actions: dict[str, Any],
        action_history: list[dict[str, Any]],
        observation: str,
    ) -> InterventionDecision:
        should_route = bool(
            getattr(pre_action_report, "should_block_hypothetical", False)
            or getattr(pre_action_report, "missing_attributes", [])
            or getattr(pre_action_report, "unsupported_assumptions", [])
        )
        if not should_route:
            return InterventionDecision(
                allow_execute=True,
                raw_action=raw_action,
                executed_action=raw_action,
                would_block=False,
                would_complete=False,
                would_repair=False,
                reason="Intervention mode: action risk is acceptable.",
                metadata={"mode": "intervention", "changed_action": False},
            )

        executed_action, route_reason = self.completion_policy.choose_completion_action(
            pre_action_report=pre_action_report,
            state_manager=state_manager,
            available_actions=available_actions,
            action_history=action_history,
            observation=observation,
        )
        if route_reason == "completion_exhausted_on_product_page":
            return InterventionDecision(
                allow_execute=True,
                raw_action=raw_action,
                executed_action=raw_action,
                would_block=bool(getattr(pre_action_report, "should_block_hypothetical", False)),
                would_complete=bool(getattr(pre_action_report, "missing_attributes", [])),
                would_repair=False,
                hypothetical_completion_action=str(
                    getattr(pre_action_report, "hypothetical_completion_action", "")
                ),
                reason=(
                    "Intervention mode allowed raw action after supported completion actions were exhausted."
                ),
                metadata={
                    "mode": "intervention",
                    "changed_action": False,
                    "intervention_type": "completion_exhausted_allow_raw",
                    "route_reason": route_reason,
                    "risk_categories": list(getattr(pre_action_report, "risk_categories", [])),
                    "missing_attributes": list(getattr(pre_action_report, "missing_attributes", [])),
                    "unsupported_assumptions": list(
                        getattr(pre_action_report, "unsupported_assumptions", [])
                    ),
                },
            )
        if not executed_action:
            executed_action, route_reason = self._fallback_action(
                state_manager, raw_action, available_actions
            )

        if not executed_action:
            executed_action = raw_action
            route_reason = "no_safe_alternative_available"

        return InterventionDecision(
            allow_execute=True,
            raw_action=raw_action,
            executed_action=executed_action,
            would_block=bool(getattr(pre_action_report, "should_block_hypothetical", False)),
            would_complete=bool(getattr(pre_action_report, "missing_attributes", [])),
            would_repair=False,
            hypothetical_completion_action=str(
                getattr(pre_action_report, "hypothetical_completion_action", "")
            ),
            reason=f"Intervention mode routed action: {route_reason}.",
            metadata={
                "mode": "intervention",
                "changed_action": executed_action != raw_action,
                "intervention_type": "pre_action_completion_or_block",
                "route_reason": route_reason,
                "risk_categories": list(getattr(pre_action_report, "risk_categories", [])),
                "missing_attributes": list(getattr(pre_action_report, "missing_attributes", [])),
                "unsupported_assumptions": list(
                    getattr(pre_action_report, "unsupported_assumptions", [])
                ),
            },
        )

    def _fallback_action(
        self,
        state_manager: StateManager,
        raw_action: str,
        available_actions: dict[str, Any],
    ) -> tuple[str, str]:
        parsed = parse_webshop_action(raw_action)
        clickables = {str(item).lower() for item in available_actions.get("clickables", [])}
        if parsed.action_type == "click" and parsed.target.lower() == "buy now":
            for detail in ("description", "features", "reviews"):
                if detail in clickables:
                    return f"click[{detail}]", f"fallback_inspect_{detail}"
        if "< prev" in clickables:
            return "click[< prev]", "fallback_return_to_product"
        if available_actions.get("has_search_bar"):
            return f"search[{build_requirement_query(state_manager)}]", "fallback_search"
        product = first_clickable_product(available_actions)
        if product:
            return f"click[{product}]", "fallback_click_first_product"
        if "back to search" in clickables:
            return "click[back to search]", "fallback_back_to_search"
        return "", "fallback_unavailable"
