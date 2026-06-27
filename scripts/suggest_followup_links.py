from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
EVENTS_PATH = BASE_DIR / "data" / "events.json"
TRANSLATIONS_PATH = BASE_DIR / "data" / "translations_zh_cn.json"
MISSING_PATHS = [
    BASE_DIR / "runtime" / "missing_events.json",
    BASE_DIR / "runtime" / "missing_events.before_filter_fix.json",
]


def load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_events(raw_events: dict[str, Any]):
    for category, events in raw_events.items():
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            name = event.get("name")
            if name:
                yield category, name, event


def build_source_id_index(raw_events: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}

    for _, name, event in iter_events(raw_events):
        source_ids = event.get("source_ids", [])
        source_id = event.get("source_id")
        if source_id:
            source_ids = [source_id, *source_ids]

        for value in source_ids:
            if value:
                index[str(value).lower()] = name

    return index


def build_name_to_location(raw_events: dict[str, Any]) -> dict[str, tuple[str, int]]:
    result: dict[str, tuple[str, int]] = {}

    for category, events in raw_events.items():
        if not isinstance(events, list):
            continue

        for index, event in enumerate(events):
            if isinstance(event, dict) and event.get("name"):
                result[str(event["name"])] = (category, index)

    return result


def has_direct_value(event: dict[str, Any]) -> bool:
    if event.get("shop_pool"):
        return True
    if event.get("card_reward", {}).get("enabled"):
        return True

    resource_rewards = event.get("resource_rewards", {})
    if isinstance(resource_rewards, dict):
        if any(value for value in resource_rewards.values()):
            return True

    category = event.get("event_category")
    if category in {"shops", "item_rewards", "resource_events"}:
        return True

    event_type = event.get("event_type")
    if event_type in {"item_reward", "resource_event"}:
        return True

    return False


def is_parent_candidate(event: dict[str, Any]) -> bool:
    if event.get("followup_options") or event.get("followup_option_names"):
        return False

    if has_direct_value(event):
        return False

    event_type = str(event.get("event_type", ""))
    return event_type in {"utility_event", "choice_event", "unknown_event", ""}


def collect_observed_groups(missing: dict[str, Any]) -> list[list[str]]:
    groups: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    for item in missing.values():
        ids = item.get("raw_event_option_template_ids", [])
        if not isinstance(ids, list):
            continue

        group = tuple(str(value).lower() for value in ids if value)
        if not group or group in seen:
            continue

        seen.add(group)
        groups.append(list(group))

    return groups


def main() -> None:
    raw_events = load_json(EVENTS_PATH)
    translations = load_json(TRANSLATIONS_PATH)
    by_id = translations.get("by_id", {})

    source_id_index = build_source_id_index(raw_events)
    name_location = build_name_to_location(raw_events)

    event_lookup = {
        name: event
        for _, name, event in iter_events(raw_events)
    }

    suggestions: dict[str, set[str]] = {}

    for missing_path in MISSING_PATHS:
        missing = load_json(missing_path)
        if not isinstance(missing, dict):
            continue

        for group in collect_observed_groups(missing):
            known_names = []
            unknown_ids = []

            for template_id in group:
                name = source_id_index.get(template_id)
                if not name:
                    translated = by_id.get(template_id)
                    if translated:
                        unknown_ids.append(f"{template_id} -> {translated}")
                    else:
                        unknown_ids.append(template_id)
                    continue

                known_names.append(name)

            if len(known_names) < 2:
                continue

            parent_names = [
                name
                for name in known_names
                if is_parent_candidate(event_lookup.get(name, {}))
            ]

            child_names = [
                name
                for name in known_names
                if has_direct_value(event_lookup.get(name, {}))
            ]

            for parent_name in parent_names:
                for child_name in child_names:
                    if child_name != parent_name:
                        suggestions.setdefault(parent_name, set()).add(child_name)

    if not suggestions:
        print("没有找到可自动关联的父事件。")
        return

    print("建议关联：")
    for parent_name, child_names in sorted(suggestions.items()):
        print("=" * 80)
        print(parent_name)
        for child_name in sorted(child_names):
            print(f"  - {child_name}")

    answer = input("\n是否写入 data/events.json？输入 YES 确认：").strip()
    if answer != "YES":
        print("未写入。")
        return

    for parent_name, child_names in suggestions.items():
        location = name_location.get(parent_name)
        if not location:
            continue

        category, index = location
        event = raw_events[category][index]
        existing = set(event.get("followup_option_names", []))
        event["event_type"] = "choice_event"
        event["followup_option_names"] = sorted(existing | child_names)

    write_json(EVENTS_PATH, raw_events)
    print("已写入 data/events.json")


if __name__ == "__main__":
    main()