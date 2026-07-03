"""象征推理引擎 — MVP 桩实现。"""
from __future__ import annotations
from abc import ABC, abstractmethod
import hashlib
import numpy as np
from wcpa.schemas.symbolic import SymbolicSignal, TarotSignal, IChingSignal, AstrologySignal
from wcpa.data.repositories.fixture_loader import load_fixture

class SymbolicEngine(ABC):
    """象征推理引擎接口。"""
    @abstractmethod
    def generate_signal(self, match_id: str, home_team_id: str, away_team_id: str,
                        rng: np.random.Generator) -> SymbolicSignal:
        ...

class FixtureSymbolicEngine(SymbolicEngine):
    """桩实现：从 fixture 读取固定象征信号，保证可复现。"""
    
    def __init__(self):
        self._tarot_cards = load_fixture("tarot-cards.sample.json")
        self._iching = load_fixture("iching.sample.json")
        self._astrology = load_fixture("astrology-rules.sample.json")
    
    def generate_signal(self, match_id: str, home_team_id: str, away_team_id: str,
                        rng: np.random.Generator) -> SymbolicSignal:
        """生成象征信号 — 桩实现返回固定信号。"""
        # 用 match_id 的哈希值确定性地选择牌/卦
        seed_val = int.from_bytes(hashlib.sha256(match_id.encode("utf-8")).digest()[:8], "big") & 0x7FFFFFFF
        local_rng = np.random.default_rng(seed_val)
        
        # 抽塔罗牌
        home_cards = [self._tarot_cards[i % len(self._tarot_cards)]["name"]
                      for i in local_rng.integers(0, len(self._tarot_cards), 3)]
        away_cards = [self._tarot_cards[i % len(self._tarot_cards)]["name"]
                      for i in local_rng.integers(0, len(self._tarot_cards), 3)]
        
        home_keywords = [kw for c in home_cards
                         for kw in next((tc["keywords"] for tc in self._tarot_cards if tc["name"] == c), [])]
        away_keywords = [kw for c in away_cards
                         for kw in next((tc["keywords"] for tc in self._tarot_cards if tc["name"] == c), [])]
        
        # 查卦象
        gua = self._iching[seed_val % len(self._iching)]["name"]
        iching_entry = next((e for e in self._iching if e["name"] == gua), {})
        
        # 四元素能量
        energies = {e: local_rng.uniform(0.3, 0.8) for e in ["fire", "earth", "air", "water"]}
        
        return SymbolicSignal(
            match_id=match_id,
            tarot=TarotSignal(
                home_cards=home_cards, away_cards=away_cards,
                keywords=list(set(home_keywords + away_keywords))[:5],
            ),
            iching=IChingSignal(
                gua=gua,
                keywords=iching_entry.get("keywords", []),
                upset_risk=iching_entry.get("upset_risk", 0.5),
            ),
            astrology=AstrologySignal(
                fire_energy=energies["fire"], earth_energy=energies["earth"],
                air_energy=energies["air"], water_energy=energies["water"],
            ),
            fortune_score=0.5,
            symbolic_weight_applied=0.1,
        )
