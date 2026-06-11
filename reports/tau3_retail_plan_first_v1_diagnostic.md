# Tau3 Retail Subset Summary

- Run dir: `/root/autodl-tmp/llm_agent/trajectories/20260611_tau3_retail_qwen3_8b_subset5_plan_first`
- Total simulations: 1
- Scored simulations: 1
- Infrastructure/premature errors: 1
- Successes: 0
- Accuracy over all attempted tasks: 0.0000
- Accuracy over scored tasks: 0.0000

## Failure Types

- premature_termination:too_many_errors: 1

## Per Task

| task_id | reward | termination | failure_type | tool_calls | messages |
|---|---:|---|---|---:|---:|
| 0 | 0.0 | too_many_errors | premature_termination:too_many_errors | 9 | 20 |

## Official Reference

These are full benchmark leaderboard pass^1 retail numbers from the tau3-bench repository snapshot. They are not directly comparable to this local 5-task run because this run uses Qwen3-8B as both agent and user simulator, and also uses a local Qwen evaluator for NL assertions.

- Qwen3.5-397B-A17B retail pass^1: 84.43%
- Qwen3-Max-Thinking retail pass^1: 79.39%
- GPT-4.1 retail pass^1: 74.00%
- o4-mini retail pass^1: 68.30%

## Failure Trace Notes

### Task 0 - premature_termination:too_many_errors
- Last user: Hi there! I hope you're doing well. I have a request regarding my recent order. My order number is W2378156, and I received the mechanical keyboard and the smart thermostat. I would like to exchange the mechanical keyboard for one with clicky switches. If there isn't a keyboard that has clicky switches, RGB backlight, and is full size, I'm okay with one that...
- Last assistant: Hi! How can I help you today?
- Tool error at turn 11: Error: Item not found
- Tool error at turn 13: Error: Item not found
- Tool error at turn 15: Error: Item not found
- Tool error at turn 17: Error: Item not found
- Tool error at turn 19: Error: Item not found

