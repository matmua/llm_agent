"""Controller policy for direct, shadow, and soft prediction modes."""

from __future__ import annotations

from llm_agent_guard.schemas import ControllerDecision, OutcomePrediction


RISK_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


ACTIONABILITY_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


def risk_value(risk_level: str | None) -> int:
    return RISK_ORDER.get(str(risk_level or "").lower(), RISK_ORDER["medium"])


def actionability_value(actionability: str | None) -> int:
    return ACTIONABILITY_ORDER.get(
        str(actionability or "").lower(),
        ACTIONABILITY_ORDER["medium"],
    )


class PredictiveController:
    def __init__(
        self,
        mode: str,
        controller_version: str = "v2",
        soft_risk_level: str = "high",
        soft_confidence_threshold: float = 0.6,
        soft_intervention_confidence_threshold: float = 0.6,
    ):
        assert mode in ["direct", "predictor_shadow", "predictor_soft"]
        self.mode = mode
        self.controller_version = controller_version
        self.soft_risk_level = (
            soft_risk_level
            if soft_risk_level in RISK_ORDER
            else "high"
        )
        self.soft_confidence_threshold = float(soft_confidence_threshold)
        self.soft_intervention_confidence_threshold = float(
            soft_intervention_confidence_threshold
        )

    def should_call_predictor(self) -> bool:
        return self.mode in ["predictor_shadow", "predictor_soft"]

    def decide_before_execution(
        self, prediction: OutcomePrediction | None
    ) -> ControllerDecision:
        if self.mode == "direct" or prediction is None:
            return ControllerDecision(decision="execute", reason="direct mode")
        if self.mode == "predictor_shadow":
            return ControllerDecision(
                decision="execute",
                reason="shadow mode records prediction only",
                prediction=prediction,
            )
        should_revise = (
            self.mode == "predictor_soft"
            and risk_value(prediction.risk_level) >= risk_value(self.soft_risk_level)
            and prediction.confidence >= self.soft_confidence_threshold
            and prediction.intervention_confidence
            >= self.soft_intervention_confidence_threshold
            and prediction.recommendation in ["revise", "ask_user", "recover", "stop"]
            and actionability_value(prediction.actionability)
            >= ACTIONABILITY_ORDER["medium"]
            and bool(prediction.safe_action_constraint.strip())
        )
        if should_revise:
            return ControllerDecision(
                decision="revise_once",
                reason=(
                    f"{self.controller_version} soft mode threshold met: "
                    f"risk>={self.soft_risk_level}, "
                    f"confidence>={self.soft_confidence_threshold}, "
                    "intervention_confidence>="
                    f"{self.soft_intervention_confidence_threshold}, "
                    "actionability>=medium, safe_action_constraint present"
                ),
                prediction=prediction,
            )
        return ControllerDecision(
            decision="execute",
            reason=(
                f"{self.controller_version} soft mode threshold not met: "
                f"risk>={self.soft_risk_level}, "
                f"confidence>={self.soft_confidence_threshold}, "
                "intervention_confidence>="
                f"{self.soft_intervention_confidence_threshold}, "
                "actionability>=medium, safe_action_constraint present"
            ),
            prediction=prediction,
        )
