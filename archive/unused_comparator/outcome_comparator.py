"""General predicted-vs-actual outcome comparator."""

from __future__ import annotations

import json
from dataclasses import asdict

from llm_agent_guard.schemas import (
    OutcomeComparison,
    OutcomePrediction,
    ProposedAction,
    ReviewContext,
    comparison_from_dict,
    to_jsonable,
)


COMPARATOR_SYSTEM_PROMPT = """
You are a general outcome comparator for a tool-using AI agent.

You compare the predicted consequence of an action with the actual observation returned by the environment.

Do not use hidden gold answers.
Do not judge by reference trajectories.
Only compare:
1. Whether the actual observation matches the predicted outcome.
2. Whether the actual observation indicates progress, no progress, or degradation.
3. Whether the mismatch suggests error propagation risk.
4. Whether the agent should recover before continuing.

Return JSON only.
""".strip()


class OutcomeComparator:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    def compare(
        self,
        context: ReviewContext,
        action: ProposedAction,
        prediction: OutcomePrediction,
        actual_observation: str,
    ) -> OutcomeComparison:
        user_prompt = f"""
TASK GOAL:
{context.task_goal}

RECENT HISTORY:
{json.dumps(to_jsonable(context.recent_history), ensure_ascii=False, indent=2)}

PROPOSED ACTION:
{json.dumps(to_jsonable(asdict(action)), ensure_ascii=False, indent=2)}

PREDICTED OUTCOME:
{prediction.predicted_outcome}

ACTUAL OBSERVATION:
{actual_observation}

Return JSON with exactly these fields:
{{
  "prediction_match": true,
  "actual_progress": "improve | neutral | degrade | unknown",
  "unexpected_outcome": false,
  "new_risk_level": "low | medium | high | critical",
  "should_recover": false,
  "reason": "string"
}}
""".strip()
        result = self.llm_client.chat_json(
            [
                {"role": "system", "content": COMPARATOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=768,
        )
        raw_response = result.get("raw_response")
        return comparison_from_dict(result, raw_response)
