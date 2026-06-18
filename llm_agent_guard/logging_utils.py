"""Structured JSONL logging for guarded tau3 runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_agent_guard.schemas import to_jsonable


@dataclass
class GuardRunStats:
    predictor_called: int = 0
    high_risk_count: int = 0
    critical_risk_count: int = 0
    revise_once_count: int = 0
    changed_by_controller_count: int = 0
    constraint_guided_revise_count: int = 0
    second_check_count: int = 0
    risk_reduced_after_revision_count: int = 0
    fallback_used_count: int = 0
    invalid_revised_action_count: int = 0
    executed_original_count: int = 0
    executed_revised_count: int = 0
    executed_fallback_count: int = 0
    per_task_steps: dict[str, int] = field(default_factory=dict)


class JsonlRunLogger:
    def __init__(self, run_name: str, root: Path | str = "runs"):
        self.run_name = run_name
        self.run_dir = Path(root) / run_name
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.stats = GuardRunStats()

    def log_step(self, task_id: str, row: dict[str, Any]) -> None:
        task_key = str(task_id)
        row = dict(row)
        row.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        path = self.run_dir / f"task_{task_key}.jsonl"
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(to_jsonable(row), ensure_ascii=False) + "\n")

        self.stats.per_task_steps[task_key] = self.stats.per_task_steps.get(task_key, 0) + 1
        prediction = row.get("prediction") or {}
        decision = row.get("controller_decision") or {}
        if prediction:
            self.stats.predictor_called += 1
            if prediction.get("risk_level") == "high":
                self.stats.high_risk_count += 1
            if prediction.get("risk_level") == "critical":
                self.stats.critical_risk_count += 1
        if decision.get("decision") == "revise_once":
            self.stats.revise_once_count += 1
            self.stats.constraint_guided_revise_count += 1
        if row.get("changed_by_controller"):
            self.stats.changed_by_controller_count += 1
        if row.get("revised_prediction"):
            self.stats.second_check_count += 1
        if row.get("risk_reduced_after_revision"):
            self.stats.risk_reduced_after_revision_count += 1
        if row.get("fallback_used"):
            self.stats.fallback_used_count += 1
        if row.get("revised_action_valid") is False:
            self.stats.invalid_revised_action_count += 1
        source = row.get("executed_action_source")
        if source == "original":
            self.stats.executed_original_count += 1
        elif source == "revised":
            self.stats.executed_revised_count += 1
        elif source == "fallback":
            self.stats.executed_fallback_count += 1
