"""Shadow-mode intervention policy.

Phase 1 shadow mode only. No intervention is performed. Completion, blocking,
repair, rollback, and minimal state repair are interface placeholders only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InterventionDecision:
    allow_execute: bool
    raw_action: str
    executed_action: str
    would_block: bool
    would_complete: bool
    would_repair: bool
    hypothetical_completion_action: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_execute": self.allow_execute,
            "raw_action": self.raw_action,
            "executed_action": self.executed_action,
            "would_block": self.would_block,
            "would_complete": self.would_complete,
            "would_repair": self.would_repair,
            "hypothetical_completion_action": self.hypothetical_completion_action,
            "reason": self.reason,
            "metadata": self.metadata,
        }


@dataclass
class RepairDecision:
    repair_needed: bool
    repair_executed: bool
    reason: str
    hypothetical_repair_plan: str = ""
    repair_action: str = ""
    contaminated_slots: list[str] = field(default_factory=list)
    repaired_slots: list[str] = field(default_factory=list)
    checkpoint_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repair_needed": self.repair_needed,
            "repair_executed": self.repair_executed,
            "reason": self.reason,
            "hypothetical_repair_plan": self.hypothetical_repair_plan,
            "repair_action": self.repair_action,
            "contaminated_slots": self.contaminated_slots,
            "repaired_slots": self.repaired_slots,
            "checkpoint_id": self.checkpoint_id,
            "metadata": self.metadata,
        }


class ShadowInterventionPolicy:
    def decide_before_action(self, pre_action_report: Any, raw_action: str) -> InterventionDecision:
        decision = InterventionDecision(
            allow_execute=True,
            raw_action=raw_action,
            executed_action=raw_action,
            would_block=bool(getattr(pre_action_report, "should_block_hypothetical", False)),
            would_complete=bool(getattr(pre_action_report, "missing_attributes", [])),
            would_repair=False,
            hypothetical_completion_action=str(
                getattr(pre_action_report, "hypothetical_completion_action", "")
            ),
            reason=(
                "Phase 1 shadow mode: risk is logged but the raw action is executed unchanged."
            ),
        )
        assert decision.executed_action == raw_action
        return decision

    def repair_after_action(self, post_action_report: Any) -> RepairDecision:
        return RepairDecision(
            repair_needed=bool(getattr(post_action_report, "hypothetical_repair_needed", False)),
            repair_executed=False,
            reason="Phase 1 shadow mode: no post-action repair, rollback, or state repair is executed.",
            hypothetical_repair_plan=str(getattr(post_action_report, "hypothetical_repair_plan", "")),
        )
