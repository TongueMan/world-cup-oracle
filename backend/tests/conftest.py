"""共享 pytest fixtures。"""
import pytest
import numpy as np
from wcpa.shared.random_utils import create_rng
from wcpa.data.repositories.fixture_loader import load_teams, load_matches
from wcpa.features.feature_builder import build_features
from wcpa.prediction.match_predictor import BaselineMatchPredictor

@pytest.fixture
def rng():
    """提供 seedable RNG。"""
    return create_rng(42)

@pytest.fixture
def teams():
    return load_teams()

@pytest.fixture
def matches():
    return load_matches()

@pytest.fixture
def features(teams):
    return build_features(teams)

@pytest.fixture
def predictor():
    return BaselineMatchPredictor()

@pytest.fixture
def team_map(teams):
    return {t.team_id: t for t in teams}
