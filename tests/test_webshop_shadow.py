from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from analysis.analyze_shadow_logs import analyze_shadow_logs
from detectors.post_action import PostActionDeltaVerifier
from detectors.pre_action import PreActionDetector
from policies.shadow_policy import ShadowInterventionPolicy
from runners.run_webshop_shadow import run_webshop_shadow
from state.entity_state import StateManager


class WebShopShadowTests(unittest.TestCase):
    def test_shadow_policy_preserves_action(self) -> None:
        manager = _state("Find a red mug under $20.", "Instruction [SEP] Red Ceramic Mug [SEP] Price: $14.99")
        detector = PreActionDetector()
        report = detector.detect(
            task_instruction="Find a red mug under $20.",
            observation="Instruction [SEP] Red Ceramic Mug [SEP] Price: $14.99 [SEP] buy now",
            raw_action="click[buy now]",
            available_actions={"has_search_bar": False, "clickables": ["buy now"]},
            state_manager=manager,
            action_history=[],
        )
        decision = ShadowInterventionPolicy().decide_before_action(report, "click[buy now]")
        self.assertEqual(decision.executed_action, "click[buy now]")
        self.assertTrue(decision.allow_execute)

    def test_invalid_action_is_marked(self) -> None:
        manager = _state("Find a red mug.", "Instruction [SEP] Search page")
        report = PreActionDetector().detect(
            task_instruction="Find a red mug.",
            observation="Instruction [SEP] Search page",
            raw_action="open[foo]",
            available_actions={"has_search_bar": True, "clickables": []},
            state_manager=manager,
            action_history=[],
        )
        self.assertIn("invalid_action", report.risk_categories)
        self.assertEqual(report.risk_level, "high")

    def test_buy_now_missing_attribute_is_marked(self) -> None:
        manager = _state(
            "Find a red mug under $20.",
            "Instruction [SEP] Blue Travel Mug [SEP] Price: $18.50 [SEP] buy now",
            {"has_search_bar": False, "clickables": ["buy now"]},
        )
        report = PreActionDetector().detect(
            task_instruction="Find a red mug under $20.",
            observation="Instruction [SEP] Blue Travel Mug [SEP] Price: $18.50 [SEP] buy now",
            raw_action="click[buy now]",
            available_actions={"has_search_bar": False, "clickables": ["buy now"]},
            state_manager=manager,
            action_history=[],
        )
        self.assertTrue({"missing_attribute", "premature_buy"} & set(report.risk_categories))

    def test_no_effect_is_marked(self) -> None:
        verifier = PostActionDeltaVerifier()
        report = verifier.verify(
            task_instruction="Find a mug.",
            observation_before="same observation",
            observation_after="same observation",
            raw_action="search[mug]",
            pre_action_report={"expected_delta": {"expected_page_type": "results_page", "expected_new_information": True}},
            state_before={"page_state": {"page_type": {"value": "search_page"}}},
            state_after={"page_state": {"page_type": {"value": "search_page"}}},
            reward=0.0,
            done=False,
            info={},
        )
        self.assertIn("action_no_effect", report.error_categories)
        self.assertTrue(report.post_error)

    def test_state_graph_schema_valid(self) -> None:
        manager = _state(
            "Find a red mug under $20.",
            "Instruction [SEP] Red Ceramic Mug [SEP] Price: $14.99",
            {"has_search_bar": False, "clickables": ["buy now"]},
        )
        valid, errors = manager.graph.validate()
        self.assertTrue(valid, errors)

    def test_analyzer_generates_metrics_from_fake_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "logs"
            report_dir = Path(tmp) / "reports"
            log_dir.mkdir()
            (log_dir / "config.json").write_text(json.dumps({"run_id": "fake", "env": "fake"}))
            step = {
                "task_id": 0,
                "step_id": 0,
                "raw_action": "click[buy now]",
                "pre_action_report": {
                    "risk_level": "high",
                    "risk_categories": ["missing_attribute"],
                    "missing_attributes": ["color_constraint"],
                    "reason": "missing",
                },
                "post_action_report": {
                    "post_error": True,
                    "error_categories": ["potential_preventable_failure"],
                    "reason": "failed buy",
                },
                "reward": 0.0,
                "done": True,
            }
            episode = {
                "task_id": 0,
                "task_instruction": "Find a red mug.",
                "final_success": False,
                "final_reward": 0.0,
                "num_steps": 1,
                "first_high_risk_step": 0,
                "first_post_error_step": 0,
                "had_potential_preventable_failure": True,
            }
            (log_dir / "steps.jsonl").write_text(json.dumps(step) + "\n")
            (log_dir / "episodes.jsonl").write_text(json.dumps(episode) + "\n")
            metrics = analyze_shadow_logs(log_dir, report_dir)
            self.assertEqual(metrics["total_episodes"], 1)
            self.assertEqual(metrics["failed_episode_warning_recall"], 1.0)
            self.assertTrue((report_dir / "webshop_shadow_summary.md").exists())

    def test_mock_runner_preserves_shadow_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_webshop_shadow(
                Namespace(
                    num_tasks=2,
                    start_index=0,
                    max_steps=4,
                    model="mock",
                    log_dir=tmp,
                    shadow="true",
                    env="mock",
                    webshop_repo="external/webshop",
                    num_products=1000,
                    use_llm_judge=False,
                )
            )
            steps = [
                json.loads(line)
                for line in (Path(tmp) / "steps.jsonl").read_text().splitlines()
                if line.strip()
            ]
            self.assertGreater(len(steps), 0)
            self.assertTrue(all(step["raw_action"] == step["executed_action"] for step in steps))


def _state(
    instruction: str,
    observation: str,
    available_actions: dict | None = None,
) -> StateManager:
    available = available_actions or {"has_search_bar": True, "clickables": []}
    manager = StateManager()
    manager.reset(instruction, observation, available, step_id=0)
    return manager


if __name__ == "__main__":
    unittest.main()

