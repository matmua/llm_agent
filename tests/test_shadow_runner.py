import json
from argparse import Namespace

from runners.run_webshop_shadow import run_webshop_shadow


def test_mock_shadow_runner_keeps_raw_action_and_hides_state(tmp_path):
    log_dir = tmp_path / "logs"
    run_webshop_shadow(
        Namespace(
            env="mock",
            webshop_repo="external/webshop",
            num_products=1000,
            num_tasks=1,
            start_index=0,
            max_steps=6,
            model="mock",
            state_to_agent="false",
            log_dir=str(log_dir),
        )
    )

    config = json.loads((log_dir / "config.json").read_text(encoding="utf-8"))
    steps = [
        json.loads(line)
        for line in (log_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    episodes = [
        json.loads(line)
        for line in (log_dir / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert config["shadow"] is True
    assert config["state_to_agent"] is False
    assert steps
    assert all(step["raw_action"] == step["executed_action"] for step in steps)
    assert not any(step["agent_prompt_contains_state_summary"] for step in steps)
    assert episodes[0]["action_changed_steps"] == 0
