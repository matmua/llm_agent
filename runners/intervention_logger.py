"""JSONL logger for WebShop intervention events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class InterventionLogger:
    def __init__(self, log_dir: Path):
        self.path = log_dir / "intervention_events.jsonl"
        self._fh = self.path.open("w", encoding="utf-8")

    def close(self) -> None:
        self._fh.close()

    def log_event(
        self,
        run_id: str,
        task_id: int,
        step_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        row = {
            "run_id": run_id,
            "task_id": task_id,
            "step_id": step_id,
            "event_type": event_type,
            "payload": payload,
        }
        self._fh.write(json.dumps(row, ensure_ascii=True) + "\n")
        self._fh.flush()

