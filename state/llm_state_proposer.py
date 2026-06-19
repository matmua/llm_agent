"""LLM state proposal interface.

The proposer never mutates state directly. It only returns a structured proposal
and parse metadata; StateNormalizer and StateManager own validation and merging.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agents.llm_client import LLMClient, MockLLMClient, extract_json


@dataclass
class LLMStateProposalResult:
    raw_response: str = ""
    parsed: dict[str, Any] | None = None
    parse_error: str = ""
    request_error: str = ""
    used_fallback: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.parsed is not None and not self.parse_error and not self.request_error


class LLMStateProposer:
    def __init__(self, client: LLMClient | None = None):
        self.client = client

    def propose(
        self,
        task_instruction: str,
        observation: str,
        available_actions: dict[str, Any],
        previous_state_snapshot: dict[str, Any],
        last_action: str,
        step_id: int,
    ) -> LLMStateProposalResult:
        if self.client is None or isinstance(self.client, MockLLMClient):
            return LLMStateProposalResult(
                raw_response="{}",
                parsed=_empty_proposal(),
                metadata={"provider": "mock_or_disabled", "step_id": step_id},
            )
        payload = {
            "task_instruction": task_instruction,
            "observation": observation,
            "available_actions": available_actions,
            "previous_state_snapshot": previous_state_snapshot,
            "last_action": last_action,
            "step_id": step_id,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "Propose a generic entity-state graph update. Return JSON only with "
                    "entities, constraints, relations, goals, current_observation_summary, "
                    "expected_state_changes_from_last_action, uncertain_or_missing_information. "
                    "Do not decide actions and do not overwrite state."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
        ]
        try:
            if hasattr(self.client, "chat_json"):
                parsed_response = self.client.chat_json(messages, temperature=0.0, max_tokens=1200)
                response = str(parsed_response.get("raw_response") or "")
                if parsed_response.get("_request_error"):
                    return LLMStateProposalResult(
                        raw_response=response,
                        request_error=str(parsed_response.get("raw_response") or "request_error"),
                        metadata={"step_id": step_id},
                    )
                if parsed_response.get("_parse_error"):
                    return LLMStateProposalResult(
                        raw_response=response,
                        parse_error="failed_to_parse_json_object",
                        metadata={"step_id": step_id},
                    )
                parsed = dict(parsed_response)
                parsed.pop("raw_response", None)
                return LLMStateProposalResult(
                    raw_response=response,
                    parsed=_ensure_top_level(parsed),
                    metadata={"step_id": step_id},
                )
            response = self.client.chat(messages, temperature=0.0, max_tokens=1200)
        except Exception as exc:  # pragma: no cover - client-specific failure
            return LLMStateProposalResult(request_error=str(exc), metadata={"step_id": step_id})
        parsed = extract_json(response)
        if parsed is None:
            return LLMStateProposalResult(
                raw_response=response,
                parse_error="failed_to_parse_json_object",
                metadata={"step_id": step_id},
            )
        return LLMStateProposalResult(
            raw_response=response,
            parsed=_ensure_top_level(parsed),
            metadata={"step_id": step_id},
        )


def _empty_proposal() -> dict[str, Any]:
    return {
        "entities": [],
        "constraints": [],
        "relations": [],
        "goals": [],
        "current_observation_summary": "",
        "expected_state_changes_from_last_action": [],
        "uncertain_or_missing_information": [],
    }


def _ensure_top_level(parsed: dict[str, Any]) -> dict[str, Any]:
    result = dict(parsed)
    for key in (
        "entities",
        "constraints",
        "relations",
        "goals",
        "expected_state_changes_from_last_action",
        "uncertain_or_missing_information",
    ):
        if key not in result or result[key] is None:
            result[key] = []
    result.setdefault("current_observation_summary", "")
    return result
