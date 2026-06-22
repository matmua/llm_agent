"""Action-centric state for WebShop shadow detection."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from detectors.action_parser import parse_webshop_action


ATTRIBUTE_NAMES = ("product_type", "color", "size", "brand", "price_max")
DETAIL_ACTIONS = {"description", "features", "reviews", "attributes"}
BACKTRACK_ACTIONS = {"back to search", "< prev", "prev", "previous"}


@dataclass
class Attribute:
    name: str
    value: Any
    status: str
    evidence: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"known", "unknown", "conflict"}:
            self.status = "unknown"
        if not self.evidence and self.status == "known":
            self.status = "unknown"


@dataclass
class Entity:
    entity_id: str
    type: str
    name: str
    attributes: dict[str, Attribute] = field(default_factory=dict)


@dataclass
class Relation:
    subject: str
    relation: str
    object: str
    status: str
    evidence: str = ""

    def __post_init__(self) -> None:
        if self.relation not in {"satisfies", "conflicts_with", "supports", "requires", "belongs_to", "matches"}:
            self.relation = "supports"
        if self.status not in {"supported", "missing_evidence", "conflict", "unknown"}:
            self.status = "unknown"


@dataclass
class ActionUnderCheck:
    action: str
    action_type: str
    target_entity: str
    requires: list[str] = field(default_factory=list)
    satisfied_requirements: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    conflicting_requirements: list[str] = field(default_factory=list)
    pre_warning: bool = False
    pre_error: bool = False
    repair_trigger: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        if self.action_type not in {"explore", "inspect", "commit", "backtrack", "unknown"}:
            self.action_type = "unknown"


@dataclass
class PostCheck:
    expected_effect: list[str] = field(default_factory=list)
    observed_effect: list[str] = field(default_factory=list)
    matched: bool = True
    post_warning: bool = False
    post_error: bool = False
    repair_trigger: bool = False
    reason: str = ""


@dataclass
class ActionCentricState:
    step_id: int
    task: str
    entities: dict[str, Entity]
    relations: list[Relation]
    action_under_check: ActionUnderCheck
    post_check: PostCheck | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(self)


def build_fallback_state(
    task_instruction: str,
    observation: str,
    available_actions: dict[str, Any],
    raw_action: str,
    step_id: int,
    post_check: PostCheck | None = None,
) -> ActionCentricState:
    request_attrs = extract_request_attributes(task_instruction)
    product_attrs = extract_current_product_attributes(observation)
    action_type = classify_action(raw_action)
    target_entity = _target_entity(action_type, raw_action)

    entities = {
        "request": Entity(
            entity_id="request",
            type="user_request",
            name="user request",
            attributes=request_attrs,
        )
    }
    if is_product_page(observation, available_actions) or product_attrs:
        entities["current_product"] = Entity(
            entity_id="current_product",
            type="product",
            name=extract_product_name(observation) or "current product",
            attributes=product_attrs,
        )

    relations = build_relations(request_attrs, product_attrs)
    requires = requirements_for_action(action_type, request_attrs, bool(product_attrs))
    if action_type == "commit":
        satisfied = [rel.subject + " satisfies " + rel.object for rel in relations if rel.status == "supported"]
        missing = [rel.subject + " satisfies " + rel.object for rel in relations if rel.status == "missing_evidence"]
        conflicts = [rel.subject + " conflicts_with " + rel.object for rel in relations if rel.status == "conflict"]
    else:
        satisfied = []
        missing = []
        conflicts = []

    if action_type == "commit" and "current_product exists" in requires and product_attrs:
        satisfied.insert(0, "current_product exists")
    elif action_type == "commit" and "current_product exists" in requires:
        missing.insert(0, "current_product exists")

    action_state = ActionUnderCheck(
        action=raw_action,
        action_type=action_type,
        target_entity=target_entity,
        requires=requires,
        satisfied_requirements=_unique(satisfied),
        missing_requirements=_unique(missing),
        conflicting_requirements=_unique(conflicts),
        pre_warning=bool(missing or conflicts),
        pre_error=bool(conflicts),
        repair_trigger=bool(conflicts and action_type == "commit"),
        reason=_action_reason(action_type, missing, conflicts),
    )
    return ActionCentricState(
        step_id=step_id,
        task=task_instruction,
        entities=entities,
        relations=relations,
        action_under_check=action_state,
        post_check=post_check,
    )


def extract_request_attributes(task_instruction: str) -> dict[str, Attribute]:
    text = task_instruction.replace("Instruction:", "").strip()
    lowered = text.lower()
    attrs: dict[str, Attribute] = {}
    product_type = _extract_product_type(text)
    attrs["product_type"] = _attribute("product_type", product_type, product_type, product_type)
    color = _extract_named_or_with(text, "color")
    attrs["color"] = _attribute("color", color, color, color)
    size = _extract_named_or_with(text, "size")
    attrs["size"] = _attribute("size", size, size, size)
    brand = _extract_named_or_with(text, "brand")
    attrs["brand"] = _attribute("brand", brand, brand, brand)
    price = _extract_price_limit(lowered)
    attrs["price_max"] = _attribute("price_max", price, price, f"price lower than {price}" if price is not None else "")
    return attrs


def extract_current_product_attributes(observation: str) -> dict[str, Attribute]:
    attrs: dict[str, Attribute] = {}
    lowered = observation.lower()
    price = _extract_price_value(observation)
    attrs["price"] = _attribute("price", price, price, f"${price}" if price is not None else "")
    for name in ("color", "size", "brand"):
        value = _extract_explicit_named(observation, name)
        attrs[name] = _attribute(name, value, value, f"{name}: {value}" if value else "")
    product_type = extract_product_name(observation)
    attrs["product_type"] = _attribute("product_type", product_type, product_type, product_type)
    if "buy now" in lowered and not attrs["product_type"].value:
        attrs["product_type"].evidence = "product page contains buy now"
    return attrs


def build_relations(
    request_attrs: dict[str, Attribute],
    product_attrs: dict[str, Attribute],
) -> list[Relation]:
    relations: list[Relation] = []
    for request_name, product_name in (
        ("price_max", "price"),
        ("color", "color"),
        ("size", "size"),
        ("brand", "brand"),
        ("product_type", "product_type"),
    ):
        req = request_attrs.get(request_name)
        if req is None or req.status != "known":
            continue
        prod = product_attrs.get(product_name)
        if prod is None or prod.status != "known":
            relations.append(
                Relation(
                    subject=f"current_product.{product_name}",
                    relation="satisfies",
                    object=f"request.{request_name}",
                    status="missing_evidence",
                    evidence=f"{request_name} is required but not observed",
                )
            )
            continue
        status, evidence = _compare_requirement(request_name, req.value, prod.value)
        relations.append(
            Relation(
                subject=f"current_product.{product_name}",
                relation="satisfies" if status != "conflict" else "conflicts_with",
                object=f"request.{request_name}",
                status=status,
                evidence=evidence,
            )
        )
    return relations


def classify_action(action: str) -> str:
    parsed = parse_webshop_action(action)
    if not parsed.valid:
        return "unknown"
    target = parsed.target.lower()
    if parsed.action_type == "search":
        return "explore"
    if parsed.action_type == "click" and target == "buy now":
        return "commit"
    if parsed.action_type == "click" and target in DETAIL_ACTIONS:
        return "inspect"
    if parsed.action_type == "click" and target in BACKTRACK_ACTIONS:
        return "backtrack"
    if parsed.action_type == "click":
        return "inspect"
    return "unknown"


def requirements_for_action(
    action_type: str,
    request_attrs: dict[str, Attribute],
    has_product: bool,
) -> list[str]:
    if action_type != "commit":
        return []
    requires = ["current_product exists"]
    for request_name, product_name in (
        ("price_max", "price"),
        ("color", "color"),
        ("size", "size"),
        ("brand", "brand"),
        ("product_type", "product_type"),
    ):
        req = request_attrs.get(request_name)
        if req is not None and req.status == "known":
            requires.append(f"current_product.{product_name} satisfies request.{request_name}")
    if not has_product:
        return requires
    return requires


def is_product_page(observation: str, available_actions: dict[str, Any]) -> bool:
    clickables = {str(item).lower() for item in available_actions.get("clickables", [])}
    return "buy now" in clickables or "buy now" in observation.lower()


def expected_effects_for_action(action: str) -> list[str]:
    action_type = classify_action(action)
    parsed = parse_webshop_action(action)
    if not parsed.valid:
        return ["valid WebShop action"]
    if action_type == "explore":
        return ["search results or changed observation"]
    if action_type == "inspect":
        return ["product/detail page or changed observation"]
    if action_type == "backtrack":
        return ["previous/search page or changed observation"]
    if action_type == "commit":
        return ["episode done", "purchase attempted"]
    return ["changed observation"]


def observed_effects(
    before: str,
    after: str,
    reward: float,
    done: bool,
    before_available: dict[str, Any] | None = None,
    after_available: dict[str, Any] | None = None,
) -> list[str]:
    effects: list[str] = []
    if done:
        effects.append("episode done")
    if reward > 0:
        effects.append("positive reward")
    if _normalized(before) != _normalized(after):
        effects.append("observation changed")
    if before_available and after_available and before_available != after_available:
        effects.append("available actions changed")
    if is_product_page(after, after_available or {}):
        effects.append("product page visible")
    if "search results" in after.lower():
        effects.append("search results visible")
    return effects


def relation_counts(state: ActionCentricState) -> dict[str, int]:
    counts = {"supported": 0, "missing_evidence": 0, "conflict": 0, "unknown": 0}
    for relation in state.relations:
        counts[relation.status] = counts.get(relation.status, 0) + 1
    return counts


def required_known_missing_conflicting(state: ActionCentricState) -> tuple[list[str], list[str], list[str], list[str]]:
    action = state.action_under_check
    known = []
    for entity in state.entities.values():
        for key, attr in entity.attributes.items():
            if attr.status == "known":
                known.append(f"{entity.entity_id}.{key}")
    return (
        list(action.requires),
        _unique(known),
        list(action.missing_requirements),
        list(action.conflicting_requirements),
    )


def action_state_from_dict(data: dict[str, Any]) -> ActionCentricState:
    entities = {}
    for entity_id, item in data.get("entities", {}).items():
        if not isinstance(item, dict):
            continue
        attrs = {
            name: Attribute(
                name=str(attr.get("name", name)),
                value=attr.get("value"),
                status=str(attr.get("status", "unknown")),
                evidence=str(attr.get("evidence", "")),
            )
            for name, attr in (item.get("attributes") or {}).items()
            if isinstance(attr, dict)
        }
        entities[entity_id] = Entity(
            entity_id=str(item.get("entity_id", entity_id)),
            type=str(item.get("type", "unknown")),
            name=str(item.get("name", entity_id)),
            attributes=attrs,
        )
    relations = [
        Relation(
            subject=str(item.get("subject", "")),
            relation=str(item.get("relation", "supports")),
            object=str(item.get("object", "")),
            status=str(item.get("status", "unknown")),
            evidence=str(item.get("evidence", "")),
        )
        for item in data.get("relations", [])
        if isinstance(item, dict)
    ]
    action_data = data.get("action_under_check") or {}
    action = ActionUnderCheck(
        action=str(action_data.get("action", "")),
        action_type=str(action_data.get("action_type", "unknown")),
        target_entity=str(action_data.get("target_entity", "")),
        requires=[str(item) for item in action_data.get("requires", [])],
        satisfied_requirements=[str(item) for item in action_data.get("satisfied_requirements", [])],
        missing_requirements=[str(item) for item in action_data.get("missing_requirements", [])],
        conflicting_requirements=[str(item) for item in action_data.get("conflicting_requirements", [])],
        pre_warning=bool(action_data.get("pre_warning", False)),
        pre_error=bool(action_data.get("pre_error", False)),
        repair_trigger=bool(action_data.get("repair_trigger", False)),
        reason=str(action_data.get("reason", "")),
    )
    post = None
    if isinstance(data.get("post_check"), dict):
        post_data = data["post_check"]
        post = PostCheck(
            expected_effect=[str(item) for item in post_data.get("expected_effect", [])],
            observed_effect=[str(item) for item in post_data.get("observed_effect", [])],
            matched=bool(post_data.get("matched", True)),
            post_warning=bool(post_data.get("post_warning", False)),
            post_error=bool(post_data.get("post_error", False)),
            repair_trigger=bool(post_data.get("repair_trigger", False)),
            reason=str(post_data.get("reason", "")),
        )
    return ActionCentricState(
        step_id=int(data.get("step_id", 0)),
        task=str(data.get("task", "")),
        entities=entities,
        relations=relations,
        action_under_check=action,
        post_check=post,
    )


def _compare_requirement(name: str, required: Any, observed: Any) -> tuple[str, str]:
    if name == "price_max":
        try:
            req = float(required)
            obs = float(observed)
        except (TypeError, ValueError):
            return "unknown", "price comparison unavailable"
        if obs <= req:
            return "supported", f"{obs} <= {req}"
        return "conflict", f"{obs} > {req}"
    req_text = str(required).lower()
    obs_text = str(observed).lower()
    if req_text and (req_text == obs_text or req_text in obs_text or obs_text in req_text):
        return "supported", f"{observed} matches {required}"
    return "conflict", f"{observed} does not match {required}"


def _attribute(name: str, value: Any, evidence_value: Any, evidence: str) -> Attribute:
    if evidence_value in (None, "", [], {}):
        return Attribute(name=name, value=value, status="unknown", evidence="")
    return Attribute(name=name, value=value, status="known", evidence=str(evidence or evidence_value))


def _extract_price_limit(text: str) -> float | None:
    match = re.search(r"(?:price\s*)?(?:lower than|under|below|less than|up to|max(?:imum)?)\s*\$?\s*(\d+(?:\.\d+)?)", text)
    if not match:
        match = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def _extract_price_value(text: str) -> float | None:
    matches = re.findall(r"(?:price:\s*)?\$\s*(\d+(?:\.\d+)?)", text, flags=re.I)
    if not matches:
        return None
    return float(matches[0])


def _extract_named_or_with(text: str, name: str) -> str:
    match = re.search(rf"{name}\s*:\s*([^,\[\]\n]+)", text, flags=re.I)
    if match:
        return match.group(1).strip(" .")
    return ""


def _extract_explicit_named(text: str, name: str) -> str:
    match = re.search(rf"{name}\s*:\s*([^,\[\]\n]+)", text, flags=re.I)
    if match:
        return match.group(1).strip(" .")
    return ""


def _extract_product_type(text: str) -> str:
    cleaned = text.replace("Instruction:", "").strip()
    match = re.search(r"find me\s+(.+?)(?:\s+with\s+|\s+and price|\s+price lower|\s+under|\.$|$)", cleaned, flags=re.I)
    if match:
        return match.group(1).strip(" .,")
    return ""


def extract_product_name(observation: str) -> str:
    parts = [part.strip() for part in observation.split("[SEP]")]
    for part in parts[1:]:
        lowered = part.lower()
        if not part or lowered.startswith(("price", "brand", "rating", "description", "features", "reviews")):
            continue
        if lowered in {"search", "search page", "back to search", "< prev", "next >", "buy now"}:
            continue
        if "search results" in lowered or lowered.startswith("instruction"):
            continue
        return part[:160]
    return ""


def _target_entity(action_type: str, action: str) -> str:
    if action_type == "commit":
        return "current_product"
    parsed = parse_webshop_action(action)
    if parsed.valid and parsed.action_type == "search":
        return "search_query"
    if parsed.valid and parsed.action_type == "click":
        return parsed.target
    return ""


def _action_reason(action_type: str, missing: list[str], conflicts: list[str]) -> str:
    if conflicts:
        return "Explicit conflicting requirements were found for this action."
    if missing:
        return "Missing evidence for required attributes; this is a warning, not an error."
    return f"No action-centric risk detected for {action_type} action."


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _to_plain(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value
