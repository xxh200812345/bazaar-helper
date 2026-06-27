from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from build_strategy import format_build_timing_summary, get_game_stage_for_day
from recommender import format_resource_rewards


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_API_KEY_FILE = Path(__file__).resolve().parent.parent / "runtime" / "deepseek_api_key.txt"
STAGE_LABELS_ZH = {
    "early": "前期",
    "mid": "中期",
    "late": "后期",
}
RECOMMENDATION_LABELS_ZH = {
    "High Value": "优先选择",
    "Medium Value": "可以考虑",
    "Low Value": "优先级低",
}
ROLE_LABELS_ZH = {
    "core": "核心",
    "transition": "过渡",
    "optional": "可选",
    "unrelated": "无关",
}


def _round_ratio(value: float) -> float:
    return round(float(value), 4)


def _zh_name(data: dict[str, Any], name: Any) -> str:
    if not name:
        return ""
    return data.get("translations", {}).get("by_name", {}).get(str(name), str(name))


def _zh_text(data: dict[str, Any], text: Any) -> str:
    if not text:
        return ""
    result = str(text)
    by_name = data.get("translations", {}).get("by_name", {})
    for source_name in sorted(by_name, key=len, reverse=True):
        translated = by_name.get(source_name)
        if translated:
            result = result.replace(source_name, translated)
    return result


