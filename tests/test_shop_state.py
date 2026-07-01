from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data_loader import load_all_data
from game_state import GameState
from recommender import analyze_event


DATA_DIR = PROJECT_ROOT / "data"


def test_state_keeps_combat_health_separate_from_prestige() -> None:
    state = GameState.from_dict(
        {
            "hero": "Vanessa",
            "build": "VanessaAquaticAmmo",
            "day": 2,
            "health": 550,
            "prestige": 18,
        }
    )

    assert state.combat_health == 550
    assert state.health == 550
    assert state.prestige == 18
    assert state.max_prestige is None


def test_shop_prefers_visible_items_and_does_not_refresh_past_target() -> None:
    data = load_all_data(DATA_DIR)
    event = data["events"]["Colt"]
    result = analyze_event(
        event_name="Colt",
        event_data=event,
        cards=data["cards"],
        build_name="huokai",
        build_data=data["builds"]["huokai"],
        current_day=6,
        rarity_rules=data["rarity_rules"],
        current_hero="Vanessa",
        current_shop={
            "visible_items": [{"name": "Burnacuda"}],
            "refresh_available": True,
            "refresh_cost": 1,
        },
        current_gold=8,
    )

    assert [card["name"] for card in result["possible_cards"]] == ["Burnacuda"]
    assert result["shop_decision"]["action"] == "buy"
    assert result["shop_decision"]["visible_offer_count"] == 3
    assert result["shop_decision"]["refresh_offer_count"] == 3


def test_unknown_refresh_cost_never_pushes_refresh() -> None:
    data = load_all_data(DATA_DIR)
    event = data["events"]["Colt"]
    result = analyze_event(
        event_name="Colt",
        event_data=event,
        cards=data["cards"],
        build_name="huokai",
        build_data=data["builds"]["huokai"],
        current_day=6,
        rarity_rules=data["rarity_rules"],
        current_hero="Vanessa",
        current_shop={
            "visible_items": [{"name": "Unknown Visible Item"}],
            "refresh_available": True,
            "refresh_cost": None,
        },
        current_gold=20,
    )

    assert result["shop_decision"]["action"] == "skip"
    assert "未知" in result["shop_decision"]["reason"]
