"""Tau2 LLMAgent wrapper with optional predictor-only risk logging."""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from llm_agent_guard.llm_client import OpenAICompatibleClient
from llm_agent_guard.logging_utils import JsonlRunLogger
from llm_agent_guard.outcome_predictor import OutcomePredictor
from llm_agent_guard.predictive_controller import PredictiveController
from llm_agent_guard.schemas import (
    ControllerDecision,
    OutcomePrediction,
    ProposedAction,
    ReviewContext,
    to_jsonable,
)


REVISION_TEMPLATE = """
The previous proposed action was flagged as high-risk by a general action consequence predictor.

Risk reason:
{risk_reason}

Missing information:
{missing_information}

Please generate exactly one safer next action.
Do not explain.
Do not invent facts.
Use only information available in the conversation, observation, tools, and constraints.
""".strip()


class GuardedLLMAgentMixin:
    def _init_guard(self, guard_config: dict[str, Any], task: Any) -> None:
        self.guard_config = guard_config
        self.guard_mode = guard_config.get("mode", "direct")
        self.guard_run_name = guard_config.get("run_name", "guarded_run")
        self.guard_domain = guard_config.get("domain")
        self.guard_task_id = str(getattr(task, "id", guard_config.get("task_id", "unknown")))
        self.guard_task_goal = _task_goal(task)
        self.guard_soft_risk_level = guard_config.get("soft_risk_level", "critical")
        self.guard_soft_confidence_threshold = float(
            guard_config.get("soft_confidence_threshold", 0.7)
        )
        self.guard_controller = PredictiveController(
            self.guard_mode,
            soft_risk_level=self.guard_soft_risk_level,
            soft_confidence_threshold=self.guard_soft_confidence_threshold,
        )
        self.guard_logger = JsonlRunLogger(
            self.guard_run_name,
            root=Path(guard_config.get("runs_root", "runs")),
        )
        self.guard_step = 0
        self.guard_predictor: Optional[OutcomePredictor] = None
        if self.guard_controller.should_call_predictor():
            predictor_cfg = guard_config.get("predictor") or {}
            client = OpenAICompatibleClient(
                model=predictor_cfg.get("model"),
                base_url=predictor_cfg.get("base_url"),
                api_key=predictor_cfg.get("api_key")
                or os.environ.get(predictor_cfg.get("api_key_env", ""), ""),
                timeout=int(predictor_cfg.get("timeout", 120)),
            )
            self.guard_predictor = OutcomePredictor(client)

    def _guard_context(self, state: Any, message: Any) -> ReviewContext:
        return ReviewContext(
            task_goal=self.guard_task_goal,
            recent_history=_recent_history(state.messages),
            current_observation=_message_to_text(message),
            available_actions=_available_actions(self.tools),
            constraints=self.domain_policy,
            domain=self.guard_domain,
            metadata={"task_id": self.guard_task_id, "run_name": self.guard_run_name},
        )

    def _guard_review_action(
        self,
        proposed_message: Any,
        context: ReviewContext,
        base_messages: list[Any],
    ) -> tuple[Any, ProposedAction, ProposedAction, Optional[OutcomePrediction], ControllerDecision, bool]:
        proposed_action = _message_to_action(proposed_message)
        executed_message = proposed_message
        executed_action = proposed_action
        prediction = None
        decision = self.guard_controller.decide_before_execution(None)
        changed = False

        if self.guard_controller.should_call_predictor() and self.guard_predictor is not None:
            prediction = self.guard_predictor.predict(context, proposed_action)
            decision = self.guard_controller.decide_before_execution(prediction)
            if decision.decision == "revise_once":
                from tau2.data_model.message import SystemMessage
                from tau2.utils.llm_utils import generate

                feedback = REVISION_TEMPLATE.format(
                    risk_reason=prediction.risk_reason,
                    missing_information=", ".join(prediction.missing_information) or "unknown",
                )
                revised_messages = [
                    *base_messages,
                    SystemMessage(role="system", content=feedback),
                ]
                executed_message = generate(
                    model=self.llm,
                    tools=self.tools,
                    messages=revised_messages,
                    call_name="agent_response_revised_once",
                    **self.llm_args,
                )
                executed_action = _message_to_action(executed_message)
                changed = _actions_differ(proposed_action, executed_action)

        return executed_message, proposed_action, executed_action, prediction, decision, changed

    def _guard_record(
        self,
        proposed_action: ProposedAction,
        executed_action: ProposedAction,
        prediction: Optional[OutcomePrediction],
        decision: ControllerDecision,
        changed: bool,
    ) -> None:
        self.guard_step += 1
        row = {
            "run_name": self.guard_run_name,
            "domain": self.guard_domain,
            "task_id": self.guard_task_id,
            "step": self.guard_step,
            "mode": self.guard_mode,
            "soft_risk_level": self.guard_soft_risk_level,
            "soft_confidence_threshold": self.guard_soft_confidence_threshold,
            "proposed_action": asdict(proposed_action),
            "executed_action": asdict(executed_action),
            "prediction": _dataclass_or_none(prediction),
            "controller_decision": _dataclass_or_none(decision),
            "changed_by_controller": changed,
        }
        self.guard_logger.log_step(self.guard_task_id, row)


