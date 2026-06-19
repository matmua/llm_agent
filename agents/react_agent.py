"""ReAct-style WebShop agent."""

from __future__ import annotations

import re
from typing import Any

from agents.llm_client import LLMClient


class WebShopReactAgent:
    def __init__(self, client: LLMClient):
        self.client = client

    def act(
        self,
        task_instruction: str,
        observation: str,
        action_history: list[dict[str, Any]],
        available_actions: dict[str, Any],
        state_summary: str = "",
    ) -> str:
        prompt = self._build_prompt(
            task_instruction=task_instruction,
            observation=observation,
            action_history=action_history,
            available_actions=available_actions,
            state_summary=state_summary,
        )
        response = self.client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a WebShop ReAct agent. Return exactly one next action. "
                        "Valid actions are search[keywords] and click[value]."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=256,
        )
        return parse_action_from_response(response)

    @staticmethod
    def _build_prompt(
        task_instruction: str,
        observation: str,
        action_history: list[dict[str, Any]],
        available_actions: dict[str, Any],
        state_summary: str,
    ) -> str:
        recent_history = action_history[-6:]
        clickables = available_actions.get("clickables", [])
        return (
            f"Task instruction:\n{task_instruction}\n"
            f"Observation:\n{observation}\n"
            "Available actions:\n"
            f"has_search_bar: {str(bool(available_actions.get('has_search_bar'))).lower()}\n"
            f"clickables: {clickables}\n"
            f"Current task state summary:\n{state_summary}\n"
            f"Recent action history:\n{recent_history}\n\n"
            "Think briefly, then output one line in this exact form:\n"
            "Action: search[keywords]\n"
            "or\n"
            "Action: click[value]"
        )


def parse_action_from_response(response: str) -> str:
    for pattern in (
        r"Action\s*:\s*(search\[[^\n\]]*\]|click\[[^\n\]]*\])",
        r"\b(search\[[^\n\]]*\]|click\[[^\n\]]*\])",
    ):
        match = re.search(pattern, response, re.I)
        if match:
            return match.group(1).strip()
    return response.strip().splitlines()[-1].strip() if response.strip() else ""

