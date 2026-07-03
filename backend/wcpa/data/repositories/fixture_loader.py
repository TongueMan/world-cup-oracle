"""Fixture 加载器 — 从 data/fixtures/ 读取样本数据。

提供 ``load_fixture`` 通用加载和 ``load_narratives`` 专用加载，
返回 schema 实例或原始字典/列表。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from wcpa.schemas.match import Match
from wcpa.schemas.narrative import NarrativeProfile
from wcpa.schemas.team import Team
from wcpa.shared.paths import FIXTURES_DIR


@lru_cache(maxsize=32)
def load_fixture(filename: str) -> Any:
    """从 ``data/fixtures/{filename}`` 加载 JSON fixture。

    结果按 ``filename`` 缓存（同一进程内多次调用返回同一对象）。

    Args:
        filename: fixture 文件名，如 ``"tarot-cards.sample.json"``。

    Returns:
        解析后的 JSON 数据（dict 或 list）。

    Raises:
        FileNotFoundError: fixture 文件不存在。
    """
    path: Path = FIXTURES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Fixture file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_teams() -> list[Team]:
    """加载全部球队 fixture。

    从 ``teams.sample.json`` 读取并转为 :class:`Team` 列表。
    """
    raw: list[dict] = load_fixture("teams.sample.json")
    return [Team(**entry) for entry in raw]


def load_matches() -> list[Match]:
    """加载全部比赛 fixture。

    从 ``matches.sample.json`` 读取并转为 :class:`Match` 列表。
    """
    raw: list[dict] = load_fixture("matches.sample.json")
    return [Match(**entry) for entry in raw]


def load_narratives() -> list[NarrativeProfile]:
    """加载全部球队叙事画像 fixture。

    从 ``narratives.sample.json`` 读取并转为
    :class:`NarrativeProfile` 列表。

    Returns:
        NarrativeProfile 列表。
    """
    raw: list[dict] = load_fixture("narratives.sample.json")
    return [NarrativeProfile(**entry) for entry in raw]
