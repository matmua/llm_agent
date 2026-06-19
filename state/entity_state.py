"""Entity-attribute state graph for WebShop shadow detection."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from state.base_state import ActionRecord, StateGraph
from state.domain_adapters.webshop_adapter import WebShopAdapter
from state.llm_state_proposer import LLMStateProposer
from state.state_normalizer import StateNormalizer


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
SIZES = {"xs", "small", "medium", "large", "xl", "xxl", "queen", "king", "twin"}
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


@dataclass
class AttributeRecord:
    name: str
    value: Any
    source: str
    confidence: str
    evidence_text: str
    updated_at_step: int


@dataclass
class CandidateProduct:
    product_name: AttributeRecord
    price: AttributeRecord | None = None
    brand: AttributeRecord | None = None
    color: AttributeRecord | None = None
    size: AttributeRecord | None = None
    rating: AttributeRecord | None = None
    description_attributes: list[AttributeRecord] = field(default_factory=list)
    source: str = "observation"
    confidence: str = "medium"


@dataclass
class PageState:
    page_type: AttributeRecord
    query: AttributeRecord | None
    visible_products: list[AttributeRecord]
    available_actions: dict[str, Any]
    current_product_id_or_name: AttributeRecord | None


@dataclass
class ActionState:
    last_action: str
    last_action_type: str
    last_action_target: str
    action_source_supported: bool
    missing_preconditions: list[str]
    expected_delta: dict[str, Any]


@dataclass
class EntityAttributeStateGraph:
    task_requirement: dict[str, AttributeRecord] = field(default_factory=dict)
    page_state: PageState | None = None
    candidate_products: dict[str, CandidateProduct] = field(default_factory=dict)
    action_state: ActionState | None = None
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    state_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def validate(self) -> tuple[bool, list[str]]:
        errors: list[str] = []
        for name, record in self.task_requirement.items():
            _validate_attribute(record, f"task_requirement.{name}", errors)
        if self.page_state is None:
            errors.append("page_state is missing")
        else:
            _validate_attribute(self.page_state.page_type, "page_state.page_type", errors)
            for idx, product in enumerate(self.page_state.visible_products):
                _validate_attribute(product, f"page_state.visible_products.{idx}", errors)
        for key, product in self.candidate_products.items():
            _validate_attribute(product.product_name, f"candidate_products.{key}.product_name", errors)
        return len(errors) == 0, errors


class StateManager:
    def __init__(
        self,
        state_builder: str = "rule",
        use_llm_state: bool = False,
        llm_state_proposer: LLMStateProposer | None = None,
        domain_adapter: WebShopAdapter | None = None,
    ) -> None:
        self.graph = EntityAttributeStateGraph()
        self.generic_graph = StateGraph()
        self.instruction = ""
        self.state_builder = state_builder
        self.use_llm_state = use_llm_state
        self.llm_state_proposer = llm_state_proposer
        self.domain_adapter = domain_adapter or WebShopAdapter()
        self.normalizer = StateNormalizer()
        self.last_update_metadata: dict[str, Any] = {}

    def reset(
        self,
        instruction: str,
        observation: str,
        available_actions: dict[str, Any],
        step_id: int = 0,
    ) -> None:
        self.graph = EntityAttributeStateGraph()
        self.generic_graph = StateGraph()
        self.instruction = instruction
        self._update_task_requirements(instruction, step_id)
        self.update_observation(observation, available_actions, step_id)

    def update_observation(
        self,
        observation: str,
        available_actions: dict[str, Any],
        step_id: int,
    ) -> None:
        legacy_before = len(self.graph.state_history)
        page_type = infer_page_type(observation, available_actions)
        query = infer_query(observation)
        visible = infer_visible_products(available_actions)
        current = infer_current_product(observation, available_actions, page_type)
        self.graph.page_state = PageState(
            page_type=attr("page_type", page_type, "observation", "high", observation[:240], step_id),
            query=attr("query", query, "observation", "medium", observation[:240], step_id) if query else None,
            visible_products=[
                attr("product_name", item, "observation", "high", item, step_id) for item in visible
            ],
            available_actions=copy.deepcopy(available_actions),
            current_product_id_or_name=attr(
                "current_product_id_or_name", current, "observation", "medium", current, step_id
            )
            if current
            else None,
        )
        for product_name in visible:
            self._upsert_candidate(product_name, observation, step_id)
        if current:
            self._upsert_candidate(current, observation, step_id)
        self._record_history("observation", step_id)
        self._update_generic_state(observation, available_actions, step_id)
        self.last_update_metadata["legacy_state_events_added"] = len(self.graph.state_history) - legacy_before

    def update_action(self, action: str, step_id: int) -> None:
        action_type, target = parse_action_parts(action)
        self.graph.action_state = ActionState(
            last_action=action,
            last_action_type=action_type,
            last_action_target=target,
            action_source_supported=True,
            missing_preconditions=[],
            expected_delta=expected_delta_for_action(action_type, target),
        )
        self.generic_graph.action_state = ActionRecord(
            action_text=action,
            action_type=action_type,
            action_target=target,
            expected_delta=expected_delta_for_action(action_type, target),
            source_supported=True,
            missing_preconditions=[],
        )
        self._record_history("action", step_id)

    def snapshot(self) -> dict[str, Any]:
        legacy = copy.deepcopy(self.graph.to_dict())
        legacy["generic_state_graph"] = copy.deepcopy(self.generic_graph.to_dict())
        legacy["state_builder"] = self.state_builder
        return legacy

    def summary(self) -> str:
        return self.summary_for_detector()

    def summary_for_detector(self) -> str:
        req = {
            key: record.value
            for key, record in self.graph.task_requirement.items()
            if record.value not in (None, "", [], {})
        }
        page = self.graph.page_state.page_type.value if self.graph.page_state else "unknown"
        current = (
            self.graph.page_state.current_product_id_or_name.value
            if self.graph.page_state and self.graph.page_state.current_product_id_or_name
            else ""
        )
        return json.dumps(
            {
                "task_requirement": req,
                "page_type": page,
                "current_product": current,
                "conflicts": self.graph.conflicts[-3:],
                "generic_entities": len(self.generic_graph.entities),
                "generic_constraints": len(self.generic_graph.constraints),
            },
            ensure_ascii=True,
        )

    def _update_generic_state(
        self,
        observation: str,
        available_actions: dict[str, Any],
        step_id: int,
    ) -> None:
        previous_snapshot = self.generic_graph.to_dict()
        last_action = self.graph.action_state.last_action if self.graph.action_state else ""
        llm_raw = ""
        llm_parse_error = ""
        fallback_used = False
        normalized_errors: list[str] = []
        merge_delta: dict[str, Any] = {}

        proposal: dict[str, Any] | None = None
        if self.state_builder in {"llm", "llm_hybrid"} and self.use_llm_state and self.llm_state_proposer:
            result = self.llm_state_proposer.propose(
                task_instruction=self.instruction,
                observation=observation,
                available_actions=available_actions,
                previous_state_snapshot=previous_snapshot,
                last_action=last_action,
                step_id=step_id,
            )
            llm_raw = result.raw_response
            llm_parse_error = result.parse_error or result.request_error
            if result.ok and result.parsed is not None:
                proposal = result.parsed
            else:
                fallback_used = True

        if proposal is None:
            proposal = self.domain_adapter.build_proposal(
                task_instruction=self.instruction,
                observation=observation,
                available_actions=available_actions,
                step_id=step_id,
                last_action=last_action,
            )
            fallback_used = fallback_used or self.state_builder in {"llm", "llm_hybrid"}
        elif self.state_builder == "llm_hybrid":
            adapter_proposal = self.domain_adapter.build_proposal(
                task_instruction=self.instruction,
                observation=observation,
                available_actions=available_actions,
                step_id=step_id,
                last_action=last_action,
            )
            proposal = _combine_proposals(proposal, adapter_proposal)

        normalized = self.normalizer.normalize(proposal, step_id=step_id)
        normalized_errors.extend(normalized.errors)
        merged = self.normalizer.merge(self.generic_graph, normalized.graph, step_id=step_id)
        merge_delta = merged.delta
        self.generic_graph = merged.graph
        self.last_update_metadata = {
            "state_builder": self.state_builder,
            "use_llm_state": self.use_llm_state,
            "llm_state_proposal_raw": llm_raw,
            "llm_state_proposal_parse_error": llm_parse_error,
            "state_fallback_used": fallback_used,
            "normalized_state_delta": merge_delta,
            "normalized_state_errors": normalized_errors,
            "generic_entities": len(self.generic_graph.entities),
            "generic_constraints": len(self.generic_graph.constraints),
            "generic_conflicts": len(self.generic_graph.conflicts),
        }

    def missing_hard_constraints_for_current_product(self) -> list[str]:
        page = self.graph.page_state
        if page is None or page.current_product_id_or_name is None:
            return self._hard_constraint_names()
        current_name = str(page.current_product_id_or_name.value).lower()
        product = self.graph.candidate_products.get(current_name)
        if not product:
            return self._hard_constraint_names()
        missing: list[str] = []
        for name in self._hard_constraint_names():
            requirement = self.graph.task_requirement.get(name)
            if requirement is None or requirement.value in (None, "", []):
                continue
            product_attr = getattr(product, name.replace("_constraint", ""), None)
            if product_attr is None or product_attr.value in (None, "", []):
                observation = page.current_product_id_or_name.evidence_text.lower()
                if str(requirement.value).lower() not in observation:
                    missing.append(name)
            elif name == "price_constraint":
                try:
                    if float(product_attr.value) > float(requirement.value):
                        missing.append(name)
                except (TypeError, ValueError):
                    missing.append(name)
            elif str(requirement.value).lower() in str(product_attr.evidence_text).lower():
                continue
            elif str(product_attr.value).lower() != str(requirement.value).lower():
                missing.append(name)
        return missing

    def repair_candidate_slots(self, contaminated_slots: list[str], step_id: int) -> list[str]:
        page = self.graph.page_state
        if page is None or page.current_product_id_or_name is None:
            return []
        current_name = str(page.current_product_id_or_name.value).lower()
        product = self.graph.candidate_products.get(current_name)
        if product is None:
            return []
        repaired: list[str] = []
        for slot in contaminated_slots:
            normalized = slot.split(".")[-1].replace("_constraint", "")
            if normalized in {"color", "size", "brand", "price", "rating"} and hasattr(product, normalized):
                if getattr(product, normalized) is not None:
                    setattr(product, normalized, None)
                    repaired.append(f"{current_name}.{normalized}")
        if repaired:
            self.graph.conflicts.append(
                {
                    "attribute": "minimal_state_repair",
                    "old_value": contaminated_slots,
                    "new_value": repaired,
                    "step_id": step_id,
                    "evidence_text": "Cleared only contaminated candidate-product slots.",
                }
            )
            self._record_history("minimal_state_repair", step_id)
        return repaired

    def _hard_constraint_names(self) -> list[str]:
        names = []
        for name in ("color_constraint", "size_constraint", "brand_constraint", "price_constraint", "quantity_constraint"):
            record = self.graph.task_requirement.get(name)
            if record is not None and record.value not in (None, "", []):
                names.append(name)
        return names

    def _update_task_requirements(self, instruction: str, step_id: int) -> None:
        product_type = infer_product_type(instruction)
        required_attrs = infer_required_attributes(instruction)
        extracted = {
            "product_type": product_type,
            "required_attributes": required_attrs,
            "preferred_attributes": [],
            "price_constraint": infer_price_constraint(instruction),
            "brand_constraint": infer_brand_constraint(instruction),
            "color_constraint": infer_named_constraint(instruction, "color")
            or infer_token_constraint(instruction, COLORS),
            "size_constraint": infer_named_constraint(instruction, "size")
            or infer_token_constraint(instruction, SIZES),
            "quantity_constraint": infer_quantity(instruction),
            "other_constraints": infer_other_constraints(instruction),
        }
        for name, value in extracted.items():
            self._set_requirement(name, value, instruction, step_id)

    def _set_requirement(self, name: str, value: Any, evidence: str, step_id: int) -> None:
        source = "user_instruction" if value not in (None, "", []) else "missing"
        confidence = "high" if value not in (None, "", []) else "unknown"
        existing = self.graph.task_requirement.get(name)
        if existing and existing.value not in (None, "", []) and existing.value != value:
            self.graph.conflicts.append(
                {
                    "attribute": name,
                    "old_value": existing.value,
                    "new_value": value,
                    "step_id": step_id,
                    "evidence_text": evidence[:240],
                }
            )
            return
        self.graph.task_requirement[name] = attr(name, value, source, confidence, evidence[:240], step_id)

    def _upsert_candidate(self, product_name: str, observation: str, step_id: int) -> None:
        key = product_name.lower()
        product = self.graph.candidate_products.get(key)
        if product is None:
            product = CandidateProduct(
                product_name=attr("product_name", product_name, "observation", "high", product_name, step_id)
            )
        price = infer_price_near_product(observation, product_name) or infer_price_constraint(observation)
        if price is not None:
            product.price = attr("price", price, "observation", "medium", observation[:240], step_id)
        color = infer_token_constraint(observation, COLORS)
        if color:
            product.color = attr("color", color, "observation", "medium", observation[:240], step_id)
        size = infer_token_constraint(observation, SIZES)
        if size:
            product.size = attr("size", size, "observation", "medium", observation[:240], step_id)
        brand = infer_brand_constraint(observation)
        if brand:
            product.brand = attr("brand", brand, "observation", "medium", observation[:240], step_id)
        self.graph.candidate_products[key] = product

    def _record_history(self, event_type: str, step_id: int) -> None:
        page_type = self.graph.page_state.page_type.value if self.graph.page_state else "unknown"
        action = self.graph.action_state.last_action if self.graph.action_state else ""
        self.graph.state_history.append(
            {
                "event_type": event_type,
                "step_id": step_id,
                "page_type": page_type,
                "last_action": action,
                "num_candidate_products": len(self.graph.candidate_products),
                "num_conflicts": len(self.graph.conflicts),
            }
        )


def attr(name: str, value: Any, source: str, confidence: str, evidence: str, step: int) -> AttributeRecord:
    return AttributeRecord(
        name=name,
        value=value,
        source=source,
        confidence=confidence,
        evidence_text=evidence,
        updated_at_step=step,
    )


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


def infer_product_type(text: str) -> str:
    lowered = text.lower()
    patterns = [
        r"(?:find|buy|purchase|search for|get)\s+(?:me\s+)?(?:a|an|the)?\s*([a-z0-9 -]{2,120})",
        r"looking for\s+(?:a|an|the)?\s*([a-z0-9 -]{2,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            phrase = re.split(r"\b(?:under|below|less than|price|with|that|for|and)\b", match.group(1))[0]
            return " ".join(phrase.split()[:5]).strip()
    words = [
        word
        for word in re.findall(r"[a-z][a-z0-9-]+", lowered)
        if word not in {"instruction", "please", "find", "me", "buy"}
    ]
    return " ".join(words[:3])


def infer_required_attributes(text: str) -> list[str]:
    attrs: list[str] = []
    lowered = text.lower()
    if any(color in lowered for color in COLORS) or "color:" in lowered:
        attrs.append("color")
    if any(size in lowered for size in SIZES) or "size:" in lowered:
        attrs.append("size")
    if "$" in lowered or "under" in lowered or "below" in lowered or "price lower than" in lowered:
        attrs.append("price")
    if "brand" in lowered:
        attrs.append("brand")
    return attrs


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
    index = text.lower().find(product_name.lower())
    window = text[index : index + 260] if index >= 0 else text
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


def infer_quantity(text: str) -> int | None:
    match = re.search(r"\b(\d+)\s*(?:pack|packs|count|pcs|pieces|items?)\b", text.lower())
    return int(match.group(1)) if match else None


def infer_other_constraints(text: str) -> list[str]:
    lowered = text.lower()
    markers = ["waterproof", "organic", "wireless", "rechargeable", "stainless", "cotton"]
    return [marker for marker in markers if marker in lowered]


def infer_query(observation: str) -> str:
    match = re.search(r"(?:query|search results for|keywords?)[:\s]+([a-z0-9 +_-]{2,80})", observation.lower())
    return match.group(1).strip(" .") if match else ""


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
        lowered = text.lower()
        if text and lowered not in NAV_CLICKABLES:
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


def parse_action_parts(action: str) -> tuple[str, str]:
    match = re.match(r"\s*(search|click)\[(.*)\]\s*$", action, re.I)
    if not match:
        return "invalid", ""
    return match.group(1).lower(), match.group(2).strip().lower()


def expected_delta_for_action(action_type: str, target: str) -> dict[str, Any]:
    if action_type == "search":
        return {"expected_page_type": "results_page", "expected_new_information": True}
    if action_type == "click" and target == "buy now":
        return {"expected_page_type": "done_page", "expected_done": True}
    if action_type == "click" and target in {"description", "features", "reviews"}:
        return {"expected_page_type": "detail_page", "expected_new_information": True}
    if action_type == "click" and target in {"< prev", "prev", "previous"}:
        return {"expected_page_type": "product_page", "expected_new_information": True}
    if action_type == "click" and target == "back to search":
        return {"expected_page_type": "search_page", "expected_new_information": True}
    if action_type == "click":
        return {"expected_page_type": "product_page", "expected_new_information": True}
    return {"expected_page_type": "unknown"}


def _validate_attribute(record: Any, path: str, errors: list[str]) -> None:
    if not isinstance(record, AttributeRecord):
        errors.append(f"{path} is not AttributeRecord")
        return
    for field_name in ("name", "source", "confidence", "evidence_text", "updated_at_step"):
        if not hasattr(record, field_name):
            errors.append(f"{path}.{field_name} is missing")


def _empty_proposal() -> dict[str, Any]:
    return {
        "entities": [],
        "constraints": [],
        "relations": [],
        "goals": [],
        "current_observation_summary": "",
        "expected_state_changes_from_last_action": [],
        "uncertain_or_missing_information": [],
    }


def _combine_proposals(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    combined = dict(primary)
    for key in ("entities", "constraints", "relations", "goals"):
        combined[key] = list(primary.get(key) or []) + list(secondary.get(key) or [])
    for key in ("expected_state_changes_from_last_action", "uncertain_or_missing_information"):
        combined[key] = list(primary.get(key) or []) + list(secondary.get(key) or [])
    if not combined.get("current_observation_summary"):
        combined["current_observation_summary"] = secondary.get("current_observation_summary", "")
    return combined
