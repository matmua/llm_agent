"""Dataset-specific repair decisions.

Policies sit after rule detection and LLM verification. They do not change
rule/verifier outputs; they only decide whether a verified risk should trigger
an intervention for the current dataset semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from intervention.action_space import candidate_action_texts


LOW_BUDGET_THRESHOLD = 3
MEDIUM_BUDGET_THRESHOLD = 6


@dataclass(frozen=True)
class RepairDecision:
    mode: str
    reason: str
    policy: str
    prompt_strength: str = "standard"
    action_class: str = "unknown"
    protected: bool = False
    stuck: bool = False
    completion_visible: bool = False
    remaining_steps: int | None = None
    budget_level: str = "unknown"
    budget_fraction: float | None = None
    task_progress: str = "unknown"
    completion_candidates: tuple[str, ...] = ()
    finalization_type: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "policy": self.policy,
            "prompt_strength": self.prompt_strength,
            "action_class": self.action_class,
            "protected": self.protected,
            "stuck": self.stuck,
            "completion_visible": self.completion_visible,
            "remaining_steps": self.remaining_steps,
            "budget_level": self.budget_level,
            "budget_fraction": self.budget_fraction,
            "task_progress": self.task_progress,
            "completion_candidates": list(self.completion_candidates),
            "finalization_type": self.finalization_type,
        }


class GenericDatasetPolicy:
    name = "generic"

    def decide_pre_repair(
        self,
        action_record: dict[str, Any],
        verification: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        blevel = budget_level(remaining_steps)
        if verification.get("is_error") is not True:
            return RepairDecision(
                mode="skip",
                reason="not_verified_error",
                policy=self.name,
                remaining_steps=remaining_steps,
                budget_level=blevel,
            )
        return RepairDecision(
            mode="pre_repair",
            reason="generic_verified_error",
            policy=self.name,
            prompt_strength="standard",
            action_class="unknown",
            remaining_steps=remaining_steps,
            budget_level=blevel,
        )

    def decide_post_hint(
        self,
        action_record: dict[str, Any],
        verification: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        blevel = budget_level(remaining_steps)
        if verification.get("is_error") is not True:
            return RepairDecision(
                mode="skip",
                reason="not_verified_error",
                policy=self.name,
                remaining_steps=remaining_steps,
                budget_level=blevel,
            )
        prompt_strength = "late" if is_low_budget(remaining_steps) else "standard"
        reason = "generic_low_budget_verified_error" if prompt_strength == "late" else "generic_verified_error"
        return RepairDecision(
            mode="hint",
            reason=reason,
            policy=self.name,
            prompt_strength=prompt_strength,
            action_class="unknown",
            remaining_steps=remaining_steps,
            budget_level=blevel,
        )

    def decide_budget_hint(
        self,
        action_record: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        return RepairDecision(
            mode="skip",
            reason="budget_hint_disabled",
            policy=self.name,
            action_class="unknown",
            remaining_steps=remaining_steps,
            budget_level=budget_level(remaining_steps),
        )


class StepBudgetPolicy(GenericDatasetPolicy):
    """Dataset-agnostic intervention policy using only remaining step budget."""

    name = "step_budget"

    def decide_pre_repair(
        self,
        action_record: dict[str, Any],
        verification: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        blevel = budget_level(remaining_steps)
        if verification.get("is_error") is not True:
            return RepairDecision(
                mode="skip",
                reason="not_verified_error",
                policy=self.name,
                action_class="unknown",
                remaining_steps=remaining_steps,
                budget_level=blevel,
            )
        if is_low_budget(remaining_steps):
            return RepairDecision(
                mode="pre_repair",
                reason="step_budget_low_budget_verified_pre_error",
                policy=self.name,
                prompt_strength="late",
                action_class="unknown",
                remaining_steps=remaining_steps,
                budget_level=blevel,
            )
        return RepairDecision(
            mode="record_only",
            reason="step_budget_record_pre_error_until_low_budget",
            policy=self.name,
            prompt_strength="none",
            action_class="unknown",
            remaining_steps=remaining_steps,
            budget_level=blevel,
        )

    def decide_post_hint(
        self,
        action_record: dict[str, Any],
        verification: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        blevel = budget_level(remaining_steps)
        if verification.get("is_error") is not True:
            return RepairDecision(
                mode="skip",
                reason="not_verified_error",
                policy=self.name,
                action_class="unknown",
                remaining_steps=remaining_steps,
                budget_level=blevel,
            )
        low_budget = is_low_budget(remaining_steps)
        return RepairDecision(
            mode="hint",
            reason="step_budget_low_budget_post_hint" if low_budget else "step_budget_standard_post_hint",
            policy=self.name,
            prompt_strength="late" if low_budget else "standard",
            action_class="unknown",
            remaining_steps=remaining_steps,
            budget_level=blevel,
        )


class SimpleBudgetV2Policy(StepBudgetPolicy):
    """Small generic policy: budget gating plus guarded completion when stuck."""

    name = "simple_budget_v2"

    def decide_post_hint(
        self,
        action_record: dict[str, Any],
        verification: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        blevel = budget_level(remaining_steps)
        completion_candidates = visible_completion_candidates(observation, available_actions)
        if verification.get("is_error") is not True:
            return RepairDecision(
                mode="skip",
                reason="not_verified_error",
                policy=self.name,
                action_class="unknown",
                remaining_steps=remaining_steps,
                budget_level=blevel,
                completion_candidates=completion_candidates,
                completion_visible=bool(completion_candidates),
            )

        low_budget = is_low_budget(remaining_steps)
        post_check = action_record.get("post_check") or {}
        stalled_count = int(post_check.get("same_action_no_visible_delta_count") or 0)
        if (
            verification.get("error_type") == "loop_or_repetition"
            and stalled_count >= 3
            and completion_candidates
        ):
            return RepairDecision(
                mode="hint",
                reason=(
                    "simple_budget_low_budget_stalled_repeat"
                    if low_budget
                    else "simple_budget_stalled_repeat_with_completion_candidate"
                ),
                policy=self.name,
                prompt_strength="late" if low_budget else "finish_guarded",
                action_class="unknown",
                protected=False,
                stuck=True,
                completion_visible=True,
                remaining_steps=remaining_steps,
                budget_level=blevel,
                completion_candidates=completion_candidates,
            )

        return RepairDecision(
            mode="hint",
            reason="simple_budget_low_budget_post_hint" if low_budget else "simple_budget_standard_post_hint",
            policy=self.name,
            prompt_strength="late" if low_budget else "standard",
            action_class="unknown",
            completion_visible=bool(completion_candidates),
            remaining_steps=remaining_steps,
            budget_level=blevel,
            completion_candidates=completion_candidates,
        )


class SimpleBudgetPolicy(SimpleBudgetV2Policy):
    """V3 simple budget policy with a generic finalization nudge."""

    name = "simple_budget"

    def decide_budget_hint(
        self,
        action_record: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        blevel = budget_level_for_task(remaining_steps, max_steps)
        bfrac = budget_fraction(remaining_steps, max_steps)
        completion_candidates = visible_completion_candidates(observation, available_actions)
        finalization_type = infer_finalization_type(
            task,
            observation,
            available_actions,
            completion_candidates,
        )
        task_progress = task_progress_signal(task, observation, available_actions, action_record)
        if not is_final_budget(remaining_steps, max_steps):
            return RepairDecision(
                mode="skip",
                reason="simple_budget_no_finalization_nudge",
                policy=self.name,
                action_class="unknown",
                remaining_steps=remaining_steps,
                budget_level=blevel,
                budget_fraction=bfrac,
                task_progress=task_progress,
                completion_candidates=completion_candidates,
                completion_visible=bool(completion_candidates),
                finalization_type=finalization_type,
            )
        return RepairDecision(
            mode="hint",
            reason="simple_budget_generic_finalization_nudge",
            policy=self.name,
            prompt_strength="budget_finish",
            action_class="unknown",
            completion_visible=bool(completion_candidates),
            remaining_steps=remaining_steps,
            budget_level=blevel,
            budget_fraction=bfrac,
            task_progress=task_progress,
            completion_candidates=completion_candidates,
            finalization_type=finalization_type,
        )


class SimpleBudgetV4Policy(SimpleBudgetPolicy):
    """V4 replaces the old strict verifier policy with generic v3 finalization."""

    name = "simple_budget_v4"


class TaskAwarePolicy(GenericDatasetPolicy):
    """Dataset-agnostic policy that uses task-local progress signals."""

    name = "task_aware"

    def decide_pre_repair(
        self,
        action_record: dict[str, Any],
        verification: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        base = self._base_decision_kwargs(
            action_record=action_record,
            observation=observation,
            available_actions=available_actions,
            remaining_steps=remaining_steps,
            max_steps=max_steps,
            task=task,
        )
        if verification.get("is_error") is not True:
            return RepairDecision(mode="skip", reason="not_verified_error", **base)

        error_type = verification.get("error_type")
        if error_type == "format_error":
            return RepairDecision(
                mode="pre_repair",
                reason="task_aware_format_error",
                prompt_strength="standard",
                **base,
            )

        if is_low_budget_level(base["budget_level"]):
            return RepairDecision(
                mode="pre_repair",
                reason="task_aware_low_budget_verified_pre_error",
                prompt_strength="task_late",
                **base,
            )

        return RepairDecision(
            mode="record_only",
            reason="task_aware_record_pre_error_until_low_budget",
            prompt_strength="none",
            **base,
        )

    def decide_post_hint(
        self,
        action_record: dict[str, Any],
        verification: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        base = self._base_decision_kwargs(
            action_record=action_record,
            observation=observation,
            available_actions=available_actions,
            remaining_steps=remaining_steps,
            max_steps=max_steps,
            task=task,
        )
        if verification.get("is_error") is not True:
            return RepairDecision(mode="skip", reason="not_verified_error", **base)

        low_budget = is_low_budget_level(base["budget_level"])
        return RepairDecision(
            mode="hint",
            reason="task_aware_low_budget_post_hint" if low_budget else "task_aware_standard_post_hint",
            prompt_strength="task_late" if low_budget else "standard",
            **base,
        )

    def _base_decision_kwargs(
        self,
        action_record: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        remaining_steps: int | None,
        max_steps: int | None,
        task: str,
    ) -> dict[str, Any]:
        blevel = budget_level_for_task(remaining_steps, max_steps)
        completion_candidates = visible_completion_candidates(observation, available_actions)
        return {
            "policy": self.name,
            "action_class": "unknown",
            "remaining_steps": remaining_steps,
            "budget_level": blevel,
            "budget_fraction": budget_fraction(remaining_steps, max_steps),
            "task_progress": task_progress_signal(task, observation, available_actions, action_record),
            "completion_candidates": completion_candidates,
            "completion_visible": bool(completion_candidates),
        }


class WebShopPolicy(GenericDatasetPolicy):
    name = "webshop"

    def decide_pre_repair(
        self,
        action_record: dict[str, Any],
        verification: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        blevel = budget_level(remaining_steps)
        if verification.get("is_error") is not True:
            return RepairDecision(
                mode="skip",
                reason="not_verified_error",
                policy=self.name,
                remaining_steps=remaining_steps,
                budget_level=blevel,
            )

        error_type = verification.get("error_type")
        action_class = classify_webshop_action(action_record)
        if error_type == "format_error":
            return RepairDecision(
                mode="pre_repair",
                reason="format_error",
                policy=self.name,
                prompt_strength="standard",
                action_class=action_class,
                remaining_steps=remaining_steps,
                budget_level=blevel,
            )

        if error_type == "loop_or_repetition":
            if action_class in {"navigation", "search"}:
                return RepairDecision(
                    mode="pre_repair",
                    reason="webshop_navigation_or_search_repeat",
                    policy=self.name,
                    prompt_strength="strong",
                    action_class=action_class,
                    remaining_steps=remaining_steps,
                    budget_level=blevel,
                )
            if self._is_protected_local_stuck(
                action_record=action_record,
                observation=observation,
                available_actions=available_actions,
                shadow_state=shadow_state,
            ):
                return RepairDecision(
                    mode="pre_repair",
                    reason="webshop_protected_local_repeat_stuck_completion_visible",
                    policy=self.name,
                    prompt_strength="completion",
                    action_class=action_class,
                    protected=False,
                    stuck=True,
                    completion_visible=True,
                    remaining_steps=remaining_steps,
                    budget_level=blevel,
                )
            return RepairDecision(
                mode="record_only",
                reason="webshop_protected_local_repeat",
                policy=self.name,
                prompt_strength="none",
                action_class=action_class,
                protected=True,
                completion_visible=has_buy_now(observation, available_actions),
                remaining_steps=remaining_steps,
                budget_level=blevel,
            )

        return RepairDecision(
            mode="pre_repair",
            reason="webshop_verified_non_loop_error",
            policy=self.name,
            prompt_strength="standard",
            action_class=action_class,
            remaining_steps=remaining_steps,
            budget_level=blevel,
        )

    def decide_post_hint(
        self,
        action_record: dict[str, Any],
        verification: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        remaining_steps: int | None = None,
        max_steps: int | None = None,
        task: str = "",
    ) -> RepairDecision:
        blevel = budget_level(remaining_steps)
        if verification.get("is_error") is not True:
            return RepairDecision(
                mode="skip",
                reason="not_verified_error",
                policy=self.name,
                remaining_steps=remaining_steps,
                budget_level=blevel,
            )

        error_type = verification.get("error_type")
        action_class = classify_webshop_action(action_record)
        completion_visible = has_buy_now(observation, available_actions)
        low_budget = is_low_budget(remaining_steps)
        if error_type == "loop_or_repetition":
            if self._is_protected_local_stuck(
                action_record=action_record,
                observation=observation,
                available_actions=available_actions,
                shadow_state=shadow_state,
                include_current=True,
            ):
                return RepairDecision(
                    mode="hint",
                    reason="webshop_protected_local_repeat_stuck_completion_visible",
                    policy=self.name,
                    prompt_strength="completion",
                    action_class=action_class,
                    protected=False,
                    stuck=True,
                    completion_visible=True,
                    remaining_steps=remaining_steps,
                    budget_level=blevel,
                )
            if action_class in {"product", "option"} and low_budget and completion_visible:
                return RepairDecision(
                    mode="hint",
                    reason="webshop_low_budget_local_repeat_completion_visible",
                    policy=self.name,
                    prompt_strength="completion",
                    action_class=action_class,
                    protected=False,
                    stuck=False,
                    completion_visible=True,
                    remaining_steps=remaining_steps,
                    budget_level=blevel,
                )
            if action_class in {"product", "option", "completion"}:
                return RepairDecision(
                    mode="hint",
                    reason=(
                        "webshop_low_budget_protected_local_repeat"
                        if low_budget
                        else "webshop_protected_local_repeat_soft_hint"
                    ),
                    policy=self.name,
                    prompt_strength="late" if low_budget else "soft",
                    action_class=action_class,
                    protected=True,
                    completion_visible=completion_visible,
                    remaining_steps=remaining_steps,
                    budget_level=blevel,
                )

        return RepairDecision(
            mode="hint",
            reason="webshop_low_budget_standard_post_hint" if low_budget else "webshop_standard_post_hint",
            policy=self.name,
            prompt_strength="late" if low_budget else "standard",
            action_class=action_class,
            completion_visible=completion_visible,
            remaining_steps=remaining_steps,
            budget_level=blevel,
        )

    def _is_protected_local_stuck(
        self,
        action_record: dict[str, Any],
        observation: str,
        available_actions: dict[str, Any],
        shadow_state: dict[str, Any] | None = None,
        include_current: bool = False,
    ) -> bool:
        action_class = classify_webshop_action(action_record)
        if action_class not in {"product", "option"}:
            return False
        if not has_buy_now(observation, available_actions):
            return False
        if include_current:
            post_check = action_record.get("post_check") or {}
            return int(post_check.get("same_action_no_visible_delta_count") or 0) >= 3
        return _previous_same_action_no_visible_delta_count(action_record, shadow_state) >= 3


def get_dataset_policy(name: str, requested_env: str = "", env_name: str = "") -> GenericDatasetPolicy:
    resolved = (name or "auto").strip().lower()
    if resolved == "auto":
        haystack = f"{requested_env} {env_name}".lower()
        resolved = "webshop" if "webshop" in haystack or requested_env in {"official", "mock"} else "simple_budget"
    if resolved == "webshop":
        return WebShopPolicy()
    if resolved in {"simple_budget_v2", "simple_v2"}:
        return SimpleBudgetV2Policy()
    if resolved in {"simple_budget_v4", "simple_v4", "universal_v4"}:
        return SimpleBudgetV4Policy()
    if resolved in {"simple_budget", "simple", "simple_step", "simple_budget_v3", "simple_v3"}:
        return SimpleBudgetPolicy()
    if resolved in {"step_budget", "step", "budget"}:
        return StepBudgetPolicy()
    if resolved in {"task_aware", "task", "general_task"}:
        return TaskAwarePolicy()
    if resolved == "generic":
        return GenericDatasetPolicy()
    raise ValueError(f"unknown dataset policy: {name!r}")


def classify_webshop_action(action_record: dict[str, Any]) -> str:
    parsed = (
        action_record.get("original_parsed_action")
        or action_record.get("parsed_action")
        or {}
    )
    action_type = parsed.get("type", action_record.get("type"))
    params = parsed.get("params") or action_record.get("params") or {}
    if action_type == "search":
        return "search"
    if action_type != "click":
        return "other"

    target = str(params.get("target") or "").strip()
    normalized = _normalize_target(target)
    if normalized in {"next >", "next", "< prev", "prev", "previous", "back to search"}:
        return "navigation"
    if normalized == "buy now":
        return "completion"
    if re.fullmatch(r"b[0-9a-z]{9}", normalized):
        return "product"
    return "option"


def budget_level(remaining_steps: int | None) -> str:
    if remaining_steps is None:
        return "unknown"
    if remaining_steps <= 1:
        return "final"
    if remaining_steps <= LOW_BUDGET_THRESHOLD:
        return "low"
    if remaining_steps <= MEDIUM_BUDGET_THRESHOLD:
        return "medium"
    return "high"


def budget_level_for_task(remaining_steps: int | None, max_steps: int | None) -> str:
    if remaining_steps is None:
        return "unknown"
    if max_steps is None or max_steps <= 0:
        return budget_level(remaining_steps)
    fraction = budget_fraction(remaining_steps, max_steps)
    if remaining_steps <= 1:
        return "final"
    if fraction is not None and fraction <= 0.2:
        return "low"
    if fraction is not None and fraction <= 0.5:
        return "medium"
    return "high"


def budget_fraction(remaining_steps: int | None, max_steps: int | None) -> float | None:
    if remaining_steps is None or max_steps is None or max_steps <= 0:
        return None
    return max(0.0, min(1.0, float(remaining_steps) / float(max_steps)))


def is_low_budget(remaining_steps: int | None) -> bool:
    return budget_level(remaining_steps) in {"low", "final"}


def is_low_budget_level(level: str) -> bool:
    return level in {"low", "final"}


def is_final_budget(remaining_steps: int | None, max_steps: int | None = None) -> bool:
    if remaining_steps is None:
        return False
    if remaining_steps <= 1:
        return True
    fraction = budget_fraction(remaining_steps, max_steps)
    return fraction is not None and fraction <= 0.1


def infer_finalization_type(
    task: str,
    observation: str,
    available_actions: Any,
    completion_candidates: tuple[str, ...] = (),
) -> str:
    completion_texts = completion_candidates or visible_completion_candidates(observation, available_actions)
    text = _normalize_target(
        " ".join(
            str(part)
            for part in (
                task,
                observation,
                " ".join(str(item) for item in completion_texts),
            )
            if part
        )
    )
    if _has_any_keyword(text, ("pytest", "test", "tests", "check", "verify", "validate", "grade")):
        return "verify"
    if _has_any_keyword(text, ("save", "write", "output", "export", "file", "report", "result")):
        return "deliverable"
    if completion_texts:
        return "commit"
    return "last_gap"


def visible_completion_candidates(
    observation: str,
    available_actions: Any,
) -> tuple[str, ...]:
    keywords = (
        "submit",
        "finish",
        "done",
        "complete",
        "confirm",
        "checkout",
        "purchase",
        "buy",
        "answer",
        "final",
        "test",
        "pytest",
        "check",
        "verify",
        "validate",
        "save",
        "write",
        "output",
        "export",
        "result",
        "grade",
    )
    candidates: list[str] = []
    for item in candidate_action_texts(available_actions):
        text = str(item).strip()
        normalized = _normalize_target(text)
        if _has_any_keyword(normalized, keywords):
            candidates.append(text)
    if not candidates:
        normalized_observation = _normalize_target(observation or "")
        for keyword in keywords:
            if _has_keyword(normalized_observation, keyword):
                candidates.append(keyword)
                break
    return tuple(candidates[:3])


def task_progress_signal(
    task: str,
    observation: str,
    available_actions: Any,
    action_record: dict[str, Any],
) -> str:
    task_terms = _content_terms(task)
    if not task_terms:
        return "unknown"
    visible_text = observation or ""
    visible_text += " " + " ".join(candidate_action_texts(available_actions))
    visible_terms = _content_terms(visible_text)
    action_terms = _content_terms(
        action_record.get("raw_action")
        or action_record.get("executed_action")
        or action_record.get("raw")
        or ""
    )
    if task_terms & action_terms:
        return "task_aligned_action"
    if task_terms & visible_terms:
        return "task_evidence_visible"
    return "no_task_evidence_visible"


def verifier_progress(verification: dict[str, Any]) -> str:
    value = str(verification.get("progress_assessment") or "uncertain").strip().lower()
    return value if value in {"progressed", "no_progress", "uncertain"} else "uncertain"


def verifier_intervention(verification: dict[str, Any]) -> str:
    value = str(verification.get("should_intervene") or "").strip().lower()
    if value in {"yes", "no", "soft"}:
        return value
    return "yes" if verification.get("is_error") is True else "no"


def action_made_progress(action_record: dict[str, Any]) -> bool:
    post_check = action_record.get("post_check") or {}
    return post_check.get("visible_delta") is True or post_check.get("info_gain") is True


def is_hard_stuck(action_record: dict[str, Any], verification: dict[str, Any] | None = None) -> bool:
    post_check = action_record.get("post_check") or {}
    if post_check.get("no_progress") is True or post_check.get("context_cycle_detected") is True:
        return True
    if int(post_check.get("same_action_no_visible_delta_count") or 0) >= 2:
        return True
    if verification and verifier_progress(verification) == "no_progress":
        return True
    return False


def previous_hint_recovered(action_record: dict[str, Any]) -> bool:
    repair = action_record.get("repair") or {}
    applied = repair.get("hint_applied_from_previous_step") or {}
    if applied.get("applied") is not True or applied.get("followed") is not True:
        return False
    return action_made_progress(action_record)


def has_buy_now(observation: str, available_actions: Any) -> bool:
    for item in candidate_action_texts(available_actions):
        if _normalize_target(str(item)) == "buy now":
            return True
    return "buy now" in _normalize_target(observation or "")


def _normalize_target(target: str) -> str:
    return " ".join(target.strip().lower().split())


def _has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(_has_keyword(text, keyword) for keyword in keywords)


def _has_keyword(text: str, keyword: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(_normalize_target(keyword)) + r"(?![a-z0-9])"
    return re.search(pattern, _normalize_target(text or "")) is not None


def _content_terms(text: str) -> set[str]:
    stopwords = {
        "the",
        "and",
        "or",
        "a",
        "an",
        "to",
        "of",
        "for",
        "with",
        "in",
        "on",
        "at",
        "by",
        "me",
        "find",
        "need",
        "want",
        "please",
        "instruction",
        "task",
        "click",
        "search",
        "price",
        "less",
        "lower",
        "than",
    }
    terms = set()
    for token in re.findall(r"[a-zA-Z0-9]+", (text or "").lower()):
        if len(token) < 3:
            continue
        if token in stopwords:
            continue
        terms.add(token)
    return terms


def _previous_same_action_no_visible_delta_count(
    action_record: dict[str, Any],
    shadow_state: dict[str, Any] | None,
) -> int:
    if not shadow_state:
        return 0
    context = action_record.get("context_before")
    signature = action_record.get("action_signature")
    if not context or not signature:
        return 0
    count = 0
    for previous in shadow_state.get("actions", []):
        if previous.get("context_before") != context:
            continue
        if previous.get("action_signature") != signature:
            continue
        post_check = previous.get("post_check") or {}
        visible_delta = post_check.get("visible_delta", post_check.get("info_gain"))
        if visible_delta is False:
            count += 1
    return count
