"""Controller policy for direct, shadow, and soft prediction modes."""

from __future__ import annotations

from llm_agent_guard.schemas import ControllerDecision, OutcomePrediction


RISK_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


def _risk_value(risk_level: str | None) -> int:
    return RISK_ORDER.get(str(risk_level or "").lower(), RISK_ORDER["medium"])


class PredictiveController:
    def __init__(
        self,
        mode: str,
        soft_risk_level: str = "critical",
        soft_confidence_threshold: float = 0.7,
    ):
        assert mode in ["direct", "predictor_shadow", "predictor_soft"]
        self.mode = mode
        self.soft_risk_level = (
            soft_risk_level
            if soft_risk_level in RISK_ORDER
            else "medium"
        )
        self.soft_confidence_threshold = float(soft_confidence_threshold)

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
        if (
            _risk_value(prediction.risk_level) >= _risk_value(self.soft_risk_level)
            and prediction.confidence >= self.soft_confidence_threshold
            and prediction.recommendation in ["revise", "ask_user", "recover", "stop"]
        ):
            return ControllerDecision(
                decision="revise_once",
                reason=(
                    "soft mode risk threshold met: "
                    f"risk>={self.soft_risk_level}, "
                    f"confidence>={self.soft_confidence_threshold}"
                ),
                prediction=prediction,
            )
        return ControllerDecision(
            decision="execute",
            reason=(
                "soft mode risk threshold not met: "
                f"risk>={self.soft_risk_level}, "
                f"confidence>={self.soft_confidence_threshold}"
            ),
            prediction=prediction,
        )
