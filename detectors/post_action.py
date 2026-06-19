"""Post-action delta verifier for WebShop."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from detectors.action_parser import parse_webshop_action


@dataclass
class PostActionReport:
    post_error: bool = False
    error_categories: list[str] = field(default_factory=list)
    warning_categories: list[str] = field(default_factory=list)
    observed_delta: dict[str, Any] = field(default_factory=dict)
    expected_delta: dict[str, Any] = field(default_factory=dict)
    delta_match: bool = True
    state_conflicts: list[dict[str, Any]] = field(default_factory=list)
    constraint_checks: dict[str, Any] = field(default_factory=dict)
    potential_contaminated_slots: list[str] = field(default_factory=list)
    hypothetical_repair_needed: bool = False
    hypothetical_repair_plan: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_error": self.post_error,
            "error_categories": self.error_categories,
            "warning_categories": self.warning_categories,
            "observed_delta": self.observed_delta,
            "expected_delta": self.expected_delta,
            "delta_match": self.delta_match,
            "state_conflicts": self.state_conflicts,
            "constraint_checks": self.constraint_checks,
            "potential_contaminated_slots": self.potential_contaminated_slots,
            "hypothetical_repair_needed": self.hypothetical_repair_needed,
            "hypothetical_repair_plan": self.hypothetical_repair_plan,
            "reason": self.reason,
        }


class PostActionDeltaVerifier:
    def verify(
        self,
        task_instruction: str,
        observation_before: str,
        observation_after: str,
        raw_action: str,
        pre_action_report: dict[str, Any],
        state_before: dict[str, Any],
        state_after: dict[str, Any],
        reward: float,
        done: bool,
        info: Any,
    ) -> PostActionReport:
        parsed = parse_webshop_action(raw_action)
        expected = dict(pre_action_report.get("expected_delta") or {})
        observed = {
            "page_type_before": _page_type_from_state(state_before),
            "page_type_after": _page_type_from_state(state_after),
            "done": done,
            "reward": reward,
            "info": info,
            "observation_similarity": _similarity(observation_before, observation_after),
        }
        categories: list[str] = []
        warnings: list[str] = []
        conflicts: list[dict[str, Any]] = []
        contaminated: list[str] = []

        expected_page = expected.get("expected_page_type")
        if expected.get("expected_new_information") and observed["observation_similarity"] > 0.985:
            categories.extend(["no_effect", "action_no_effect"])
        if expected_page and expected_page != "unknown":
            actual_page = str(observed["page_type_after"])
            allowed = _allowed_page_matches(expected_page, actual_page, done)
            if not allowed:
                categories.append("unexpected_transition")
        if parsed.action_type == "click" and parsed.target.lower() == "buy now":
            if not done:
                categories.append("unexpected_transition")
            if reward <= 0 and (
                pre_action_report.get("risk_level") == "high"
                or "missing_attribute" in pre_action_report.get("risk_categories", [])
                or "missing_evidence" in pre_action_report.get("risk_categories", [])
                or "missing_hard_constraint" in pre_action_report.get("risk_categories", [])
                or "premature_buy" in pre_action_report.get("risk_categories", [])
            ):
                categories.extend(["preventable_failure", "potential_preventable_failure"])

        constraint_checks = _constraint_findings(task_instruction, observation_after, state_after)
        explicit_conflicts = constraint_checks["explicit_conflicts"]
        missing_evidence = constraint_checks["missing_evidence"]
        if explicit_conflicts:
            conflicts.extend(explicit_conflicts)
            categories.extend(["explicit_conflict", "constraint_conflict"])
            contaminated.extend(
                [
                    f"current_product.{conflict.get('attribute')}"
                    for conflict in explicit_conflicts
                    if conflict.get("attribute")
                ]
            )
        if missing_evidence:
            warnings.append("missing_evidence")
            categories.append("missing_evidence")
        unsupported_slots = _unsupported_state_updates(state_after)
        if unsupported_slots:
            categories.append("unsupported_state_update")
            contaminated.extend(unsupported_slots)

        categories = _unique(categories)
        warnings = _unique(warnings)
        strong_categories = {
            "explicit_conflict",
            "constraint_conflict",
            "unexpected_transition",
            "no_effect",
            "action_no_effect",
            "preventable_failure",
            "potential_preventable_failure",
            "unsupported_state_update",
        }
        post_error = any(category in strong_categories for category in categories)
        reason = (
            "No post-action delta error detected."
            if not categories
            else f"categories={categories}; warnings={warnings}"
        )
        return PostActionReport(
            post_error=post_error,
            error_categories=categories,
            warning_categories=warnings,
            observed_delta=observed,
            expected_delta=expected,
            delta_match=not post_error,
            state_conflicts=conflicts,
            constraint_checks=constraint_checks,
            potential_contaminated_slots=contaminated,
            hypothetical_repair_needed=post_error,
            hypothetical_repair_plan=_repair_plan(categories),
            reason=reason,
        )


def _page_type_from_state(state: dict[str, Any]) -> str:
    try:
        return str(state["page_state"]["page_type"]["value"])
    except (KeyError, TypeError):
        return "unknown"


def _similarity(a: str, b: str) -> float:
    compact_a = re.sub(r"\s+", " ", a or "").strip()
    compact_b = re.sub(r"\s+", " ", b or "").strip()
    if not compact_a and not compact_b:
        return 1.0
    return difflib.SequenceMatcher(None, compact_a, compact_b).ratio()


def _allowed_page_matches(expected_page: str, actual_page: str, done: bool = False) -> bool:
    if expected_page == actual_page:
        return True
    if expected_page == "detail_page" and actual_page in {"product_page", "detail_page"}:
        return True
    if expected_page == "done_page" and (actual_page == "done_page" or done):
        return True
    return False


def _constraint_findings(
    task_instruction: str, observation_after: str, state_after: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    explicit_conflicts: list[dict[str, Any]] = []
    missing_evidence: list[dict[str, Any]] = []
    requirements = state_after.get("task_requirement", {}) if isinstance(state_after, dict) else {}
    lowered_obs = observation_after.lower()
    price_req = _attr_value(requirements, "price_constraint")
    if price_req is not None:
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", lowered_obs)
        if price_match and float(price_match.group(1)) > float(price_req):
            explicit_conflicts.append(
                {
                    "category": "explicit_conflict",
                    "attribute": "price",
                    "required": price_req,
                    "observed": float(price_match.group(1)),
                }
            )
        elif not price_match and _is_final_or_product_state(lowered_obs, state_after):
            missing_evidence.append(
                {"attribute": "price", "required": price_req, "observed": "not_evidenced"}
            )
    for name, plain_name in (
        ("color_constraint", "color"),
        ("brand_constraint", "brand"),
        ("size_constraint", "size"),
    ):
        value = _attr_value(requirements, name)
        if not value:
            continue
        explicit_value = _explicit_named_value(observation_after, plain_name)
        if explicit_value and str(explicit_value).lower() != str(value).lower():
            explicit_conflicts.append(
                {
                    "category": "explicit_conflict",
                    "attribute": plain_name,
                    "required": value,
                    "observed": explicit_value,
                }
            )
        elif str(value).lower() not in lowered_obs and _is_final_or_product_state(lowered_obs, state_after):
            missing_evidence.append(
                {"attribute": plain_name, "required": value, "observed": "not_evidenced"}
            )
    return {"explicit_conflicts": explicit_conflicts, "missing_evidence": missing_evidence}


def _explicit_named_value(text: str, attribute: str) -> str:
    match = re.search(rf"\b{re.escape(attribute)}\s*:\s*([^,\[\]\n]+)", text.lower())
    if match:
        return match.group(1).strip(" .")
    return ""


def _is_final_or_product_state(lowered_obs: str, state_after: dict[str, Any]) -> bool:
    return "buy now" in lowered_obs or _page_type_from_state(state_after) == "product_page"


def _attr_value(records: dict[str, Any], name: str) -> Any:
    record = records.get(name)
    if isinstance(record, dict):
        return record.get("value")
    return None


def _unsupported_state_updates(state_after: dict[str, Any]) -> list[str]:
    slots: list[str] = []
    requirements = state_after.get("task_requirement", {}) if isinstance(state_after, dict) else {}
    for key, record in requirements.items():
        if isinstance(record, dict) and record.get("confidence") == "high" and record.get("source") == "agent_inference":
            slots.append(key)
    generic = state_after.get("generic_state_graph", {}) if isinstance(state_after, dict) else {}
    for entity_id, entity in generic.get("entities", {}).items():
        for attr_name, record in entity.get("attributes", {}).items():
            if (
                isinstance(record, dict)
                and record.get("confidence") == "high"
                and not record.get("evidence_text")
            ):
                slots.append(f"generic.{entity_id}.{attr_name}")
    return slots


def _repair_plan(categories: list[str]) -> str:
    if "no_effect" in categories or "action_no_effect" in categories or "unexpected_transition" in categories:
        return "Phase 2 could retry with a visible action or roll back to the previous page checkpoint."
    if "explicit_conflict" in categories or "constraint_conflict" in categories:
        return "Phase 2 could repair contaminated product attributes and search for a better candidate."
    if "preventable_failure" in categories or "potential_preventable_failure" in categories:
        return "Phase 2 could require missing-attribute completion before final purchase."
    if categories:
        return "Phase 2 placeholder repair would be considered here."
    return ""


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
