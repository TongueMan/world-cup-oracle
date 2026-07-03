"""叙事感知引擎 — MVP 桩实现。"""
from __future__ import annotations
from abc import ABC, abstractmethod
import numpy as np
from wcpa.schemas.narrative import NarrativeProfile
from wcpa.data.repositories.fixture_loader import load_narratives

class NarrativeEngine(ABC):
    """叙事感知引擎接口。"""
    @abstractmethod
    def generate_profile(self, team_id: str, rng: np.random.Generator) -> NarrativeProfile:
        ...

class FixtureNarrativeEngine(NarrativeEngine):
    """桩实现：从 fixture 读取预定义 narrative_profile。"""
    
    def __init__(self):
        self._profiles = {p.team_id: p for p in load_narratives()}
    
    def generate_profile(self, team_id: str, rng: np.random.Generator) -> NarrativeProfile:
        return self._profiles.get(team_id, NarrativeProfile(
            team_id=team_id,
            media_heat_score=0.5, morale_score=0.5, dark_horse_score=0.5,
            pressure_score=0.5, destiny_score=0.5, fan_momentum_score=0.5,
            tags=["no_narrative_data"],
        ))

def compute_narrative_score(profile: NarrativeProfile, weights: dict | None = None) -> float:
    """计算叙事综合评分。"""
    if weights is None:
        from wcpa.shared.config_loader import load_config
        weights = load_config("narrative-rules")["narrative_score_weights"]
    score = (
        weights["media_heat_score"] * profile.media_heat_score +
        weights["morale_score"] * profile.morale_score +
        weights["dark_horse_score"] * profile.dark_horse_score +
        weights["destiny_score"] * profile.destiny_score +
        weights["fan_momentum_score"] * profile.fan_momentum_score -
        abs(weights["pressure_penalty"]) * profile.pressure_score
    )
    return max(0.0, min(1.0, score))
