"""Generic entity-state graph used by shadow detection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


VALID_SOURCES = {
    "user_instruction",
    "observation",
    "environment",
    "tool_result",
    "agent_action",
    "llm_proposal",
    "rule_extraction",
    "missing",
    "unknown",
}
VALID_CONFIDENCE = {"high", "medium", "low", "unknown"}
VALID_OPERATORS = {
    "equals",
    "contains",
    "less_equal",
    "greater_equal",
    "not_equals",
    "exists",
    "unknown",
}
VALID_CONSTRAINT_STATUS = {"satisfied", "violated", "missing_evidence", "unknown"}


@dataclass
class AttributeRecord:
    name: str
    value: Any
    value_type: str = "unknown"
    source: str = "unknown"
    confidence: str = "unknown"
    evidence_text: str = ""
    updated_at_step: int = 0
    is_required_for_goal: bool = False
    is_confirmed: bool = False


@dataclass
class Entity:
    entity_id: str
    entity_type: str
    aliases: list[str] = field(default_factory=list)
    attributes: dict[str, AttributeRecord] = field(default_factory=dict)
    source: str = "unknown"
    confidence: str = "unknown"
    evidence_text: str = ""
    updated_at_step: int = 0


@dataclass
class Constraint:
    constraint_id: str
    target_entity_type: str = ""
    target_entity_id: str = ""
    attribute_name: str = ""
    operator: str = "unknown"
    expected_value: Any = None
    source: str = "unknown"
    evidence_text: str = ""
    strictness: str = "unknown"
    status: str = "unknown"


@dataclass
class Relation:
    subject_entity: str
    relation_type: str
    object_entity: str
    source: str = "unknown"
    confidence: str = "unknown"
    evidence_text: str = ""


@dataclass
class GoalState:
    goal_id: str
    description: str
    required_entities: list[str] = field(default_factory=list)
    required_constraints: list[str] = field(default_factory=list)
    completion_action_type: str = ""
    status: str = "unknown"


@dataclass
class ActionRecord:
    action_text: str = ""
    action_type: str = ""
    action_target: str = ""
    referenced_entities: list[str] = field(default_factory=list)
    referenced_attributes: list[str] = field(default_factory=list)
    expected_delta: dict[str, Any] = field(default_factory=dict)
    source_supported: bool = True
    missing_preconditions: list[str] = field(default_factory=list)


@dataclass
class StateGraph:
    entities: dict[str, Entity] = field(default_factory=dict)
    constraints: dict[str, Constraint] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    goals: dict[str, GoalState] = field(default_factory=dict)
    current_observation_summary: str = ""
    action_state: ActionRecord | None = None
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    state_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)

    def validate(self) -> tuple[bool, list[str]]:
        errors: list[str] = []
        for entity_id, entity in self.entities.items():
            if not entity.entity_id:
                errors.append(f"entities.{entity_id}.entity_id is empty")
            if not entity.entity_type:
                errors.append(f"entities.{entity_id}.entity_type is empty")
            if entity.source not in VALID_SOURCES:
                errors.append(f"entities.{entity_id}.source is invalid: {entity.source}")
            if entity.confidence not in VALID_CONFIDENCE:
                errors.append(f"entities.{entity_id}.confidence is invalid: {entity.confidence}")
            for attr_name, record in entity.attributes.items():
                _validate_attribute(record, f"entities.{entity_id}.attributes.{attr_name}", errors)
        for constraint_id, constraint in self.constraints.items():
            if constraint.operator not in VALID_OPERATORS:
                errors.append(f"constraints.{constraint_id}.operator is invalid: {constraint.operator}")
            if constraint.status not in VALID_CONSTRAINT_STATUS:
                errors.append(f"constraints.{constraint_id}.status is invalid: {constraint.status}")
            if constraint.source not in VALID_SOURCES:
                errors.append(f"constraints.{constraint_id}.source is invalid: {constraint.source}")
        return len(errors) == 0, errors


def _validate_attribute(record: AttributeRecord, path: str, errors: list[str]) -> None:
    if record.source not in VALID_SOURCES:
        errors.append(f"{path}.source is invalid: {record.source}")
    if record.confidence not in VALID_CONFIDENCE:
        errors.append(f"{path}.confidence is invalid: {record.confidence}")
    if record.confidence == "high" and not record.evidence_text:
        errors.append(f"{path}.high_confidence_without_evidence")


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value
