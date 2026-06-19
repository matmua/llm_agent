"""ReAct-style WebShop agent."""

from __future__ import annotations

import re
from typing import Any

from agents.llm_client import LLMClient


class WebShopReactAgent:
    def __init__(self, client: LLMClient):
        self.client = client
        self.last_trace: dict[str, Any] = {}

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
                        "You are a WebShop action generator. Return exactly one next action line "
                        "and nothing else. Valid actions are search[keywords] and click[value]. "
                        "Do not include thoughts, explanations, markdown, or quotes around the action."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=96,
        )
        action = parse_action_from_response(response)
        self.last_trace = {
            "prompt_chars": len(prompt),
            "response_chars": len(response),
            "estimated_prompt_tokens": estimate_tokens(prompt),
            "estimated_response_tokens": estimate_tokens(response),
            "estimated_total_tokens": estimate_tokens(prompt) + estimate_tokens(response),
            "prompt_contains_state_summary": "Current task state summary:" in prompt,
            "prompt_excerpt": prompt[:4000],
            "raw_response": response[:2000],
        }
        return action

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
        state_block = f"Current task state summary:\n{state_summary}\n" if state_summary else ""
        return (
            f"Task instruction:\n{task_instruction}\n"
            f"Observation:\n{observation}\n"
            "Available actions:\n"
            f"has_search_bar: {str(bool(available_actions.get('has_search_bar'))).lower()}\n"
            f"clickables: {clickables}\n"
            f"{state_block}"
            f"Recent action history:\n{recent_history}\n\n"
            "Output exactly one line in one of these forms:\n"
            "Action: search[keywords]\n"
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


def estimate_tokens(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)
