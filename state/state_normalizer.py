"""Normalize and merge LLM/domain state proposals into a generic StateGraph."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from state.base_state import AttributeRecord, Constraint, Entity, GoalState, Relation, StateGraph


SOURCE_RANK = {
    "missing": 0,
    "unknown": 0,
    "llm_proposal": 1,
    "agent_action": 1,
    "rule_extraction": 2,
    "tool_result": 3,
    "environment": 4,
    "observation": 4,
    "user_instruction": 5,
}
CONFIDENCE_RANK = {"unknown": 0, "low": 1, "medium": 2, "high": 3}


@dataclass
class MergeResult:
    graph: StateGraph
    delta: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class StateNormalizer:
    def normalize(self, proposal: dict[str, Any], step_id: int) -> MergeResult:
        graph = StateGraph()
        delta = {
            "entities_added": 0,
            "attributes_added": 0,
            "constraints_added": 0,
            "goals_added": 0,
            "relations_added": 0,
            "conflicts_added": 0,
        }
        errors: list[str] = []
        graph.current_observation_summary = str(
            proposal.get("current_observation_summary") or proposal.get("observation_summary") or ""
        )[:500]

        for idx, item in enumerate(_as_list(proposal.get("entities"))):
            entity = _normalize_entity(item, idx, step_id, errors)
            if entity is None:
                continue
            graph.entities[entity.entity_id] = entity
            delta["entities_added"] += 1
            delta["attributes_added"] += len(entity.attributes)

        for idx, item in enumerate(_as_list(proposal.get("constraints"))):
            constraint = _normalize_constraint(item, idx, errors)
            if constraint is None:
                continue
            graph.constraints[constraint.constraint_id] = constraint
            delta["constraints_added"] += 1

        for idx, item in enumerate(_as_list(proposal.get("relations"))):
            relation = _normalize_relation(item, errors)
            if relation is None:
                continue
            graph.relations.append(relation)
            delta["relations_added"] += 1

        for idx, item in enumerate(_as_list(proposal.get("goals"))):
            goal = _normalize_goal(item, idx, errors)
            if goal is None:
                continue
            graph.goals[goal.goal_id] = goal
            delta["goals_added"] += 1

        graph.state_history.append({"event_type": "normalize_proposal", "step_id": step_id, **delta})
        valid, validation_errors = graph.validate()
        if not valid:
            errors.extend(validation_errors)
        return MergeResult(graph=graph, delta=delta, errors=errors)

    def merge(self, base: StateGraph, proposal: StateGraph, step_id: int) -> MergeResult:
        delta = {
            "entities_added": 0,
            "attributes_added": 0,
            "attributes_updated": 0,
            "constraints_added": 0,
            "constraints_updated": 0,
            "goals_added": 0,
            "relations_added": 0,
            "conflicts_added": 0,
        }
        for entity_id, incoming in proposal.entities.items():
            existing = base.entities.get(entity_id)
            if existing is None:
                base.entities[entity_id] = incoming
                delta["entities_added"] += 1
                delta["attributes_added"] += len(incoming.attributes)
                continue
            for alias in incoming.aliases:
                if alias not in existing.aliases:
                    existing.aliases.append(alias)
            for attr_name, incoming_attr in incoming.attributes.items():
                existing_attr = existing.attributes.get(attr_name)
                if existing_attr is None:
                    existing.attributes[attr_name] = incoming_attr
                    delta["attributes_added"] += 1
                    continue
                if _should_replace(existing_attr, incoming_attr):
                    if _is_conflict(existing_attr.value, incoming_attr.value):
                        base.conflicts.append(
                            {
                                "type": "attribute_conflict",
                                "entity_id": entity_id,
                                "attribute": attr_name,
                                "old_value": existing_attr.value,
                                "new_value": incoming_attr.value,
                                "old_source": existing_attr.source,
                                "new_source": incoming_attr.source,
                                "evidence_text": incoming_attr.evidence_text,
                                "step_id": step_id,
                            }
                        )
                        delta["conflicts_added"] += 1
                    existing.attributes[attr_name] = incoming_attr
                    delta["attributes_updated"] += 1
                elif _is_conflict(existing_attr.value, incoming_attr.value) and _both_confident(
                    existing_attr, incoming_attr
                ):
                    base.conflicts.append(
                        {
                            "type": "attribute_conflict_retained_existing",
                            "entity_id": entity_id,
                            "attribute": attr_name,
                            "old_value": existing_attr.value,
                            "new_value": incoming_attr.value,
                            "old_source": existing_attr.source,
                            "new_source": incoming_attr.source,
                            "evidence_text": incoming_attr.evidence_text,
                            "step_id": step_id,
                        }
                    )
                    delta["conflicts_added"] += 1

        for constraint_id, incoming in proposal.constraints.items():
            existing = base.constraints.get(constraint_id)
            if existing is None:
                base.constraints[constraint_id] = incoming
                delta["constraints_added"] += 1
                continue
            if existing.source == "user_instruction" and existing.strictness == "hard":
                continue
            if SOURCE_RANK.get(incoming.source, 0) >= SOURCE_RANK.get(existing.source, 0):
                base.constraints[constraint_id] = incoming
                delta["constraints_updated"] += 1

        for relation in proposal.relations:
            if relation not in base.relations:
                base.relations.append(relation)
                delta["relations_added"] += 1

        for goal_id, goal in proposal.goals.items():
            if goal_id not in base.goals:
                base.goals[goal_id] = goal
                delta["goals_added"] += 1

        if proposal.current_observation_summary:
            base.current_observation_summary = proposal.current_observation_summary
        base.state_history.append({"event_type": "merge_proposal", "step_id": step_id, **delta})
        return MergeResult(graph=base, delta=delta, errors=[])


def _normalize_entity(item: Any, idx: int, step_id: int, errors: list[str]) -> Entity | None:
    if not isinstance(item, dict):
        errors.append(f"entities.{idx} is not an object")
        return None
    entity_type = str(item.get("entity_type") or item.get("type") or "unknown").strip() or "unknown"
    name = str(item.get("name") or item.get("entity_id") or f"{entity_type}_{idx}").strip()
    entity_id = _slug(str(item.get("entity_id") or f"{entity_type}:{name}"))
    source = _source(item.get("source") or "llm_proposal")
    confidence = _confidence(item.get("confidence") or "medium", item.get("evidence_text"))
    entity = Entity(
        entity_id=entity_id,
        entity_type=entity_type,
        aliases=[alias for alias in [name, *_as_list(item.get("aliases"))] if alias],
        source=source,
        confidence=confidence,
        evidence_text=str(item.get("evidence_text") or "")[:500],
        updated_at_step=step_id,
    )
    for attr_idx, attr in enumerate(_as_list(item.get("attributes"))):
        record = _normalize_attribute(attr, attr_idx, step_id, errors)
        if record:
            entity.attributes[record.name] = record
    return entity


def _normalize_attribute(
    item: Any, idx: int, step_id: int, errors: list[str]
) -> AttributeRecord | None:
    if not isinstance(item, dict):
        errors.append(f"attributes.{idx} is not an object")
        return None
    name = str(item.get("name") or "").strip()
    if not name:
        errors.append(f"attributes.{idx}.name is empty")
        return None
    evidence = str(item.get("evidence_text") or "")[:500]
    return AttributeRecord(
        name=name,
        value=item.get("value"),
        value_type=str(item.get("value_type") or _infer_value_type(item.get("value"))),
        source=_source(item.get("source") or "llm_proposal"),
        confidence=_confidence(item.get("confidence") or "medium", evidence),
        evidence_text=evidence,
        updated_at_step=step_id,
        is_required_for_goal=bool(item.get("is_required_for_goal", False)),
        is_confirmed=bool(item.get("is_confirmed", bool(evidence))),
    )


def _normalize_constraint(item: Any, idx: int, errors: list[str]) -> Constraint | None:
    if not isinstance(item, dict):
        errors.append(f"constraints.{idx} is not an object")
        return None
    attribute_name = str(item.get("attribute_name") or item.get("name") or "").strip()
    if not attribute_name:
        errors.append(f"constraints.{idx}.attribute_name is empty")
        return None
    target_entity_type = str(item.get("target_entity_type") or item.get("entity_type") or "").strip()
    target_entity_id = str(item.get("target_entity_id") or "").strip()
    expected_value = item.get("expected_value")
    operator = _operator(item.get("operator") or "unknown")
    constraint_id = _slug(
        str(
            item.get("constraint_id")
            or f"{target_entity_type or target_entity_id or 'entity'}:{attribute_name}:{operator}:{expected_value}"
        )
    )
    return Constraint(
        constraint_id=constraint_id,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        attribute_name=attribute_name,
        operator=operator,
        expected_value=expected_value,
        source=_source(item.get("source") or "llm_proposal"),
        evidence_text=str(item.get("evidence_text") or "")[:500],
        strictness=str(item.get("strictness") or "unknown"),
        status=str(item.get("status") or "unknown"),
    )


def _normalize_relation(item: Any, errors: list[str]) -> Relation | None:
    if not isinstance(item, dict):
        errors.append("relation is not an object")
        return None
    return Relation(
        subject_entity=str(item.get("subject_entity") or ""),
        relation_type=str(item.get("relation_type") or "related_to"),
        object_entity=str(item.get("object_entity") or ""),
        source=_source(item.get("source") or "llm_proposal"),
        confidence=_confidence(item.get("confidence") or "medium", item.get("evidence_text")),
        evidence_text=str(item.get("evidence_text") or "")[:500],
    )


def _normalize_goal(item: Any, idx: int, errors: list[str]) -> GoalState | None:
    if not isinstance(item, dict):
        errors.append(f"goals.{idx} is not an object")
        return None
    description = str(item.get("description") or "").strip()
    if not description:
        errors.append(f"goals.{idx}.description is empty")
        return None
    return GoalState(
        goal_id=_slug(str(item.get("goal_id") or f"goal:{idx}:{description[:40]}")),
        description=description,
        required_entities=[str(value) for value in _as_list(item.get("required_entities"))],
        required_constraints=[str(value) for value in _as_list(item.get("required_constraints"))],
        completion_action_type=str(item.get("completion_action_type") or ""),
        status=str(item.get("status") or "unknown"),
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _source(value: Any) -> str:
    text = str(value or "unknown")
    return text if text in SOURCE_RANK else "unknown"


def _confidence(value: Any, evidence: Any = "") -> str:
    text = str(value or "unknown")
    if text not in CONFIDENCE_RANK:
        text = "unknown"
    if text == "high" and not str(evidence or ""):
        return "low"
    return text


def _operator(value: Any) -> str:
    text = str(value or "unknown")
    valid = {"equals", "contains", "less_equal", "greater_equal", "not_equals", "exists", "unknown"}
    return text if text in valid else "unknown"


def _infer_value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "list"
    if value is None:
        return "unknown"
    return "string"


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "_", value.strip().lower()).strip("_") or "unknown"


def _should_replace(existing: AttributeRecord, incoming: AttributeRecord) -> bool:
    incoming_source = SOURCE_RANK.get(incoming.source, 0)
    existing_source = SOURCE_RANK.get(existing.source, 0)
    incoming_conf = CONFIDENCE_RANK.get(incoming.confidence, 0)
    existing_conf = CONFIDENCE_RANK.get(existing.confidence, 0)
    if existing.source == "user_instruction" and existing.is_required_for_goal:
        return False
    if incoming_source > existing_source:
        return True
    if incoming_source == existing_source and incoming_conf >= existing_conf:
        return True
    return False


def _is_conflict(a: Any, b: Any) -> bool:
    if a in (None, "", []):
        return False
    if b in (None, "", []):
        return False
    return str(a).lower() != str(b).lower()


def _both_confident(a: AttributeRecord, b: AttributeRecord) -> bool:
    return CONFIDENCE_RANK.get(a.confidence, 0) >= 2 and CONFIDENCE_RANK.get(b.confidence, 0) >= 2
