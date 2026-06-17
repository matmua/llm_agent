"""Controller policy for direct, shadow, and soft prediction modes."""

from __future__ import annotations

from llm_agent_guard.schemas import ControllerDecision, OutcomePrediction


class PredictiveController:
    def __init__(self, mode: str):
        assert mode in ["direct", "predictor_shadow", "predictor_soft"]
        self.mode = mode

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
            prediction.risk_level == "critical"
            and prediction.confidence >= 0.7
            and prediction.recommendation in ["revise", "ask_user", "recover", "stop"]
        ):
            return ControllerDecision(
                decision="revise_once",
                reason="critical high-confidence risk",
                prediction=prediction,
            )
        return ControllerDecision(
            decision="execute",
            reason="soft mode risk threshold not met",
            prediction=prediction,
        )
