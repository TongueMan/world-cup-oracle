"""SymbolicSignal 模型 — 象征推理信号（塔罗/易经/占星）。"""

from typing import Optional

from pydantic import Field

from wcpa.schemas import WCPABaseModel


class TarotSignal(WCPABaseModel):
    """塔罗牌信号。"""

    home_cards: list[str] = []
    away_cards: list[str] = []
    keywords: list[str] = []


class IChingSignal(WCPABaseModel):
    """易经卦象信号。"""

    gua: str = ""
    keywords: list[str] = []
    upset_risk: float = Field(default=0.5, ge=0, le=1)


class AstrologySignal(WCPABaseModel):
    """占星能量信号。"""

    fire_energy: float = Field(default=0.5, ge=0, le=1)
    earth_energy: float = Field(default=0.5, ge=0, le=1)
    air_energy: float = Field(default=0.5, ge=0, le=1)
    water_energy: float = Field(default=0.5, ge=0, le=1)
    keywords: list[str] = []


class SymbolicSignal(WCPABaseModel):
    """单场比赛的象征推理综合信号。

    ``fortune_score`` 为综合运势分；
    ``symbolic_weight_applied`` 为实际施加到预测的象征权重。
    """

    match_id: str
    tarot: Optional[TarotSignal] = None
    iching: Optional[IChingSignal] = None
    astrology: Optional[AstrologySignal] = None
    fortune_score: float = Field(default=0.5, ge=0, le=1)
    symbolic_weight_applied: float = Field(default=0.1, ge=0, le=1)
