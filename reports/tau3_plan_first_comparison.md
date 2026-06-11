# Tau3 Retail Plan-First Comparison

Date: 2026-06-11

This compares the original direct Qwen3-8B agent with a private plan-first
variant on the same local tau3 retail base subset: tasks `0 1 2 3 4`.

The plan-first variant asks the model to privately predict the next action's
consequence, risk, cost, and recommendation before generating the real
tool/user action.

## Runs

| run | agent mode | tasks | success | accuracy | notes |
|---|---|---:|---:|---:|---|
| `20260611_tau3_retail_qwen3_8b_subset5_local_eval` | direct | 5 | 1 | 20.0% | baseline |
| `20260611_tau3_retail_qwen3_8b_subset5_plan_first` | plan_first V1 | 1 | 0 | 0.0% | diagnostic partial run; long planning prompt caused repeated invalid item lookup |
| `20260611_tau3_retail_qwen3_8b_subset5_plan_first_v2` | plan_first V2 | 5 | 0 | 0.0% | compact planning prompt; full comparison run |

## Per-Task Comparison

| task | direct result | plan-first V2 result | observed change |
|---|---|---|---|
| 0 | success, reward 1.0 | `too_many_errors`, reward 0.0 | regression; guessed product IDs and repeated failed reads |
| 1 | `db_state_failed`, reward 0.0 | `too_many_errors`, reward 0.0 | regression; repeated invalid order lookup |
| 2 | `db_state_failed`, reward 0.0 | `nl_assertion_failed`, reward 0.0 | partial improvement; DB passed, but final message said 9 options instead of expected 10 |
| 3 | `nl_assertion_failed`, reward 0.0 | `nl_assertion_failed`, reward 0.0 | no success gain; still missed required order checks and final count |
| 4 | `max_steps`, reward 0.0 | `max_steps`, reward 0.0 | no improvement; became slower and looped in clarification |

## Failure Roots

Plan-first V1 exposed the clearest failure mode:

- Task 0 repeatedly called `get_item_details` on known-bad or guessed item IDs.
- It hit `too_many_errors` after five `Item not found` errors.
- The baseline direct agent completed task 0 successfully, so this was a true
  strategy regression rather than an environment problem.

Plan-first V2 reduced the verbosity and tool-call count, but did not improve
task success:

- Tasks 0 and 1 still terminated with `too_many_errors`.
- Task 2 performed the write-side DB state correctly, but failed the required
  natural-language assertion by reporting only 9 available options rather than
  stating the expected total of 10 t-shirt options.
- Task 3 modified an order, but not the expected order/item path, and still
  failed the required "10 t-shirt options" assertion.
- Task 4 stayed in clarification loops until `max_steps`.

## Cost And Risk

The plan-first call roughly doubles agent LLM calls because each real turn has
an extra private planning completion. On this local 5-task run it also increased
average wall time:

| mode | total tool calls | average task duration |
|---|---:|---:|
| direct | 46 | 13.1s |
| plan-first V2 | 31 | 34.9s |

The lower tool-call count in plan-first V2 is not a quality gain; two tasks
terminated early from repeated tool errors, and one task hit `max_steps` mostly
through user-facing clarification.

Recommendation: do not use this naive text plan-first mode as the default for
Qwen3-8B on tau3 retail. It makes the agent more cautious in wording, but it
also anchors the model on guessed IDs and repeats invalid lookups.

## Better Next Direction

The more promising intervention is a code-level action reviewer/guardrail
instead of another free-form planning message:

- block exact repeated tool calls after a tool error;
- reject guessed IDs unless they came from user text or prior tool output;
- require read-only evidence before write tools;
- require explicit confirmation before write tools;
- add a final-answer checklist for benchmark-sensitive assertions such as
  product-option counts.

That should preserve the baseline success while targeting the actual failure
roots visible in the trajectories.

## Artifacts

- Baseline trajectory: `trajectories/20260611_tau3_retail_qwen3_8b_subset5_local_eval`
- Plan-first V1 diagnostic: `trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first`
- Plan-first V2 full run: `trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first_v2`
- Baseline report: `reports/tau3_retail_subset_summary.md`
- V1 diagnostic report: `reports/tau3_retail_plan_first_v1_diagnostic.md`
- V2 report: `reports/tau3_retail_plan_first_v2_summary.md`
