"""星象引擎 — MVP 桩实现。"""
import numpy as np
from wcpa.data.repositories.fixture_loader import load_fixture

class AstrologyEngine:
    """星象能量引擎。"""
    
    def __init__(self):
        self._rules = load_fixture("astrology-rules.sample.json")
    
    def get_energy(self, rng: np.random.Generator) -> dict:
        """获取四元素能量值（可复现）。"""
        result = {}
        for element in ["fire", "earth", "air", "water"]:
            rule = self._rules[element]
            lo, hi = rule["intensity_range"]
            result[element] = float(rng.uniform(lo, hi))
        return result
