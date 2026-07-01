from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stage_build_matcher import analyze_stage_builds, normalize_build


def _data() -> dict:
    return {
        "builds": {
            "old": {
                "hero": "Vanessa",
                "name": "Old",
                "phase": "early",
                "core_cards": ["Old Core"],
                "optional_cards": [],
            },
            "now": {
                "hero": "Vanessa",
                "name": "Now",
                "phase": "mid",
                "core_cards": ["A", "B", "C"],
                "optional_cards": ["D"],
            },
            "later": {
                "hero": "Vanessa",
                "name": "Later",
                "phase": "late",
                "core_cards": ["B", "L"],
                "optional_cards": [],
            },
        },
        "cards": {
            name: {
                "size": "Small",
                "buy_prices": {"silver": 3},
            }
            for name in ("Old Core", "A", "B", "C", "D", "L", "Other")
        },
    }


def test_legacy_non_core_cards_become_optional() -> None:
    normalized = normalize_build(
        "legacy",
        {
            "hero": "Vanessa",
            "applicable_stages": ["mid", "late"],
            "core_cards": ["A"],
            "transition_cards": ["B"],
            "optional_cards": ["C"],
        },
    )

    assert normalized["phase"] == "mid"
    assert normalized["optional_cards"] == ["B", "C"]


def test_past_core_is_ignored_and_current_close_core_is_critical() -> None:
    result = analyze_stage_builds(
        data=_data(),
        hero="Vanessa",
        day=7,
        owned_cards={"A", "B"},
        candidates=[
            {"name": "Old Core", "rarity": "silver"},
            {"name": "C", "rarity": "silver"},
        ],
        gold=10,
        prestige=15,
        inventory_slots_used=5,
        inventory_slots_total=10,
        current_shop={"refresh_available": True, "refresh_cost": 1},
    )

    cards = {item["card_name"]: item for item in result["candidate_cards"]}
    assert cards["Old Core"]["importance"] == "ignored"
    assert cards["Old Core"]["recommendation_type"] == "skip"
    assert cards["C"]["importance"] == "critical"
    assert cards["C"]["recommendation_type"] == "buy_now"
    assert result["shop_action"] == "buy_visible"


def test_visible_core_bundle_only_uses_actual_candidates() -> None:
    result = analyze_stage_builds(
        data=_data(),
        hero="Vanessa",
        day=7,
        owned_cards={"A"},
        candidates=[
            {"name": "B", "rarity": "silver"},
            {"name": "C", "rarity": "silver"},
        ],
        gold=10,
        prestige=15,
        inventory_slots_used=5,
        inventory_slots_total=10,
        current_shop={"refresh_available": True, "refresh_cost": 1},
    )

    bundle = result["visible_core_bundles"][0]
    assert bundle["candidate_core_cards"] == ["B", "C"]
    assert bundle["owned_core_after_if_bought"] == ["A", "B", "C"]
    assert bundle["recommendation"] == "consider_buying_together"


def test_future_stash_with_unknown_resources_requests_ai_judgement() -> None:
    result = analyze_stage_builds(
        data=_data(),
        hero="Vanessa",
        day=7,
        owned_cards=set(),
        candidates=[{"name": "L", "rarity": "silver"}],
        gold=None,
        prestige=None,
        inventory_slots_used=None,
        inventory_slots_total=None,
        current_shop={"refresh_available": True, "refresh_cost": None},
    )

    card = result["candidate_cards"][0]
    assert card["recommendation_type"] == "stash_future"
    assert card["needs_ai_judgement"] is True
    assert result["shop_action"] == "unknown"


def test_live_candidate_price_takes_priority_over_missing_static_price() -> None:
    data = _data()
    data["cards"]["C"]["buy_prices"] = {}
    result = analyze_stage_builds(
        data=data,
        hero="Vanessa",
        day=7,
        owned_cards={"A", "B"},
        candidates=[{"name": "C", "rarity": "silver", "price": 4}],
        gold=5,
        prestige=15,
        inventory_slots_used=5,
        inventory_slots_total=10,
        current_shop={"refresh_available": True, "refresh_cost": 1},
    )

    card = result["candidate_cards"][0]
    assert card["price"] == 4
    assert card["affordable"] is True
