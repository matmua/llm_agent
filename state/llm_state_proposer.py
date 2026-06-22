"""LLM proposal wrapper for action-centric state.

The proposer only constructs state for detector use. It never changes an agent
action and the runner never passes this state back into the agent prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agents.llm_client import LLMClient, MockLLMClient
from state.action_state import ActionCentricState, action_state_from_dict, build_fallback_state


@dataclass
class StateProposalResult:
    state: ActionCentricState
    raw_response: str = ""
    parse_error: str = ""
    request_error: str = ""
    fallback_used: bool = False

    @property
    def ok(self) -> bool:
        return not self.parse_error and not self.request_error and not self.fallback_used


class LLMStateProposer:
    def __init__(self, client: LLMClient | None = None):
        self.client = client

    def propose(
        self,
        task_instruction: str,
        observation: str,
        available_actions: dict[str, Any],
        raw_action: str,
        previous_action_state: ActionCentricState | dict[str, Any] | None,
        step_id: int,
    ) -> StateProposalResult:
        fallback = build_fallback_state(
            task_instruction=task_instruction,
            observation=observation,
            available_actions=available_actions,
            raw_action=raw_action,
            step_id=step_id,
        )
        if self.client is None or isinstance(self.client, MockLLMClient):
            return StateProposalResult(state=fallback, raw_response="{}", fallback_used=True)

        payload = {
            "task_instruction": task_instruction,
            "current_observation": observation,
            "available_actions": available_actions,
            "raw_action": raw_action,
            "previous_action_state": _plain_state(previous_action_state),
            "fallback_action_centric_state": fallback.to_dict(),
            "step_id": step_id,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You produce exactly one JSON object that conforms to the "
                    "ActionCentricState schema. Do not invent a new schema. Keep only "
                    "entities and relations needed to judge the current raw_action. "
                    "Do not include goals, plans, recommendations, action alternatives, "
                    "state history, or full world state. Use the provided "
                    "fallback_action_centric_state as the skeleton and return the same "
                    "top-level keys: step_id, task, entities, relations, "
                    "action_under_check, post_check. Every entity value must be an "
                    "object with entity_id, type, name, attributes. Every attribute "
                    "must be an object with name, value, status, evidence. Allowed "
                    "attribute.status values: known, unknown, conflict. Allowed "
                    "relation.status values: supported, missing_evidence, conflict, "
                    "unknown. If evidence is empty, status must be unknown. "
                    "action_under_check.action must equal raw_action exactly. Return "
                    "compact minified JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Return the ActionCentricState JSON only. Preserve the schema of "
                    "fallback_action_centric_state and improve evidence only when the "
                    "current observation directly supports it.\n"
                    + json.dumps(payload, ensure_ascii=True)
                ),
            },
        ]
        try:
            response = self.client.chat_json(messages, temperature=0.0, max_tokens=800)
        except Exception as exc:  # pragma: no cover - provider-specific failures
            return StateProposalResult(
                state=fallback,
                request_error=str(exc),
                fallback_used=True,
            )
        raw = str(response.get("raw_response") or "")
        if response.get("_request_error"):
            return StateProposalResult(
                state=fallback,
                raw_response=raw,
                request_error=str(response.get("raw_response") or "request_error"),
                fallback_used=True,
            )
        if response.get("_parse_error"):
            return StateProposalResult(
                state=fallback,
                raw_response=raw,
                parse_error="failed_to_parse_action_centric_state",
                fallback_used=True,
            )
        parsed = dict(response)
        parsed.pop("raw_response", None)
        try:
            state = _state_with_fallback_defaults(action_state_from_dict(parsed), fallback)
        except Exception as exc:
            return StateProposalResult(
                state=fallback,
                raw_response=raw,
                parse_error=f"invalid_action_centric_state: {exc}",
                fallback_used=True,
            )
        if not state.entities or not state.action_under_check.action:
            return StateProposalResult(
                state=fallback,
                raw_response=raw,
                parse_error="missing_required_action_state_fields",
                fallback_used=True,
            )
        return StateProposalResult(state=state, raw_response=raw)


def _plain_state(state: ActionCentricState | dict[str, Any] | None) -> dict[str, Any]:
    if state is None:
        return {}
    if isinstance(state, ActionCentricState):
        return state.to_dict()
    return state


def _state_with_fallback_defaults(
    state: ActionCentricState, fallback: ActionCentricState
) -> ActionCentricState:
    if not state.task:
        state.task = fallback.task
    state.step_id = fallback.step_id
    if not state.entities:
        state.entities = fallback.entities
    if not state.relations:
        state.relations = fallback.relations
    if not state.action_under_check.action:
        state.action_under_check = fallback.action_under_check
    else:
        state.action_under_check.action = fallback.action_under_check.action
        if state.action_under_check.action_type == "unknown":
            state.action_under_check.action_type = fallback.action_under_check.action_type
        if not state.action_under_check.target_entity:
            state.action_under_check.target_entity = fallback.action_under_check.target_entity
        if not state.action_under_check.requires:
            state.action_under_check.requires = fallback.action_under_check.requires
    return state