def create_guarded_llm_agent(tools, domain_policy, **kwargs):
    from tau2.agent.llm_agent import LLMAgent

    class GuardedLLMAgent(GuardedLLMAgentMixin, LLMAgent):
        def __init__(self, tools, domain_policy, llm, llm_args=None, task=None):
            llm_args = deepcopy(llm_args or {})
            guard_config = llm_args.pop("guard_config", {"mode": "direct"})
            super().__init__(
                tools=tools,
                domain_policy=domain_policy,
                llm=llm,
                llm_args=llm_args,
            )
            self._init_guard(guard_config, task)

        def _generate_next_message(self, message, state):
            from tau2.data_model.message import MultiToolMessage, UserMessage
            from tau2.utils.llm_utils import generate

            if isinstance(message, UserMessage) and message.is_audio:
                raise ValueError("User message cannot be audio. Use VoiceLLMAgent instead.")
            if isinstance(message, MultiToolMessage):
                state.messages.extend(message.tool_messages)
            else:
                state.messages.append(message)
            base_messages = state.system_messages + state.messages
            proposed_message = generate(
                model=self.llm,
                tools=self.tools,
                messages=base_messages,
                call_name="agent_response",
                **self.llm_args,
            )
            context = self._guard_context(state, message)
            (
                executed_message,
                proposed_action,
                executed_action,
                prediction,
                decision,
                changed,
            ) = self._guard_review_action(proposed_message, context, base_messages)
            self._guard_record(
                proposed_action,
                executed_action,
                prediction,
                decision,
                changed,
            )
            return executed_message

    return GuardedLLMAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=kwargs.get("llm"),
        llm_args=kwargs.get("llm_args"),
        task=kwargs.get("task"),
    )


def register_guarded_agent() -> None:
    from tau2.registry import registry

    if "guarded_llm_agent" not in registry.get_agents():
        registry.register_agent_factory(create_guarded_llm_agent, "guarded_llm_agent")


def _task_goal(task: Any) -> str:
    if task is None:
        return ""
    scenario = getattr(task, "user_scenario", None)
    instructions = getattr(scenario, "instructions", None)
    if instructions is not None:
        parts = []
        for name in ["task_instructions", "reason_for_call", "known_info", "unknown_info"]:
            value = getattr(instructions, name, None)
            if value:
                parts.append(f"{name}: {value}")
        if parts:
            return "\n".join(parts)
    return str(getattr(task, "id", ""))


def _recent_history(messages: list[Any], limit: int = 12) -> list[dict[str, Any]]:
    return [_message_to_dict(message) for message in messages[-limit:]]


def _message_to_dict(message: Any) -> dict[str, Any]:
    role = getattr(message, "role", type(message).__name__)
    data: dict[str, Any] = {"role": str(role)}
    content = getattr(message, "content", None)
    if content:
        data["content"] = str(content)[:4000]
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = [
            {
                "name": getattr(call, "name", None),
                "arguments": getattr(call, "arguments", None),
            }
            for call in tool_calls
        ]
    return data


def _message_to_text(message: Any) -> str:
    if message is None:
        return ""
    if hasattr(message, "tool_messages"):
        return "\n".join(_message_to_text(item) for item in message.tool_messages)
    content = getattr(message, "content", None)
    if content is not None:
        return str(content)
    return str(message)


def _available_actions(tools: list[Any]) -> list[dict[str, Any]]:
    actions = []
    for tool in tools:
        schema = getattr(tool, "openai_schema", None)
        if schema:
            function = schema.get("function", {})
            actions.append(
                {
                    "name": function.get("name"),
                    "description": function.get("description"),
                    "parameters": function.get("parameters"),
                }
            )
        else:
            actions.append({"name": getattr(tool, "name", str(tool))})
    return actions


def _message_to_action(message: Any) -> ProposedAction:
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        call = tool_calls[0]
        raw = [
            {"name": getattr(item, "name", None), "arguments": getattr(item, "arguments", None)}
            for item in tool_calls
        ]
        return ProposedAction(
            action_type="tool_call",
            raw=raw,
            tool_name=getattr(call, "name", None),
            tool_arguments=getattr(call, "arguments", None),
        )
    content = getattr(message, "content", None)
    if content:
        return ProposedAction(
            action_type="assistant_message",
            raw={"content": content},
            assistant_content=content,
        )
    return ProposedAction(action_type="unknown", raw=str(message))


def _dataclass_or_none(value: Any) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    return to_jsonable(value)


def _actions_differ(left: ProposedAction, right: ProposedAction) -> bool:
    return to_jsonable(left) != to_jsonable(right)
