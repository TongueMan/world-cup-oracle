"""塔罗引擎 — MVP 桩实现。"""
import numpy as np
from wcpa.data.repositories.fixture_loader import load_fixture

class TarotEngine:
    """塔罗牌抽取引擎。"""
    
    def __init__(self):
        self._cards = load_fixture("tarot-cards.sample.json")
    
    def draw_cards(self, n: int, rng: np.random.Generator) -> list[dict]:
        """抽 n 张牌（可复现）。"""
        indices = rng.integers(0, len(self._cards), n)
        return [self._cards[i] for i in indices]
