"""Plan-first LLMAgent implementation for local tau3 experiments."""

from __future__ import annotations

from copy import deepcopy
from typing import Optional

from tau2.agent.base_agent import ValidAgentInputMessage
from tau2.agent.llm_agent import LLMAgent, LLMAgentState
from tau2.data_model.message import (
    AssistantMessage,
    MultiToolMessage,
    SystemMessage,
    UserMessage,
)
from tau2.utils.llm_utils import generate


PLAN_FIRST_INSTRUCTION = """
You are a customer service agent that helps the user according to the <policy> below.

In each real turn you can either:
- Send a message to the user.
- Make exactly one tool call.

Before choosing the real next action, you must do a short internal planning pass.
The planning pass is not shown to the user. Use it as a safety gate to predict
consequences and avoid irreversible, guessed, or repeated wrong tool calls.

Planning checklist:
1. Restate the user's current goal and the known verified facts.
2. Identify missing facts and whether they must be obtained from tools or from the user.
3. Estimate expected consequence, risk, turn/tool cost, and recommendation from 1 to 5.
4. Choose one recommended next action.
5. If a prior tool call returned an error, do not retry the same invalid arguments.
6. Do not invent IDs, emails, order numbers, item IDs, product IDs, or payment method IDs.
7. To find exchange/modify variants for a known product, use get_product_details(product_id).
   Do not use get_item_details on guessed variant item IDs.
8. If the policy requires confirmation before a write tool, ask for confirmation first.

After planning, execute only the chosen real next action. Do not mention the
internal plan, risks, scores, or checklist to the user.
Always follow the policy. Always make sure you generate valid JSON only.
""".strip()


PLAN_SYSTEM_PROMPT = """
You are doing a private planning pass for the next customer-service agent turn.
Do not call tools. Do not answer the user directly.
Return only compact valid JSON, at most 120 words.

Required JSON schema:
{
  "goal": "current user goal",
  "known": ["only verified facts"],
  "missing": ["facts still needed"],
  "next": "one next action",
  "tool": "tool name or null",
  "consequence": "expected result",
  "risk": "low|medium|high",
  "cost": "turn/tool estimate",
  "recommendation": 1,
  "avoid": ["specific mistakes to avoid"]
}

Rules:
- Use only IDs already present in user or tool messages.
- For product variants, use get_product_details(product_id), not guessed item IDs.
- Do not repeat an exact prior tool call unless the previous result was unusable.
- Before any write tool, make sure required confirmation and payment details exist.
""".strip()


DECISION_SYSTEM_PROMPT = """
Use the private plan below to choose the next real action.

Rules:
- Do not reveal or summarize the private plan to the user.
- Treat the plan as advisory, not as permission to invent tool names or IDs.
- If the recommended action needs a tool, call the exact appropriate real tool.
- If the plan says key facts are missing, ask the user or call a read-only tool.
- If any proposed write action has medium/high risk or lacks required confirmation,
  ask a clarifying/confirmation question instead.
- If a tool error happened, change strategy instead of retrying identical invalid arguments.
- Do not repeat an exact successful read call. Use its result already in the context.
- To find available exchange/modify variants, call get_product_details with a verified
  product_id from an order or product result. Never guess variant item IDs.

<private_plan>
{plan}
</private_plan>
""".strip()


class PlanFirstLLMAgent(LLMAgent):
    """LLMAgent variant that performs an internal planning call before acting."""

    def __init__(
        self,
        tools,
        domain_policy: str,
        llm: str,
        llm_args: Optional[dict] = None,
        plan_llm_args: Optional[dict] = None,
    ):
        super().__init__(
            tools=tools,
            domain_policy=domain_policy,
            llm=llm,
            llm_args=llm_args,
        )
        self.plan_llm_args = plan_llm_args or {}

    @property
    def system_prompt(self) -> str:
        from tau2.agent.llm_agent import SYSTEM_PROMPT

        return SYSTEM_PROMPT.format(
            domain_policy=self.domain_policy,
            agent_instruction=PLAN_FIRST_INSTRUCTION,
        )

    def _generate_next_message(
        self, message: ValidAgentInputMessage, state: LLMAgentState
    ) -> AssistantMessage:
        if isinstance(message, UserMessage) and message.is_audio:
            raise ValueError("User message cannot be audio. Use VoiceLLMAgent instead.")
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        else:
            state.messages.append(message)

        base_messages = state.system_messages + state.messages
        planning_messages = [
            SystemMessage(role="system", content=PLAN_SYSTEM_PROMPT),
            *base_messages,
        ]
        plan_args = deepcopy(self.llm_args)
        plan_args.update(self.plan_llm_args)
        plan_message = generate(
            model=self.llm,
            messages=planning_messages,
            call_name="agent_private_plan",
            **plan_args,
        )
        plan_text = plan_message.content or "{}"

        decision_messages = [
            *base_messages,
            SystemMessage(
                role="system",
                content=DECISION_SYSTEM_PROMPT.format(plan=plan_text),
            ),
        ]
        return generate(
            model=self.llm,
            tools=self.tools,
            messages=decision_messages,
            call_name="agent_response",
            **self.llm_args,
        )


def create_plan_first_llm_agent(tools, domain_policy, **kwargs):
    llm_args = deepcopy(kwargs.get("llm_args") or {})
    plan_llm_args = llm_args.pop("plan_llm_args", None) or kwargs.get("plan_llm_args")
    return PlanFirstLLMAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=kwargs.get("llm"),
        llm_args=llm_args,
        plan_llm_args=plan_llm_args,
    )


def register_plan_first_agent() -> None:
    from tau2.registry import registry

    if "plan_first_llm_agent" not in registry.get_agents():
        registry.register_agent_factory(
            create_plan_first_llm_agent,
            "plan_first_llm_agent",
        )
