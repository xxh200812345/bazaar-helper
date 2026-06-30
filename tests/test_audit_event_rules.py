from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from audit_event_rules import benefit_rule_kinds, is_recognized_event


def test_unknown_event_without_rule_is_not_recognized() -> None:
    event = {
        "event_category": "unknown_events",
        "resource_rewards": {"gold": 0},
    }

    assert not is_recognized_event(event)
    assert benefit_rule_kinds(event) == []


def test_effect_and_qualitative_rewards_are_benefit_rules() -> None:
    assert benefit_rule_kinds({"effect": "upgrade_items"}) == ["effect"]
    assert benefit_rule_kinds({"qualitative_rewards": ["regen"]}) == [
        "qualitative_rewards"
    ]


def test_empty_card_reward_is_not_a_benefit_rule() -> None:
    event = {
        "event_category": "item_rewards",
        "card_reward": {
            "enabled": True,
            "exact_names": [],
            "reward_tags": [],
        },
    }

    assert is_recognized_event(event)
    assert benefit_rule_kinds(event) == []
