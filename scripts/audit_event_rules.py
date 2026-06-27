from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"

sys.path.insert(0, str(BASE_DIR / "src"))

from data_loader import load_all_data  # noqa: E402

EVENTS_PATH = DATA_DIR / "events.json"
TRANSLATIONS_PATH = DATA_DIR / "translations_zh_cn.json"

OUTPUT_JSON_PATH = OUTPUT_DIR / "event_rule_audit.json"
OUTPUT_CSV_PATH = OUTPUT_DIR / "event_rule_audit.csv"


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"找不到文件：{path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_translations() -> dict[str, Any]:
    if not TRANSLATIONS_PATH.exists():
        return {}

    data = load_json(TRANSLATIONS_PATH)
    return data if isinstance(data, dict) else {}


def zh_name(translations: dict[str, Any], name: str) -> str:
    by_name = translations.get("by_name", {})
    if isinstance(by_name, dict):
        return str(by_name.get(name, name))
    return name


def has_non_empty_value(value: Any) -> bool:
    """
    判断一个收益字段是否真的有值。

    这里故意不把 0 当作有效收益。
    例如：
    {"gold": 0, "health": 0} 不算有收益规则。
    """

    if value is None:
        return False

    if value is False:
        return False

    if value == 0:
        return False

    if value == "":
        return False

    if isinstance(value, dict):
        return any(has_non_empty_value(item) for item in value.values())

    if isinstance(value, list):
        return len(value) > 0

    return True


def event_has_value_rule(event_data: dict[str, Any] | None) -> bool:
    """
    判断一个 events.json 里的事件是否有可计算收益规则。

    注意：
    这里不把 event_category 当作收益规则。
    因为 Jungle Ruins 这种事件可能有分类，但仍然没有 shop_pool / card_reward / resource_rewards / followup_options。
    """

    if not event_data:
        return False

    if has_non_empty_value(event_data.get("shop_pool")):
        return True

    card_reward = event_data.get("card_reward")
    if isinstance(card_reward, dict) and card_reward.get("enabled"):
        return True

    if has_non_empty_value(event_data.get("followup_options")):
        return True

    if has_non_empty_value(event_data.get("resource_rewards")):
        return True

    return False


def missing_rule_reasons(event_data: dict[str, Any]) -> list[str]:
    reasons: list[str] = []

    if not has_non_empty_value(event_data.get("shop_pool")):
        reasons.append("缺少 shop_pool")

    card_reward = event_data.get("card_reward")
    if not (isinstance(card_reward, dict) and card_reward.get("enabled")):
        reasons.append("缺少启用的 card_reward")

    if not has_non_empty_value(event_data.get("resource_rewards")):
        reasons.append("缺少 resource_rewards")

    if not has_non_empty_value(event_data.get("followup_options")):
        reasons.append("缺少 followup_options")

    return reasons


def audit_events() -> list[dict[str, Any]]:
    data = load_all_data(DATA_DIR)
    events = data.get("events", {})
    translations = data.get("translations", load_translations())

    if not isinstance(events, dict):
        raise TypeError("load_all_data(DATA_DIR) 得到的 data['events'] 应该是 dict/object")

    rows: list[dict[str, Any]] = []

    for event_name, event_data in sorted(events.items()):
        if not isinstance(event_data, dict):
            continue

        has_rule = event_has_value_rule(event_data)

        row = {
            "event_name": event_name,
            "display_name": zh_name(translations, event_name),
            "event_category": event_data.get("event_category", ""),
            "has_value_rule": has_rule,
            "status": "with_value_rule" if has_rule else "known_without_value_rule",
            "source_ids_count": len(event_data.get("source_ids", []) or []),
            "missing_reasons": missing_rule_reasons(event_data) if not has_rule else [],
        }

        rows.append(row)

    return rows

def write_outputs(rows: list[dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    OUTPUT_JSON_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with OUTPUT_CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "event_name",
                "display_name",
                "event_category",
                "has_value_rule",
                "status",
                "source_ids_count",
                "missing_reasons",
            ],
        )
        writer.writeheader()

        for row in rows:
            csv_row = dict(row)
            csv_row["missing_reasons"] = "；".join(row.get("missing_reasons", []))
            writer.writerow(csv_row)


def print_summary(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    missing = [row for row in rows if not row["has_value_rule"]]
    with_rule = [row for row in rows if row["has_value_rule"]]

    print("事件收益规则审计完成")
    print(f"- events.json 事件总数：{total}")
    print(f"- 有收益规则：{len(with_rule)}")
    print(f"- 已识别但无收益规则：{len(missing)}")
    print()
    print(f"输出文件：{OUTPUT_JSON_PATH}")
    print(f"输出表格：{OUTPUT_CSV_PATH}")
    print()

    if missing:
        print("前 30 个无收益规则事件：")
        for row in missing[:30]:
            print(
                f"- {row['display_name']} / {row['event_name']}"
                f"｜分类：{row['event_category'] or '未标注'}"
                f"｜原因：{'；'.join(row['missing_reasons'])}"
            )


def main() -> None:
    rows = audit_events()
    write_outputs(rows)
    print_summary(rows)


if __name__ == "__main__":
    main()