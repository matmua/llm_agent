"""Pre-action detector for action-centric WebShop shadow logs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from detectors.action_parser import parse_webshop_action
from state.action_state import ActionCentricState


@dataclass
class PreActionReport:
    pre_warning: bool = False
    pre_error: bool = False
    repair_trigger: bool = False
    categories: list[str] = field(default_factory=list)
    reason: str = ""
    required_attributes: list[str] = field(default_factory=list)
    known_attributes: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    conflicting_requirements: list[str] = field(default_factory=list)
    action_type: str = "unknown"
    invalid_streak: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pre_warning": self.pre_warning,
            "pre_error": self.pre_error,
            "repair_trigger": self.repair_trigger,
            "categories": self.categories,
            "reason": self.reason,
            "required_attributes": self.required_attributes,
            "known_attributes": self.known_attributes,
            "missing_requirements": self.missing_requirements,
            "conflicting_requirements": self.conflicting_requirements,
            "action_type": self.action_type,
            "invalid_streak": self.invalid_streak,
        }


class PreActionDetector:
    def detect(
        self,
        raw_action: str,
        available_actions: dict[str, Any],
        state: ActionCentricState,
        previous_reports: list[dict[str, Any]] | None = None,
    ) -> PreActionReport:
        previous_reports = previous_reports or []
        parsed = parse_webshop_action(raw_action)
        action = state.action_under_check
        categories: list[str] = []
        missing = list(action.missing_requirements)
        conflicts = list(action.conflicting_requirements)
        required, known = _required_and_known(state)

        invalid = _invalid_action(parsed, available_actions)
        invalid_streak = _invalid_streak(previous_reports) + 1 if invalid else 0
        if invalid:
            categories.append("invalid_action")

        if missing:
            categories.append("missing_evidence")
        if conflicts:
            categories.append("explicit_conflict")

        pre_warning = bool(categories)
        pre_error = False
        if conflicts:
            pre_error = True
        if invalid and (invalid_streak >= 2 or action.action_type == "commit"):
            pre_error = True
            categories.append("repeated_invalid_action" if invalid_streak >= 2 else "invalid_commit_action")

        repair_trigger = bool(pre_error and action.action_type == "commit")
        reason = _reason(invalid, invalid_streak, missing, conflicts, action.action_type)
        return PreActionReport(
            pre_warning=pre_warning,
            pre_error=pre_error,
            repair_trigger=repair_trigger,
            categories=_unique(categories),
            reason=reason,
            required_attributes=required,
            known_attributes=known,
            missing_requirements=missing,
            conflicting_requirements=conflicts,
            action_type=action.action_type,
            invalid_streak=invalid_streak,
        )


def _invalid_action(parsed: Any, available_actions: dict[str, Any]) -> bool:
    if not parsed.valid:
        return True
    if parsed.action_type == "search":
        return not bool(available_actions.get("has_search_bar"))
    if parsed.action_type == "click":
        clickables = {str(item).lower() for item in available_actions.get("clickables", [])}
        return parsed.target.lower() not in clickables
    return True


def _invalid_streak(previous_reports: list[dict[str, Any]]) -> int:
    count = 0
    for report in reversed(previous_reports):
        if "invalid_action" not in report.get("categories", []):
            break
        count += 1
    return count


def _required_and_known(state: ActionCentricState) -> tuple[list[str], list[str]]:
    required = []
    known = []
    for item in state.action_under_check.requires:
        required.append(item)
    for entity in state.entities.values():
        for name, attr in entity.attributes.items():
            if attr.status == "known":
                known.append(f"{entity.entity_id}.{name}")
    return _unique(required), _unique(known)


def _reason(
    invalid: bool,
    invalid_streak: int,
    missing: list[str],
    conflicts: list[str],
    action_type: str,
) -> str:
    parts: list[str] = []
    if invalid:
        if invalid_streak >= 2:
            parts.append("Repeated invalid action; promoted to error.")
        elif action_type == "commit":
            parts.append("Invalid final/commit action; promoted to error.")
        else:
            parts.append("Single invalid action; warning only.")
    if missing:
        parts.append("Missing evidence is warning only.")
    if conflicts:
        parts.append("Explicit conflict is an error.")
    if not parts:
        parts.append("No pre-action issue detected.")
    return " ".join(parts)


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
