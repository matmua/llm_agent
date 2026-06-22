"""Post-action info-gain check for rule-based shadow v1."""

from __future__ import annotations

from typing import Any

from shadow.parser import normalize_value


def run_post_check(
    attributes_before: dict[str, Any],
    observed_attrs_after: dict[str, dict[str, Any]],
    context_after: str,
) -> dict[str, Any]:
    new_attrs = new_attribute_values(attributes_before, observed_attrs_after)
    return {
        "info_gain": bool(new_attrs),
        "new_attrs": new_attrs,
        "context_after": context_after,
    }


def new_attribute_values(
    attributes_before: dict[str, Any],
    observed_attrs_after: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    new_attrs: list[dict[str, str]] = []
    for key, record in observed_attrs_after.items():
        before_values = set((attributes_before.get(key, {}).get("values") or {}).keys())
        for value in (record.get("values") or {}).keys():
            norm = normalize_value(value)
            if key not in attributes_before or norm not in before_values:
                new_attrs.append({"key": key, "value": str(record.get("current_value") or value)})
    return new_attrs
