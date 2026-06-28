from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE_DIR / "runtime"
DATA_DIR = BASE_DIR / "data"
LIVE_CARDS_PATH = RUNTIME_DIR / "live_cards_raw.json"
CARDS_OUTPUT_PATH = DATA_DIR / "cards_generated.json"
CARDS_BACKUP_PATH = DATA_DIR / "cards_generated.backup.json"

RARITY_NAMES = {
    "bronze": "Bronze",
    "silver": "Silver",
    "gold": "Gold",
    "diamond": "Diamond",
    "legendary": "Legendary",
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_tags(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_text(value).lower()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def normalize_heroes(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def normalize_rarity(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""

    mapped = RARITY_NAMES.get(text.lower())
    return mapped or text


def normalize_rarity_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        rarity = normalize_rarity(value)
        if not rarity or rarity in seen:
            continue
        seen.add(rarity)
        result.append(rarity)
    return result


def normalize_price_map(values: Any) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {}

    result: dict[str, Any] = {}
    for key, value in values.items():
        rarity = normalize_rarity(key)
        if rarity:
            result[rarity] = value
    return result


def read_live_cards(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)

    if isinstance(payload, list):
        return [card for card in payload if isinstance(card, dict)]

    if isinstance(payload, dict):
        cards = payload.get("cards")
        if isinstance(cards, list):
            return [card for card in cards if isinstance(card, dict)]

    raise ValueError(f"Unsupported live card payload: {path}")


def first_nonempty(*values: Any) -> str:
    for value in values:
        text = normalize_text(value)
        if text:
            return text
    return ""


def merge_visible_tags(tags: list[str], hidden_tags: list[str], visible_tags: Any) -> list[str]:
    if isinstance(visible_tags, list):
        normalized = normalize_tags(visible_tags)
        if normalized:
            return normalized

    hidden = {tag.lower() for tag in hidden_tags}
    return [tag for tag in tags if tag.lower() not in hidden]


def convert_card(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = first_nonempty(raw.get("name"), raw.get("internal_name"), raw.get("source_id"), raw.get("template_id"))
    if not name:
        return None

    heroes = normalize_heroes(raw.get("heroes"))
    hero = normalize_text(raw.get("hero"))
    if not hero and len(heroes) == 1:
        hero = heroes[0]

    visible_source_tags = normalize_tags(raw.get("tags"))
    hidden_tags = normalize_tags(raw.get("hidden_tags"))
    tags = normalize_tags([*visible_source_tags, *hidden_tags])
    tiers = normalize_rarity_list(raw.get("tiers"))
    rarity = normalize_rarity(raw.get("rarity")) or (tiers[0] if tiers else "")
    min_rarity = normalize_rarity(raw.get("min_rarity")) or (tiers[0] if tiers else rarity)
    max_rarity = normalize_rarity(raw.get("max_rarity")) or (tiers[-1] if tiers else rarity)
    source_id = first_nonempty(raw.get("source_id"), raw.get("id"))
    template_id = first_nonempty(raw.get("template_id"), source_id)

    return {
        "id": first_nonempty(source_id, template_id, name),
        "source_id": source_id,
        "template_id": template_id,
        "internal_name": normalize_text(raw.get("internal_name")),
        "name": name,
        "hero": hero,
        "heroes": heroes,
        "type": normalize_text(raw.get("type") or raw.get("card_type")),
        "size": normalize_text(raw.get("size")),
        "min_rarity": min_rarity,
        "max_rarity": max_rarity,
        "rarity": rarity,
        "tiers": tiers,
        "tags": tags,
        "visible_tags": merge_visible_tags(
            visible_source_tags,
            hidden_tags,
            raw.get("visible_tags"),
        ),
        "hidden_tags": hidden_tags,
        "buy_prices": normalize_price_map(raw.get("buy_prices")),
        "sell_prices": normalize_price_map(raw.get("sell_prices")),
        "description": normalize_text(raw.get("description")),
        "card_pack_id": normalize_text(raw.get("card_pack_id")),
    }


def build_cards(raw_cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for raw in raw_cards:
        card = convert_card(raw)
        if not card:
            continue

        key = card["name"]
        if key in cards:
            key = f"{key} <{card['id'][:8]}>"
        cards[key] = card
    return dict(sorted(cards.items(), key=lambda item: item[0].lower()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import live Bazaar card cache into data/cards_generated.json.")
    parser.add_argument("--input", type=Path, default=LIVE_CARDS_PATH)
    parser.add_argument("--output", type=Path, default=CARDS_OUTPUT_PATH)
    parser.add_argument("--backup", type=Path, default=CARDS_BACKUP_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Missing live card export: {args.input}")

    raw_cards = read_live_cards(args.input)
    cards = build_cards(raw_cards)

    if args.output.exists():
        args.backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.output, args.backup)

    write_json(args.output, cards)
    print(f"Read live cards: {len(raw_cards)}")
    print(f"Wrote cards_generated.json: {len(cards)}")
    print(f"Backup: {args.backup}")


if __name__ == "__main__":
    main()
