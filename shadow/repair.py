"""No-op repair placeholder for rule-based shadow v1."""

from __future__ import annotations

from typing import Any


def propose_repair(action_record: dict[str, Any], shadow_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": False,
        "decision": None,
        "new_action": None,
    }
