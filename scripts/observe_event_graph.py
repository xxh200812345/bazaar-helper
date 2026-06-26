from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RUNTIME_DIR = BASE_DIR / "runtime"

STATE_PATH = RUNTIME_DIR / "game_state.json"
GRAPH_PATH = RUNTIME_DIR / "observed_event_graph.json"

sys.path.insert(0, str(BASE_DIR / "src"))

from data_loader import load_all_data  # noqa: E402


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_source_id_index(data: dict[str, Any]) -> dict[str, str]:
    return {
        str(source_id).lower(): event_name
        for event_name, event_data in data.get("events", {}).items()
        if isinstance(event_data, dict)
        for source_id in event_data.get("source_ids", []) or []
    }


def normalize_kind(option: dict[str, Any]) -> str:
    option_id = str(option.get("id") or "")
    kind = str(option.get("kind") or "").lower()
    card_type = str(option.get("card_type") or "").lower()

    if option_id.startswith("ste_") or "encounterstep" in card_type:
        return "step"

    if option_id.startswith("com_") or "combat" in card_type:
        return "combat"

    if option_id.startswith("pvp_"):
        return "pvp"

    if option_id.startswith("enc_") or "eventencounter" in card_type:
        return "encounter"

    return kind or "unknown"


def option_to_event_name(
    option: dict[str, Any],
    source_id_index: dict[str, str],
) -> str | None:
    template_id = str(option.get("template_id") or "").lower()
    if template_id and template_id in source_id_index:
        return source_id_index[template_id]

    name = option.get("name")
    if name:
        return str(name)

    return None


def load_graph() -> dict[str, Any]:
    if not GRAPH_PATH.exists():
        return {}

    try:
        data = load_json(GRAPH_PATH)
    except json.JSONDecodeError:
        return {}

    return data if isinstance(data, dict) else {}


def observe_current_state() -> None:
    data = load_all_data(DATA_DIR)
    source_id_index = build_source_id_index(data)

    payload = load_json(STATE_PATH)
    detailed_options = payload.get("event_options_detailed", [])

    if not isinstance(detailed_options, list):
        print("当前 game_state.json 没有 event_options_detailed")
        return

    normalized_options: list[dict[str, Any]] = []

    for option in detailed_options:
        if not isinstance(option, dict):
            continue

        item = dict(option)
        item["kind"] = normalize_kind(item)
        item["event_name"] = option_to_event_name(item, source_id_index)
        normalized_options.append(item)

    parents = [
        option
        for option in normalized_options
        if option.get("kind") == "encounter"
    ]

    children = [
        option
        for option in normalized_options
        if option.get("kind") in {"step", "combat", "pvp"}
    ]

    if len(parents) != 1 or not children:
        print("当前界面不像父事件展开后的子选项界面，未记录。")
        print(f"- parents: {len(parents)}")
        print(f"- children: {len(children)}")
        return

    parent = parents[0]
    parent_name = parent.get("event_name")

    if not parent_name:
        print("父事件无法映射到 events.json 名称，未记录。")
        return

    graph = load_graph()

    item = graph.get(parent_name, {})
    if not isinstance(item, dict):
        item = {}

    item.setdefault("parent_event", parent_name)
    item.setdefault("parent_source_ids", [])
    item.setdefault("children", [])
    item["observed_count"] = int(item.get("observed_count", 0)) + 1

    parent_template_id = parent.get("template_id")
    if parent_template_id and parent_template_id not in item["parent_source_ids"]:
        item["parent_source_ids"].append(parent_template_id)

    existing_children = {
        child.get("source_id"): child
        for child in item["children"]
        if isinstance(child, dict)
    }

    for child in children:
        source_id = child.get("template_id")
        if not source_id:
            continue

        child_item = existing_children.get(source_id)

        if not child_item:
            child_item = {
                "name": child.get("event_name") or child.get("name") or "",
                "source_id": source_id,
                "kind": child.get("kind"),
                "card_type": child.get("card_type"),
                "count": 0,
            }
            item["children"].append(child_item)

        child_item["count"] = int(child_item.get("count", 0)) + 1

    graph[parent_name] = item

    write_json(GRAPH_PATH, graph)

    print("已记录父事件子选项关系")
    print(f"- parent: {parent_name}")
    print(f"- children: {len(children)}")
    print(f"- output: {GRAPH_PATH}")


if __name__ == "__main__":
    observe_current_state()