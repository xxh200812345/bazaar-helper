from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs"

sys.path.insert(0, str(BASE_DIR / "src"))

from data_loader import load_all_data  # noqa: E402


UNRECOGNIZED_CATEGORIES = {"", "unknown_events", "missing_events"}
RULE_FIELDS = (
    "shop_pool",
    "card_reward",
    "resource_rewards",
    "followup_options",
    "effect",
    "qualitative_rewards",
)


def has_non_empty_value(value: Any) -> bool:
    if value in (None, False, 0, ""):
        return False
    if isinstance(value, dict):
        return any(has_non_empty_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(has_non_empty_value(item) for item in value)
    return True


def is_recognized_event(event_data: dict[str, Any]) -> bool:
    category = str(event_data.get("event_category") or "")
    if category not in UNRECOGNIZED_CATEGORIES:
        return True

    # Manual overrides may define a valid rule without belonging to a generated
    # category yet. Keep these out of the "known without rules" report.
    return any(has_non_empty_value(event_data.get(field)) for field in RULE_FIELDS)


def benefit_rule_kinds(event_data: dict[str, Any]) -> list[str]:
    kinds: list[str] = []

    if has_non_empty_value(event_data.get("shop_pool")):
        kinds.append("shop_pool")

    card_reward = event_data.get("card_reward")
    if (
        isinstance(card_reward, dict)
        and card_reward.get("enabled")
        and (
            has_non_empty_value(card_reward.get("exact_names"))
            or has_non_empty_value(card_reward.get("reward_tags"))
        )
    ):
        kinds.append("card_reward")

    if has_non_empty_value(event_data.get("resource_rewards")):
        kinds.append("resource_rewards")
    if has_non_empty_value(event_data.get("followup_options")):
        kinds.append("followup_options")
    if has_non_empty_value(event_data.get("effect")):
        kinds.append("effect")
    if has_non_empty_value(event_data.get("qualitative_rewards")):
        kinds.append("qualitative_rewards")

    return kinds


def audit_events(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    data = load_all_data(data_dir)
    events = data.get("events", {})
    translations = data.get("translations", {})
    translated_names = translations.get("by_name", {}) if isinstance(translations, dict) else {}

    recognized_count = 0
    with_rule_count = 0
    missing: list[dict[str, Any]] = []

    for event_name, event_data in sorted(events.items()):
        if not isinstance(event_data, dict) or not is_recognized_event(event_data):
            continue

        recognized_count += 1
        rule_kinds = benefit_rule_kinds(event_data)
        if rule_kinds:
            with_rule_count += 1
            continue

        missing.append(
            {
                "event_name": event_name,
                "display_name": str(translated_names.get(event_name, event_name)),
                "event_category": str(event_data.get("event_category") or ""),
                "event_type": str(event_data.get("event_type") or ""),
                "notes": str(event_data.get("notes") or ""),
                "source_ids": list(event_data.get("source_ids") or []),
                "status": "recognized_without_benefit_rule",
            }
        )

    return {
        "summary": {
            "all_events": len(events),
            "recognized_events": recognized_count,
            "recognized_with_benefit_rule": with_rule_count,
            "recognized_without_benefit_rule": len(missing),
            "by_category": dict(
                sorted(Counter(row["event_category"] for row in missing).items())
            ),
        },
        "events": missing,
    }


def write_outputs(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "events_without_benefit_rules.json"
    csv_path = output_dir / "events_without_benefit_rules.csv"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        fieldnames = [
            "event_name",
            "display_name",
            "event_category",
            "event_type",
            "notes",
            "source_ids",
            "status",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["events"]:
            csv_row = dict(row)
            csv_row["source_ids"] = "|".join(row["source_ids"])
            writer.writerow(csv_row)

    return json_path, csv_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="查找所有已识别、但暂无收益规则的事件。"
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="只打印统计，不写 JSON/CSV。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = audit_events(args.data_dir)
    summary = report["summary"]

    print("事件收益规则审计完成")
    print(f"- 全部事件：{summary['all_events']}")
    print(f"- 已识别事件：{summary['recognized_events']}")
    print(f"- 已有收益规则：{summary['recognized_with_benefit_rule']}")
    print(f"- 已识别但暂无收益规则：{summary['recognized_without_benefit_rule']}")
    if summary["by_category"]:
        category_text = ", ".join(
            f"{category or '(无分类)'}={count}"
            for category, count in summary["by_category"].items()
        )
        print(f"- 待补分类统计：{category_text}")

    if not args.no_write:
        json_path, csv_path = write_outputs(report, args.output_dir)
        print(f"- JSON：{json_path}")
        print(f"- CSV：{csv_path}")


if __name__ == "__main__":
    main()
