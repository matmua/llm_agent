"""WebShop action parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedAction:
    raw: str
    valid: bool
    action_type: str
    target: str
    error: str = ""


def parse_webshop_action(action: str) -> ParsedAction:
    match = re.match(r"\s*(search|click)\[(.*)\]\s*$", action or "", re.I)
    if not match:
        return ParsedAction(
            raw=action,
            valid=False,
            action_type="invalid",
            target="",
            error="Action must match search[...] or click[...].",
        )
    action_type = match.group(1).lower()
    target = match.group(2).strip()
    if not target:
        return ParsedAction(
            raw=action,
            valid=False,
            action_type=action_type,
            target=target,
            error="Action target is empty.",
        )
    return ParsedAction(raw=action, valid=True, action_type=action_type, target=target)

