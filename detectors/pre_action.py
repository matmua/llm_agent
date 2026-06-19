"""Pre-action shadow detector for WebShop."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from agents.llm_client import LLMClient, MockLLMClient
from detectors.action_parser import parse_webshop_action
from state.entity_state import StateManager, expected_delta_for_action


@dataclass
class PreActionReport:
    post_error: bool = False
    risk_score: float = 0.0
    risk_level: str = "low"
    should_block_hypothetical: bool = False
    risk_categories: list[str] = field(default_factory=list)
    missing_attributes: list[str] = field(default_factory=list)
    unsupported_assumptions: list[str] = field(default_factory=list)
    expected_delta: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    hypothetical_completion_action: str = ""
    hypothetical_repair_plan: str = ""
    rule_checks: dict[str, Any] = field(default_factory=dict)
    llm_judge: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "should_block_hypothetical": self.should_block_hypothetical,
            "risk_categories": self.risk_categories,
            "missing_attributes": self.missing_attributes,
            "unsupported_assumptions": self.unsupported_assumptions,
            "expected_delta": self.expected_delta,
            "reason": self.reason,
            "hypothetical_completion_action": self.hypothetical_completion_action,
            "hypothetical_repair_plan": self.hypothetical_repair_plan,
            "rule_checks": self.rule_checks,
            "llm_judge": self.llm_judge,
        }


class PreActionDetector:
    def __init__(self, llm_judge: LLMClient | None = None, use_llm_judge: bool = False):
        self.llm_judge = llm_judge
        self.use_llm_judge = use_llm_judge

    def detect(
        self,
        task_instruction: str,
        observation: str,
        raw_action: str,
        available_actions: dict[str, Any],
        state_manager: StateManager,
        action_history: list[dict[str, Any]],
    ) -> PreActionReport:
        parsed = parse_webshop_action(raw_action)
        categories: list[str] = []
        missing: list[str] = []
        unsupported: list[str] = []
        rule_checks: dict[str, Any] = {
            "format_valid": parsed.valid,
            "action_type": parsed.action_type,
            "target": parsed.target,
        }

        clickables = {str(item).lower() for item in available_actions.get("clickables", [])}
        has_search_bar = bool(available_actions.get("has_search_bar"))

        if not parsed.valid:
            categories.append("invalid_action")
            rule_checks["format_error"] = parsed.error
        elif parsed.action_type == "search":
            if not has_search_bar:
                categories.append("invalid_action")
                rule_checks["search_bar_available"] = False
            if not parsed.target.strip():
                categories.append("invalid_action")
            product_type = state_manager.graph.task_requirement.get("product_type")
            if product_type is None or not product_type.value:
                missing.append("product_type")
                categories.append("missing_evidence")
            if product_type and product_type.value and not _has_overlap(parsed.target, str(product_type.value)):
                unsupported.append("search_query_not_grounded_in_product_type")
                categories.append("unsupported_inference")
        elif parsed.action_type == "click":
            target_lower = parsed.target.lower()
            if target_lower == "search":
                categories.append("invalid_action")
                rule_checks["search_is_not_clickable_action"] = True
            if target_lower not in clickables:
                categories.append("invalid_action")
                rule_checks["target_in_available_actions"] = False
            else:
                rule_checks["target_in_available_actions"] = True
            if target_lower == "buy now":
                page_type = (
                    state_manager.graph.page_state.page_type.value
                    if state_manager.graph.page_state
                    else "unknown"
                )
                if page_type != "product_page":
                    categories.append("premature_buy")
                hard_missing = state_manager.missing_hard_constraints_for_current_product()
                if hard_missing:
                    missing.extend(hard_missing)
                    categories.append("missing_evidence")
                    categories.append("missing_hard_constraint")
                    categories.append("missing_attribute")
                    categories.append("premature_buy")
                if _requires_fine_grained_evidence(task_instruction) and not _saw_detail_page(action_history):
                    categories.append("insufficient_evidence")
                    unsupported.append("fine_grained_attributes_not_verified")

        expected_delta = expected_delta_for_action(parsed.action_type, parsed.target.lower())
        categories = _unique(categories)
        missing = _unique(missing)
        unsupported = _unique(unsupported)
        risk_score, risk_level = _score(categories)
        reason = _reason(categories, missing, unsupported)
        report = PreActionReport(
            risk_score=risk_score,
            risk_level=risk_level,
            should_block_hypothetical=risk_level == "high",
            risk_categories=categories,
            missing_attributes=missing,
            unsupported_assumptions=unsupported,
            expected_delta=expected_delta,
            reason=reason,
            hypothetical_completion_action=_completion_hint(missing),
            hypothetical_repair_plan=_repair_hint(categories, missing),
            rule_checks=rule_checks,
        )
        if self.use_llm_judge and self.llm_judge and not isinstance(self.llm_judge, MockLLMClient):
            self._merge_llm_judge(
                report,
                task_instruction,
                observation,
                raw_action,
                available_actions,
                state_manager.snapshot(),
                action_history,
            )
        return report

    def _merge_llm_judge(
        self,
        report: PreActionReport,
        task_instruction: str,
        observation: str,
        raw_action: str,
        available_actions: dict[str, Any],
        state_snapshot: dict[str, Any],
        action_history: list[dict[str, Any]],
    ) -> None:
        prompt = {
            "task_instruction": task_instruction,
            "observation": observation,
            "raw_action": raw_action,
            "available_actions": available_actions,
            "state_graph": state_snapshot,
            "history": action_history[-6:],
            "rule_based_report": report.to_dict(),
        }
        response = self.llm_judge.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Judge WebShop action risk. Return JSON with risk_score, risk_level, "
                        "should_block_hypothetical, risk_categories, missing_attributes, "
                        "unsupported_assumptions, expected_delta, reason, "
                        "hypothetical_completion_action, hypothetical_repair_plan."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
            ],
            temperature=0.0,
            max_tokens=700,
        )
        report.llm_judge = response
        if response.get("_request_error") or response.get("_parse_error"):
            return
        llm_categories = [str(item) for item in response.get("risk_categories", []) if item]
        llm_missing = [str(item) for item in response.get("missing_attributes", []) if item]
        llm_unsupported = [str(item) for item in response.get("unsupported_assumptions", []) if item]
        report.risk_categories = _unique(report.risk_categories + llm_categories)
        report.missing_attributes = _unique(report.missing_attributes + llm_missing)
        report.unsupported_assumptions = _unique(report.unsupported_assumptions + llm_unsupported)
        try:
            report.risk_score = max(report.risk_score, float(response.get("risk_score", 0.0)))
        except (TypeError, ValueError):
            pass
        if response.get("risk_level") in {"low", "medium", "high"}:
            report.risk_level = _max_level(report.risk_level, str(response["risk_level"]))
        report.should_block_hypothetical = bool(
            report.should_block_hypothetical or response.get("should_block_hypothetical")
        )
        if response.get("reason"):
            report.reason = f"{report.reason} LLM judge: {response['reason']}".strip()
        report.hypothetical_completion_action = str(
            response.get("hypothetical_completion_action") or report.hypothetical_completion_action
        )
        report.hypothetical_repair_plan = str(
            response.get("hypothetical_repair_plan") or report.hypothetical_repair_plan
        )


def _has_overlap(a: str, b: str) -> bool:
    words_a = set(re.findall(r"[a-z0-9]+", a.lower()))
    words_b = set(re.findall(r"[a-z0-9]+", b.lower()))
    return bool(words_a & words_b)


def _requires_fine_grained_evidence(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("waterproof", "organic", "wireless", "rechargeable", "cotton", "stainless"))


def _saw_detail_page(action_history: list[dict[str, Any]]) -> bool:
    for item in action_history:
        action = str(item.get("executed_action") or item.get("action") or "").lower()
        if action in {"click[description]", "click[features]", "click[reviews]"}:
            return True
    return False


def _score(categories: list[str]) -> tuple[float, str]:
    high = {"invalid_action", "missing_hard_constraint", "premature_buy"}
    medium = {"unsupported_inference", "insufficient_evidence", "missing_evidence", "missing_attribute"}
    if any(item in high for item in categories):
        return 0.85, "high"
    if any(item in medium for item in categories):
        return 0.55, "medium"
    return 0.05, "low"


def _reason(categories: list[str], missing: list[str], unsupported: list[str]) -> str:
    if not categories:
        return "No rule-based risk detected."
    parts = [f"categories={categories}"]
    if missing:
        parts.append(f"missing={missing}")
    if unsupported:
        parts.append(f"unsupported={unsupported}")
    return "; ".join(parts)


def _completion_hint(missing: list[str]) -> str:
    if not missing:
        return ""
    return "Inspect product details or search/filter to verify: " + ", ".join(missing)


def _repair_hint(categories: list[str], missing: list[str]) -> str:
    if "invalid_action" in categories:
        return "Phase 2 could replace the action with a visible WebShop action."
    if missing:
        return "Phase 2 could complete missing entity attributes before buying."
    if categories:
        return "Phase 2 could request one safer action revision."
    return ""


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _max_level(a: str, b: str) -> str:
    rank = {"low": 0, "medium": 1, "high": 2}
    return a if rank.get(a, 0) >= rank.get(b, 0) else b
