"""易经卦象引擎 — MVP 桩实现。"""
import numpy as np
from wcpa.data.repositories.fixture_loader import load_fixture

class IChingEngine:
    """卦象推演引擎。"""
    
    def __init__(self):
        self._hexagrams = load_fixture("iching.sample.json")
    
    def cast_hexagram(self, rng: np.random.Generator) -> dict:
        """掷卦（可复现）。"""
        idx = rng.integers(0, len(self._hexagrams))
        return self._hexagrams[int(idx)]
