"""Two-table shadow state for rule-based shadow v1."""

from __future__ import annotations

import copy
from typing import Any

from shadow.parser import normalize_value


def new_shadow_state() -> dict[str, Any]:
    return {"attributes": {}, "actions": []}


def clone_attributes(shadow_state: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(shadow_state.get("attributes", {}))


def merge_attributes(shadow_state: dict[str, Any], observed_attrs: dict[str, dict[str, Any]]) -> None:
    attributes = shadow_state.setdefault("attributes", {})
    for key, incoming in observed_attrs.items():
        if key not in attributes:
            attributes[key] = copy.deepcopy(incoming)
            continue
        existing = attributes[key]
        existing["kind"] = existing.get("kind") or incoming.get("kind")
        existing["entity"] = existing.get("entity") if existing.get("entity") is not None else incoming.get("entity")
        existing["name"] = existing.get("name") if existing.get("name") is not None else incoming.get("name")
        existing["source"] = incoming.get("source") or existing.get("source")
        existing["current_value"] = incoming.get("current_value")
        values = existing.setdefault("values", {})
        for value, meta in (incoming.get("values") or {}).items():
            if value not in values:
                values[value] = copy.deepcopy(meta)
            else:
                values[value]["last_seen_step"] = meta.get("last_seen_step")
                values[value]["steps"] = sorted(
                    set(list(values[value].get("steps", [])) + list(meta.get("steps", [])))
                )


def current_context(shadow_state: dict[str, Any]) -> str:
    item = shadow_state.get("attributes", {}).get("context.current", {})
    return str(item.get("current_value") or "")


def check_params(parsed_action: dict[str, Any], attributes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    params = parsed_action.get("params") or {}
    if not isinstance(params, dict):
        return checks
    for name, value in params.items():
        matched = find_matching_attr(value, attributes)
        checks[name] = {
            "value": str(value),
            "known": matched is not None,
            "matched_attr": matched,
        }
    return checks


def find_matching_attr(value: Any, attributes: dict[str, Any]) -> str | None:
    norm = normalize_value(value)
    if not norm:
        return None
    for key, record in attributes.items():
        candidates = [
            key,
            record.get("entity"),
            record.get("name"),
            record.get("current_value"),
        ]
        candidates.extend((record.get("values") or {}).keys())
        for candidate in candidates:
            if candidate is None:
                continue
            if normalize_value(candidate) == norm:
                return str(key)
    return None


def attributes_summary(shadow_state: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    attributes = shadow_state.get("attributes", {})
    sample = []
    for key in sorted(attributes)[:limit]:
        record = attributes[key]
        sample.append(
            {
                "key": key,
                "kind": record.get("kind"),
                "entity": record.get("entity"),
                "name": record.get("name"),
                "current_value": record.get("current_value"),
                "num_values": len(record.get("values") or {}),
            }
        )
    return {
        "num_attributes": len(attributes),
        "num_actions": len(shadow_state.get("actions", [])),
        "current_context": current_context(shadow_state),
        "sample": sample,
    }
