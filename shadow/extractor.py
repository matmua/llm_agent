"""Rule-based attribute extraction for shadow v1."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from shadow.parser import normalize_value


NAV_TARGETS = {
    "search",
    "next",
    "next >",
    "previous",
    "prev",
    "< prev",
    "back to search",
    "description",
    "features",
    "reviews",
    "buy now",
}


def extract_task_attributes(task_text: str, step: int) -> dict[str, dict[str, Any]]:
    text = _compact(task_text)
    if not text:
        return {}
    return {
        "text.task": _attr(
            kind="text",
            entity=None,
            name="task",
            source="task",
            value=text,
            step=step,
        )
    }


def extract_observation_attributes(
    observation: str,
    available_actions: dict[str, Any] | None,
    step: int,
) -> dict[str, dict[str, Any]]:
    available_actions = available_actions or {}
    attrs: dict[str, dict[str, Any]] = {}
    normalized_obs = _compact(observation)
    context_hash = context_value(observation)
    attrs["context.current"] = _attr(
        kind="context",
        entity=None,
        name="current",
        source="observation",
        value=context_hash,
        step=step,
    )
    if normalized_obs:
        attrs[f"text.observation.{_short_hash(normalized_obs)}"] = _attr(
            kind="text",
            entity=None,
            name="observation",
            source="observation",
            value=normalized_obs[:500],
            step=step,
        )

    chunks = _chunks(observation)
    _extract_visible_items(attrs, chunks, step)
    _extract_product_detail(attrs, chunks, step)
    _extract_clickables(attrs, available_actions.get("clickables", []), step)
    return attrs


def context_value(observation: str) -> str:
    return "ctx_" + _short_hash(_compact(observation), size=12)


def _extract_clickables(attrs: dict[str, dict[str, Any]], clickables: list[Any], step: int) -> None:
    for item in clickables or []:
        value = str(item).strip()
        if not value:
            continue
        norm = normalize_value(value)
        key = f"text.action_target.{_safe_key(norm)}"
        attrs[key] = _attr(
            kind="text",
            entity=None,
            name="action_target",
            source="observation",
            value=value,
            step=step,
        )
        if _looks_like_item_id(value) and norm not in NAV_TARGETS:
            entity = _entity_id(value)
            attrs[f"entity.{entity}"] = _attr(
                kind="entity",
                entity=entity,
                name=None,
                source="observation",
                value=entity,
                step=step,
            )


def _extract_visible_items(attrs: dict[str, dict[str, Any]], chunks: list[str], step: int) -> None:
    idx = 0
    while idx < len(chunks):
        value = chunks[idx].strip()
        if not _looks_like_item_id(value):
            idx += 1
            continue
        entity = _entity_id(value)
        attrs[f"entity.{entity}"] = _attr(
            kind="entity",
            entity=entity,
            name=None,
            source="observation",
            value=entity,
            step=step,
        )
        title = chunks[idx + 1].strip() if idx + 1 < len(chunks) else ""
        if title and not _looks_like_price(title) and not _looks_like_item_id(title):
            attrs[f"attr.{entity}.title"] = _attr(
                kind="property",
                entity=entity,
                name="title",
                source="observation",
                value=title,
                step=step,
            )
        for lookahead in chunks[idx + 1 : idx + 4]:
            price = _price_value(lookahead)
            if price:
                attrs[f"attr.{entity}.price"] = _attr(
                    kind="property",
                    entity=entity,
                    name="price",
                    source="observation",
                    value=price,
                    step=step,
                )
                break
        idx += 1


def _extract_product_detail(attrs: dict[str, dict[str, Any]], chunks: list[str], step: int) -> None:
    if not chunks:
        return
    entity = ""
    for chunk in chunks:
        if _looks_like_item_id(chunk):
            entity = _entity_id(chunk)
            break
    if not entity:
        title = _first_title_like_chunk(chunks)
        if not title:
            return
        entity = "item_" + _short_hash(title, size=8)
        attrs[f"entity.{entity}"] = _attr(
            kind="entity",
            entity=entity,
            name=None,
            source="observation",
            value=entity,
            step=step,
        )
        attrs[f"attr.{entity}.title"] = _attr(
            kind="property",
            entity=entity,
            name="title",
            source="observation",
            value=title,
            step=step,
        )
    for idx, chunk in enumerate(chunks):
        lowered = normalize_value(chunk)
        price = _price_value(chunk)
        if price:
            attrs[f"attr.{entity}.price"] = _attr("property", entity, "price", "observation", price, step)
        if lowered in {"price", "brand", "color", "size", "rating"} and idx + 1 < len(chunks):
            name = lowered
            value = chunks[idx + 1].strip()
            if value:
                attrs[f"attr.{entity}.{name}"] = _attr(
                    "property", entity, name, "observation", value, step
                )
        for name in ("price", "brand", "color", "size", "rating"):
            match = re.search(rf"\b{name}\s*:\s*([^,\[\]\n|]+)", chunk, flags=re.I)
            if match:
                value = match.group(1).strip(" .")
                if value:
                    attrs[f"attr.{entity}.{name}"] = _attr(
                        "property", entity, name, "observation", value, step
                    )


def _attr(
    kind: str,
    entity: str | None,
    name: str | None,
    source: str,
    value: Any,
    step: int,
) -> dict[str, Any]:
    norm = normalize_value(value)
    return {
        "kind": kind,
        "entity": entity,
        "name": name,
        "source": source,
        "current_value": str(value),
        "values": {
            norm: {
                "first_seen_step": step,
                "last_seen_step": step,
                "steps": [step],
            }
        },
    }


def _chunks(text: str) -> list[str]:
    raw = re.split(r"\[SEP\]|\n|\|", text or "")
    return [item.strip(" []") for item in raw if item.strip(" []")]


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("[SEP]", " | ")).strip()


def _looks_like_item_id(value: str) -> bool:
    return bool(re.fullmatch(r"[Bb][0-9A-Za-z]{9}", value.strip()))


def _looks_like_price(value: str) -> bool:
    return bool(_price_value(value))


def _price_value(value: str) -> str:
    match = re.search(r"\$\s*\d+(?:\.\d+)?", value or "")
    return match.group(0).replace(" ", "") if match else ""


def _entity_id(value: str) -> str:
    return normalize_value(value)


def _first_title_like_chunk(chunks: list[str]) -> str:
    skip = {
        "webshop",
        "instruction:",
        "instruction",
        "back to search",
        "< prev",
        "next >",
        "description",
        "features",
        "reviews",
        "buy now",
        "search",
    }
    for chunk in chunks:
        norm = normalize_value(chunk)
        if norm in skip or norm.startswith("find me "):
            continue
        if _looks_like_price(chunk) or _looks_like_item_id(chunk):
            continue
        if len(chunk) >= 8:
            return chunk[:180]
    return ""


def _short_hash(text: str, size: int = 10) -> str:
    return hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()[:size]


def _safe_key(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", normalize_value(value)).strip("_")
    return cleaned[:80] or _short_hash(value)
