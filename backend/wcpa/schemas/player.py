"""Player 模型 — 球员基础数据（MVP 最小化）。"""

from pydantic import Field

from wcpa.schemas import WCPABaseModel


class Player(WCPABaseModel):
    """球员模型。

    MVP 阶段仅保留核心字段，后续可扩展伤病、状态等。
    """

    player_id: str
    team_id: str
    name: str
    position: str  # GK/DF/MF/FW
    overall_rating: int = Field(ge=0, le=100)
