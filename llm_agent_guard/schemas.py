"""Shared generic schemas for action outcome prediction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Literal, Optional


ActionType = Literal["tool_call", "assistant_message", "unknown"]
RiskLevel = Literal["low", "medium", "high", "critical"]
TaskProgress = Literal["improve", "neutral", "degrade", "unknown"]
Recoverability = Literal["easy", "medium", "hard", "irreversible"]
Recommendation = Literal["execute", "revise", "ask_user", "recover", "stop"]
PreferredActionType = Literal[
    "ask_user",
    "read_tool",
    "write_tool",
    "final_message",
    "unknown",
]
Actionability = Literal["high", "medium", "low"]

FailureMode = Literal[
    "none",
    "invalid_action",
    "wrong_target",
    "missing_evidence",
    "goal_drift",
    "irreversible_change",
    "loop_risk",
    "policy_violation",
    "unknown",
]


@dataclass
class ProposedAction:
    action_type: ActionType
    raw: Any
    tool_name: Optional[str] = None
    tool_arguments: Optional[Dict[str, Any]] = None
    assistant_content: Optional[str] = None


@dataclass
class ReviewContext:
    task_goal: str
    recent_history: List[Dict[str, Any]]
    current_observation: Optional[str]
    available_actions: Optional[List[Dict[str, Any]]]
    constraints: Optional[str] = None
    domain: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutcomePrediction:
    predicted_outcome: str
    task_progress: TaskProgress
    risk_level: RiskLevel
    risk_reason: str
    missing_information: List[str]
    possible_failure_mode: FailureMode
    recoverability: Recoverability
    confidence: float
    recommendation: Recommendation
    unsafe_action_summary: str = ""
    safe_action_constraint: str = ""
    forbidden_action_pattern: str = ""
    preferred_action_type: PreferredActionType = "unknown"
    actionability: Actionability = "medium"
    intervention_confidence: float = 0.0
    raw_response: Optional[str] = None


@dataclass
class ControllerDecision:
    decision: Literal["execute", "revise_once"]
    reason: str
    prediction: Optional[OutcomePrediction] = None


def clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return min(1.0, max(0.0, number))


def coerce_literal(value: Any, allowed: set[str], default: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return default


def coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def prediction_from_dict(data: dict[str, Any], raw_response: Optional[str]) -> OutcomePrediction:
    return OutcomePrediction(
        predicted_outcome=str(data.get("predicted_outcome") or ""),
        task_progress=coerce_literal(
            data.get("task_progress"),
            {"improve", "neutral", "degrade", "unknown"},
            "unknown",
        ),  # type: ignore[arg-type]
        risk_level=coerce_literal(
            data.get("risk_level"),
            {"low", "medium", "high", "critical"},
            "medium",
        ),  # type: ignore[arg-type]
        risk_reason=str(
            data.get("risk_reason") or "Predictor returned incomplete output."
        ),
        missing_information=coerce_string_list(data.get("missing_information")),
        possible_failure_mode=coerce_literal(
            data.get("possible_failure_mode"),
            {
                "none",
                "invalid_action",
                "wrong_target",
                "missing_evidence",
                "goal_drift",
                "irreversible_change",
                "loop_risk",
                "policy_violation",
                "unknown",
            },
            "unknown",
        ),  # type: ignore[arg-type]
        recoverability=coerce_literal(
            data.get("recoverability"),
            {"easy", "medium", "hard", "irreversible"},
            "medium",
        ),  # type: ignore[arg-type]
        confidence=clamp_confidence(data.get("confidence")),
        recommendation=coerce_literal(
            data.get("recommendation"),
            {"execute", "revise", "ask_user", "recover", "stop"},
            "execute",
        ),  # type: ignore[arg-type]
        unsafe_action_summary=str(data.get("unsafe_action_summary") or ""),
        safe_action_constraint=str(data.get("safe_action_constraint") or ""),
        forbidden_action_pattern=str(data.get("forbidden_action_pattern") or ""),
        preferred_action_type=coerce_literal(
            data.get("preferred_action_type"),
            {"ask_user", "read_tool", "write_tool", "final_message", "unknown"},
            "unknown",
        ),  # type: ignore[arg-type]
        actionability=coerce_literal(
            data.get("actionability"),
            {"high", "medium", "low"},
            "medium",
        ),  # type: ignore[arg-type]
        intervention_confidence=clamp_confidence(
            data.get("intervention_confidence")
        ),
        raw_response=raw_response,
    )


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value
