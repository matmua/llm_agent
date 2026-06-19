"""Lightweight checkpoints for local state repair."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Checkpoint:
    checkpoint_id: str
    task_id: int
    step_id: int
    observation: str
    available_actions: dict[str, Any]
    state_snapshot: dict[str, Any]
    action_history: list[dict[str, Any]]
    dependencies: list[str] = field(default_factory=list)


class CheckpointManager:
    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}

    def create(
        self,
        task_id: int,
        step_id: int,
        observation: str,
        available_actions: dict[str, Any],
        state_snapshot: dict[str, Any],
        action_history: list[dict[str, Any]],
        dependencies: list[str] | None = None,
    ) -> Checkpoint:
        checkpoint_id = f"task{task_id}_step{step_id}"
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            task_id=task_id,
            step_id=step_id,
            observation=observation,
            available_actions=copy.deepcopy(available_actions),
            state_snapshot=copy.deepcopy(state_snapshot),
            action_history=copy.deepcopy(action_history),
            dependencies=list(dependencies or []),
        )
        self._checkpoints[checkpoint_id] = checkpoint
        return checkpoint

    def get(self, checkpoint_id: str) -> Checkpoint | None:
        return self._checkpoints.get(checkpoint_id)

