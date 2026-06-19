from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from agents.react_agent import WebShopReactAgent
from analysis.analyze_shadow_logs import analyze_shadow_logs
from detectors.post_action import PostActionDeltaVerifier, PostActionReport
from detectors.pre_action import PreActionDetector
from policies.risk_router import RiskAwareActionRouter
from policies.shadow_policy import ShadowInterventionPolicy
from repair.checkpoint_manager import CheckpointManager
from repair.minimal_state_repair import MinimalStateRepair
from runners.run_webshop_shadow import run_webshop_shadow
from state.base_state import StateGraph
from state.domain_adapters.webshop_adapter import WebShopAdapter
from state.entity_state import StateManager
from state.llm_state_proposer import LLMStateProposalResult
from state.state_normalizer import StateNormalizer


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

    def test_agent_prompt_omits_state_summary_when_disabled(self) -> None:
        prompt = WebShopReactAgent._build_prompt(
            task_instruction="Find a red mug.",
            observation="Search page",
            action_history=[],
            available_actions={"has_search_bar": True, "clickables": []},
            state_summary="",
        )
        self.assertNotIn("Current task state summary", prompt)

    def test_llm_state_proposal_merges_valid_json(self) -> None:
        proposal = {
            "entities": [
                {
                    "entity_type": "order",
                    "name": "order-1",
                    "attributes": [
                        {
                            "name": "status",
                            "value": "pending",
                            "source": "llm_proposal",
                            "confidence": "medium",
                            "evidence_text": "The order is pending.",
                        }
                    ],
                }
            ],
            "constraints": [
                {
                    "target_entity_type": "order",
                    "attribute_name": "status",
                    "operator": "equals",
                    "expected_value": "pending",
                    "source": "user_instruction",
                    "evidence_text": "Keep the order pending.",
                    "strictness": "hard",
                }
            ],
        }
        normalizer = StateNormalizer()
        normalized = normalizer.normalize(proposal, step_id=0)
        merged = normalizer.merge(StateGraph(), normalized.graph, step_id=0)
        self.assertEqual(len(merged.graph.entities), 1)
        self.assertEqual(len(merged.graph.constraints), 1)
        self.assertTrue(merged.graph.validate()[0])

    def test_llm_state_parse_failure_falls_back_to_adapter(self) -> None:
        class BadProposer:
            def propose(self, **kwargs):
                return LLMStateProposalResult(
                    raw_response="not json",
                    parse_error="failed_to_parse_json_object",
                )

        manager = StateManager(
            state_builder="llm_hybrid",
            use_llm_state=True,
            llm_state_proposer=BadProposer(),
        )
        manager.reset(
            "Find a red mug under $20.",
            "Instruction [SEP] Red Ceramic Mug [SEP] Price: $14.99",
            {"has_search_bar": False, "clickables": ["buy now"]},
            step_id=0,
        )
        self.assertTrue(manager.last_update_metadata["state_fallback_used"])
        self.assertEqual(
            manager.last_update_metadata["llm_state_proposal_parse_error"],
            "failed_to_parse_json_object",
        )
        self.assertGreater(len(manager.generic_graph.entities), 0)

    def test_generic_state_graph_accepts_non_webshop_entities(self) -> None:
        proposal = {
            "entities": [
                {
                    "entity_type": "room",
                    "name": "kitchen",
                    "attributes": [
                        {
                            "name": "light",
                            "value": "on",
                            "source": "observation",
                            "confidence": "high",
                            "evidence_text": "The kitchen light is on.",
                        }
                    ],
                },
                {
                    "entity_type": "object",
                    "name": "apple",
                    "attributes": [
                        {
                            "name": "location",
                            "value": "kitchen",
                            "source": "observation",
                            "confidence": "high",
                            "evidence_text": "The apple is in the kitchen.",
                        }
                    ],
                },
            ]
        }
        graph = StateNormalizer().normalize(proposal, step_id=0).graph
        self.assertEqual(len(graph.entities), 2)
        self.assertTrue(graph.validate()[0])

    def test_webshop_adapter_outputs_generic_product_proposal(self) -> None:
        proposal = WebShopAdapter().build_proposal(
            task_instruction="Find a red mug under $20.",
            observation="Instruction [SEP] Red Ceramic Mug [SEP] Price: $14.99 [SEP] Buy Now",
            available_actions={"has_search_bar": False, "clickables": ["buy now"]},
            step_id=0,
        )
        self.assertTrue(any(item.get("entity_type") == "product" for item in proposal["entities"]))
        self.assertTrue(any(item.get("attribute_name") == "price" for item in proposal["constraints"]))

    def test_risk_router_completes_missing_attribute_before_buy(self) -> None:
        manager = _state(
            "Find a green mug under $20.",
            "Instruction [SEP] Ceramic Mug [SEP] Price: $14.99 [SEP] buy now",
            {"has_search_bar": False, "clickables": ["description", "features", "reviews", "buy now"]},
        )
        report = PreActionDetector().detect(
            task_instruction="Find a green mug under $20.",
            observation="Instruction [SEP] Ceramic Mug [SEP] Price: $14.99 [SEP] buy now",
            raw_action="click[buy now]",
            available_actions={"has_search_bar": False, "clickables": ["description", "features", "reviews", "buy now"]},
            state_manager=manager,
            action_history=[],
        )
        decision = RiskAwareActionRouter().decide_before_action(
            pre_action_report=report,
            state_manager=manager,
            raw_action="click[buy now]",
            available_actions={"has_search_bar": False, "clickables": ["description", "features", "reviews", "buy now"]},
            action_history=[],
            observation="Instruction [SEP] Red Ceramic Mug [SEP] Price: $14.99 [SEP] buy now",
        )
        self.assertNotEqual(decision.executed_action, "click[buy now]")
        self.assertIn(decision.executed_action, {"click[description]", "click[features]", "click[reviews]"})
        self.assertTrue(decision.metadata["changed_action"])

    def test_risk_router_allows_raw_after_completion_exhausted(self) -> None:
        manager = _state(
            "Find a green mug under $20.",
            "Instruction [SEP] Ceramic Mug [SEP] Price: $14.99 [SEP] buy now",
            {"has_search_bar": False, "clickables": ["description", "features", "reviews", "buy now"]},
        )
        report = PreActionDetector().detect(
            task_instruction="Find a green mug under $20.",
            observation="Instruction [SEP] Ceramic Mug [SEP] Price: $14.99 [SEP] buy now",
            raw_action="click[buy now]",
            available_actions={"has_search_bar": False, "clickables": ["description", "features", "reviews", "buy now"]},
            state_manager=manager,
            action_history=[
                {"executed_action": "click[description]"},
                {"executed_action": "click[features]"},
                {"executed_action": "click[reviews]"},
            ],
        )
        decision = RiskAwareActionRouter().decide_before_action(
            pre_action_report=report,
            state_manager=manager,
            raw_action="click[buy now]",
            available_actions={"has_search_bar": False, "clickables": ["description", "features", "reviews", "buy now"]},
            action_history=[
                {"executed_action": "click[description]"},
                {"executed_action": "click[features]"},
                {"executed_action": "click[reviews]"},
            ],
            observation="Instruction [SEP] Ceramic Mug [SEP] Price: $14.99 [SEP] buy now",
        )
        self.assertEqual(decision.executed_action, "click[buy now]")
        self.assertFalse(decision.metadata["changed_action"])
        self.assertEqual(decision.metadata["intervention_type"], "completion_exhausted_allow_raw")

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

    def test_price_upper_bound_is_satisfied_by_lower_price(self) -> None:
        manager = _state(
            "Find a red mug under $20.",
            "Instruction [SEP] Red Ceramic Mug [SEP] Price: $14.99 [SEP] Color: red [SEP] buy now",
            {"has_search_bar": False, "clickables": ["buy now"]},
        )
        self.assertNotIn("price_constraint", manager.missing_hard_constraints_for_current_product())

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

    def test_missing_color_evidence_is_not_explicit_conflict(self) -> None:
        report = PostActionDeltaVerifier().verify(
            task_instruction="Find a red mug.",
            observation_before="results",
            observation_after="Instruction [SEP] Ceramic Mug [SEP] Price: $14.99 [SEP] buy now",
            raw_action="click[ceramic mug]",
            pre_action_report={"expected_delta": {"expected_page_type": "product_page"}},
            state_before={"page_state": {"page_type": {"value": "results_page"}}},
            state_after={
                "page_state": {"page_type": {"value": "product_page"}},
                "task_requirement": {"color_constraint": {"value": "red"}},
            },
            reward=0.0,
            done=False,
            info={},
        )
        self.assertIn("missing_evidence", report.error_categories)
        self.assertNotIn("explicit_conflict", report.error_categories)
        self.assertFalse(report.post_error)

    def test_price_over_budget_is_explicit_conflict(self) -> None:
        report = PostActionDeltaVerifier().verify(
            task_instruction="Find a mug under $20.",
            observation_before="results",
            observation_after="Instruction [SEP] Ceramic Mug [SEP] Price: $29.99 [SEP] buy now",
            raw_action="click[ceramic mug]",
            pre_action_report={"expected_delta": {"expected_page_type": "product_page"}},
            state_before={"page_state": {"page_type": {"value": "results_page"}}},
            state_after={
                "page_state": {"page_type": {"value": "product_page"}},
                "task_requirement": {"price_constraint": {"value": 20}},
            },
            reward=0.0,
            done=False,
            info={},
        )
        self.assertIn("explicit_conflict", report.error_categories)
        self.assertIn("constraint_conflict", report.error_categories)
        self.assertTrue(report.post_error)

    def test_minimal_repair_clears_contaminated_slot_and_queues_action(self) -> None:
        available = {"has_search_bar": False, "clickables": ["description", "features", "reviews", "buy now", "back to search"]}
        manager = _state(
            "Find a red mug under $20.",
            "Instruction [SEP] Blue Travel Mug [SEP] Price: $18.50 [SEP] Color: blue [SEP] buy now",
            available,
        )
        checkpoint_manager = CheckpointManager()
        checkpoint = checkpoint_manager.create(
            task_id=0,
            step_id=2,
            observation="product page",
            available_actions=available,
            state_snapshot=manager.snapshot(),
            action_history=[],
        )
        repair = MinimalStateRepair().repair_after_action(
            post_action_report=PostActionReport(
                post_error=True,
                error_categories=["constraint_conflict"],
                potential_contaminated_slots=["current_product.color"],
                hypothetical_repair_needed=True,
            ),
            state_manager=manager,
            checkpoint_manager=checkpoint_manager,
            checkpoint_id=checkpoint.checkpoint_id,
            available_actions=available,
            action_history=[],
            done=False,
        )
        self.assertTrue(repair.repair_needed)
        self.assertTrue(repair.repair_executed)
        self.assertIn("blue travel mug.color", repair.repaired_slots)
        self.assertEqual(repair.repair_action, "click[back to search]")

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
                    use_llm_state="false",
                    state_builder="rule",
                    state_to_agent="false",
                    mode="shadow",
                )
            )
            steps = [
                json.loads(line)
                for line in (Path(tmp) / "steps.jsonl").read_text().splitlines()
                if line.strip()
            ]
            self.assertGreater(len(steps), 0)
            self.assertTrue(all(step["raw_action"] == step["executed_action"] for step in steps))
            self.assertTrue(all(not step["agent_prompt_contains_state_summary"] for step in steps))
            self.assertTrue(all(step["state_to_agent"] is False for step in steps))

    def test_mock_runner_intervention_changes_only_intervention_mode(self) -> None:
        with tempfile.TemporaryDirectory() as direct_tmp, tempfile.TemporaryDirectory() as intervention_tmp:
            base_args = dict(
                num_tasks=1,
                start_index=1,
                max_steps=4,
                model="mock",
                shadow="true",
                env="mock",
                webshop_repo="external/webshop",
                num_products=1000,
                use_llm_judge=False,
                use_llm_state="false",
                state_builder="rule",
                state_to_agent="false",
            )
            run_webshop_shadow(Namespace(**base_args, mode="direct", log_dir=direct_tmp))
            run_webshop_shadow(Namespace(**base_args, mode="intervention", log_dir=intervention_tmp))
            direct_steps = _read_steps(Path(direct_tmp))
            intervention_steps = _read_steps(Path(intervention_tmp))
            self.assertTrue(all(step["raw_action"] == step["executed_action"] for step in direct_steps))
            self.assertTrue(any(step["raw_action"] != step["executed_action"] for step in intervention_steps))


def _state(
    instruction: str,
    observation: str,
    available_actions: dict | None = None,
) -> StateManager:
    available = available_actions or {"has_search_bar": True, "clickables": []}
    manager = StateManager()
    manager.reset(instruction, observation, available, step_id=0)
    return manager


def _read_steps(log_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (log_dir / "steps.jsonl").read_text().splitlines()
        if line.strip()
    ]


if __name__ == "__main__":
    unittest.main()
