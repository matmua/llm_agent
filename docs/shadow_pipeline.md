# Shadow Detection Pipeline

This project currently focuses on shadow detection, not intervention or
recovery. Shadow mode records risk and state-delta signals while executing the
agent's original action unchanged.

## Runtime Flow

```text
task_instruction, observation, available_actions, history
-> agent generates raw_action
-> StateManager updates state out of band
-> PreActionDetector checks raw_action
-> ShadowPolicy returns executed_action == raw_action
-> environment executes raw_action
-> StateManager updates state_after
-> PostActionDeltaVerifier compares expected_delta and observed_delta
-> logger writes step and episode JSONL
```

`shadow` mode does not call `RiskAwareActionRouter`, does not call
`MinimalStateRepair`, does not queue repair actions, and does not rewrite the
agent action.

## State Is Not Fed To The Agent

`--state_to_agent` defaults to `false`. In that configuration the ReAct prompt
contains task instruction, raw observation, available actions, and recent
history only. The state graph is available to detectors and analysis, not to
the acting policy.

Use `--state_to_agent true` only as an ablation.

## Generic StateGraph

The generic state layer lives in `state/base_state.py` and supports:

- `Entity`
- `AttributeRecord`
- `Constraint`
- `Relation`
- `GoalState`
- `ActionRecord`
- `StateGraph`

WebShop product fields such as price, color, size, and brand are domain-specific
instances of this schema. The same schema can represent non-WebShop entities
such as orders, rooms, objects, tools, tickets, or database records.

## LLM State Proposal

`LLMStateProposer` asks an LLM for a structured proposal. The proposal never
mutates state directly. `StateNormalizer` validates and normalizes the proposal,
then `StateManager` merges it while preserving provenance and conflicts.

Important rules:

- LLM proposes, code validates and maintains.
- High-confidence attributes require evidence text.
- User hard constraints are not overwritten by weaker proposals.
- Observation/environment evidence outranks weak LLM proposals.
- Conflicts are recorded instead of silently overwritten.
- LLM parse/request failures fall back to the domain adapter.

## WebShop Adapter

`state/domain_adapters/webshop_adapter.py` maps WebShop observations into
generic proposals. It handles page type, available actions, visible products,
current product, price, color, size, brand, and task constraints.

Future datasets should add a new adapter rather than rewriting the generic
state graph.

## State Builders

`runners.run_webshop_shadow` supports:

- `--state_builder rule`: WebShop adapter only.
- `--state_builder llm`: LLM proposal; adapter fallback on LLM failure.
- `--state_builder llm_hybrid`: LLM proposal plus WebShop adapter proposal.

Recommended smoke command:

```bash
./no_proxy_run.sh python -m runners.run_webshop_shadow \
  --env mock \
  --num_tasks 3 \
  --max_steps 6 \
  --model mock \
  --mode shadow \
  --state_builder llm_hybrid \
  --use_llm_state true \
  --state_to_agent false \
  --log_dir logs/webshop_shadow_clean_demo
```

Analyze:

```bash
./no_proxy_run.sh python -m analysis.analyze_shadow_logs \
  --log_dir logs/webshop_shadow_clean_demo \
  --report_dir reports/demo_shadow
```

## Post-Action Categories

The post verifier distinguishes:

- `explicit_conflict`: observed/state evidence clearly violates a hard constraint.
- `missing_evidence`: evidence is insufficient, but not a hard conflict by itself.
- `unexpected_transition`: page/state transition does not match expected delta.
- `no_effect`: action should advance state but observation barely changes.
- `preventable_failure`: final action failed after a high-risk/missing-evidence warning.
- `unsupported_state_update`: high-confidence state update has no evidence.

For compatibility, `constraint_conflict` remains as a category when an explicit
constraint conflict is found.

## Reading Reports

Shadow reports describe detector behavior and correlation with failure. They do
not claim success-rate improvement. The most useful metrics are:

- pre-warning recall on failed episodes
- post-error recall on failed episodes
- explicit conflict vs missing evidence counts
- pre-warning lead time before post errors
- LLM state parse success and fallback rate
- average entities/constraints per step
