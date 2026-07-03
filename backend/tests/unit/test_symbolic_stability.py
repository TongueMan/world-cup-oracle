"""象征规则稳定性测试。"""
import pytest
import numpy as np
from wcpa.symbolic.symbolic_engine import FixtureSymbolicEngine
from wcpa.shared.random_utils import create_rng


def test_symbolic_reproducibility():
    """同一 match_id 多次调用产出相同信号。"""
    engine = FixtureSymbolicEngine()
    rng1 = create_rng(42)
    rng2 = create_rng(42)

    sig1 = engine.generate_signal("G-A-001", "BRA", "ARG", rng1)
    sig2 = engine.generate_signal("G-A-001", "BRA", "ARG", rng2)

    # 塔罗牌应一致
    assert sig1.tarot.home_cards == sig2.tarot.home_cards
    assert sig1.tarot.away_cards == sig2.tarot.away_cards

    # 卦象应一致
    assert sig1.iching.gua == sig2.iching.gua

    # 四元素应一致
    assert sig1.astrology.fire_energy == sig2.astrology.fire_energy


def test_symbolic_different_matches():
    """不同 match_id 产出不同信号（大概率）。"""
    engine = FixtureSymbolicEngine()
    rng = create_rng(42)

    sig1 = engine.generate_signal("G-A-001", "BRA", "ARG", rng)
    sig2 = engine.generate_signal("G-A-002", "BRA", "MEX", rng)

    # 不同 match_id 应大概率不同
    assert sig1.match_id != sig2.match_id