def _priority_cards(
    data: dict[str, Any],
    cards: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    priority_roles = {"core", "transition", "optional"}
    priority_cards = [card for card in cards if card.get("role") in priority_roles]

    def sort_key(card: dict[str, Any]) -> tuple[int, str]:
        role_rank = {"core": 0, "transition": 1, "optional": 2}
        return role_rank.get(card.get("role", ""), 9), card.get("name", "")

    return [
        {
            "名称": _zh_name(data, card.get("name")),
            "tier": card.get("tier"),
            "定位": ROLE_LABELS_ZH.get(card.get("role"), card.get("role")),
            "可升级": card.get("can_upgrade", False),
        }
        for card in sorted(priority_cards, key=sort_key)[:limit]
    ]


def compact_recommendations(
    *,
    data: dict[str, Any],
    hero: str,
    build_name: str,
    current_day: int,
    owned_cards: dict[str, str],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    build_data = data["builds"][build_name]

    payload = {
        "英雄": hero,
        "阵容": build_name,
        "天数": current_day,
        "阶段": STAGE_LABELS_ZH.get(get_game_stage_for_day(current_day), get_game_stage_for_day(current_day)),
        "阵容时机": format_build_timing_summary(build_data, current_day),
        "阵容摘要": build_data.get("build_summary", ""),
        "实战Tips": build_data.get("pilot_tips", []),
        "已拥有卡牌": owned_cards,
        "选项": [],
    }

    for result in results:
        pool_stats = result.get("pool_stats", {})
        payload["选项"].append(
            {
                "事件名": _zh_name(data, result.get("event_name")),
                "推荐等级": RECOMMENDATION_LABELS_ZH.get(
                    result.get("recommendation"),
                    result.get("recommendation"),
                ),
                "说明": "",
                "原因": [
                    _zh_text(data, reason)
                    for reason in result.get("reasons", [])[:3]
                ],
                "关键卡": _priority_cards(data, result.get("possible_cards", [])),
                "已拥有命中": [
                    {
                        "名称": _zh_name(data, card.get("name")),
                        "评级": card.get("tier"),
                        "定位": ROLE_LABELS_ZH.get(card.get("role"), card.get("role")),
                        "可升级": card.get("can_upgrade", False),
                        "附魔": card.get("enchantments", []),
                    }
                    for card in result.get("owned_target_hits", [])[:5]
                ],
                "资源收益": format_resource_rewards(result.get("resource_rewards", {})),
                "后续选项": [
                    {
                        "名称": _zh_name(data, option.get("name")),
                        "推荐等级": RECOMMENDATION_LABELS_ZH.get(
                            option.get("recommendation"),
                            option.get("recommendation"),
                        ),
                        "说明": "",
                        "资源收益": format_resource_rewards(
                            option.get("resource_rewards", {})
                        ),
                        "预期卖价金币": _round_ratio(
                            option.get("expected_sell_gold", 0.0)
                        ),
                        "关键卡": [
                            {
                                **card,
                                "name": _zh_name(data, card.get("name")),
                                "role": ROLE_LABELS_ZH.get(card.get("role"), card.get("role")),
                            }
                            for card in option.get("priority_cards", [])[:3]
                        ],
                    }
                    for option in result.get("followup_options", [])[:6]
                ],
                "统计": {
                    "候选卡数量": int(pool_stats.get("total_pool_count", 0)),
                    "构筑相关卡数量": int(pool_stats.get("valuable_count", 0)),
                    "预期命中数量": _round_ratio(
                        pool_stats.get("expected_valuable_in_shop", 0.0)
                    ),
                    "命中相关卡概率": _round_ratio(
                        pool_stats.get("prob_valuable_in_shop", 0.0)
                    ),
                    "命中核心卡概率": _round_ratio(pool_stats.get("prob_core_in_shop", 0.0)),
                    "预期卖价金币": _round_ratio(pool_stats.get("expected_sell_gold", 0.0)),
                },
            }
        )

    return payload


def build_ai_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    summary_json = json.dumps(payload, ensure_ascii=False, indent=2)

    option_names = [
        str(option.get("事件名"))
        for option in payload.get("选项", [])
        if option.get("事件名")
    ]
    option_name_text = "、".join(option_names) if option_names else "无"

    return [
        {
            "role": "system",
            "content": (
                "你是《The Bazaar》的事件选择建议助手。\n"
                "你只能基于用户提供的数据判断，不得编造卡牌、事件、概率、规则或额外操作。\n"
                "\n"
                "最高优先级约束：\n"
                "1. 当前回合必须从候选事件中选择一个，不能跳过事件。\n"
                "2. 只要候选事件不为空，推荐行必须填写候选事件名之一，禁止写“无”“跳过”“不选”“放弃”。\n"
                "5. 如果所有候选事件都很差，也必须选择相对最不差的一个，并说明“都不理想，但该选项损失最小”。\n"
                "6. 禁止建议候选之外的行为，例如跳过事件、找商店、完成任务、升级武器、等下一回合。\n"
                "7. 阵容摘要和实战Tips只能作为背景，不能生成本轮候选之外的操作建议。\n"
                "\n"
                "选择优先级：\n"
                "1. 优先选择推荐等级更高的事件。\n"
                "2. 同等级时，优先选择构筑相关卡、核心卡概率、资源收益、已有物品命中或后续选项更好的事件。\n"
                "3. 如果全部没有明显收益，选择资源收益最高或损失最小的事件。\n"
                "\n"
                "输出规则：\n"
                "1. 必须使用中文。\n"
                "2. 禁止使用 Markdown。\n"
                "3. 禁止使用 **、#、表格、代码块。\n"
                "4. 禁止使用多层列表。\n"
                "5. 不要写成长篇攻略，但要解释清楚推荐逻辑。\n"
                "6. 总字数控制在 280 到 420 字之间。\n"
                "\n"
                "先包含下面 3 行输出，再增加其他内容：\n"
                "推荐：候选事件名之一\n"
                "核心判断：说明推荐事件对当前阵容、阶段、已有卡牌的主要价值\n"
                "对比理由：说明它为什么比其他候选更好\n"
            ),
        },
        {
            "role": "user",
            "content": (
                f"本轮候选事件名只能从这里选择：{option_name_text}\n"
                "下面是本次事件候选数据，只能基于这些数据判断：\n"
                f"{summary_json}"
            ),
        },
    ]


def read_api_key_file(path: Path = DEFAULT_API_KEY_FILE) -> str | None:
    if not path.exists():
        return None

    api_key = path.read_text(encoding="utf-8").strip()
    return api_key or None


def resolve_api_key(api_key: str | None = None) -> str | None:
    return api_key or os.environ.get("DEEPSEEK_API_KEY") or read_api_key_file()


def clean_ai_output(text: str) -> str:
    """清理 AI 输出中的 Markdown 符号，避免前端直接显示 **、缩进列表等。"""
    if not text:
        return ""

    text = text.replace("\r\n", "\n")

    # 去掉常见 Markdown 强调符号
    text = text.replace("**", "")
    text = text.replace("__", "")

    # 去掉标题符号
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)

    # 去掉行首项目符号
    text = re.sub(r"(?m)^\s*[\*\-•]\s*", "", text)

    # 压平过深缩进
    text = re.sub(r"(?m)^\s{2,}", "", text)

    # 压缩空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def call_deepseek(
    messages: list[dict[str, str]],
    *,
    api_key: str | None = None,
    model: str = DEFAULT_DEEPSEEK_MODEL,
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
    timeout: int = 30,
) -> str:
    api_key = resolve_api_key(api_key)
    if not api_key:
        raise RuntimeError(
            "没有找到 DeepSeek API Key。请在启动 UI 前设置 DEEPSEEK_API_KEY，"
            "或把 key 放到 runtime/deepseek_api_key.txt。"
        )

    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API 返回 HTTP {exc.code}：{error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 DeepSeek API：{exc.reason}") from exc

    decoded = json.loads(response_body)
    return decoded["choices"][0]["message"]["content"]


def analyze_with_ai(
    payload: dict[str, Any],
    *,
    model: str = DEFAULT_DEEPSEEK_MODEL,
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
    timeout: int = 30,
) -> str:
    raw_text = call_deepseek(
        build_ai_messages(payload),
        model=model,
        base_url=base_url,
        timeout=timeout,
    )
    return clean_ai_output(raw_text)
