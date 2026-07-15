"""胜平负赔率去水与多机构聚合。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wcpa.schemas.prediction import BookmakerOdds


@dataclass(frozen=True)
class MarketEstimate:
    probabilities: tuple[float, float, float]
    confidence: float
    bookmaker_count: int
    mean_overround: float
    dispersion: float


def devig_three_way(home: float, draw: float, away: float) -> tuple[tuple[float, float, float], float]:
    """移除三项十进制赔率中的按比例水位。"""

    if min(home, draw, away) <= 1:
        raise ValueError("decimal odds must be greater than 1")
    implied = np.array([1 / home, 1 / draw, 1 / away], dtype=float)
    overround = float(implied.sum() - 1)
    normalized = implied / implied.sum()
    return tuple(float(value) for value in normalized), overround


def aggregate_bookmaker_odds(odds: list[BookmakerOdds]) -> MarketEstimate | None:
    """按来源置信度和新鲜度聚合多家机构概率。"""

    if not odds:
        return None

    rows: list[tuple[float, float, float]] = []
    weights: list[float] = []
    overrounds: list[float] = []
    for quote in odds:
        probabilities, overround = devig_three_way(quote.home, quote.draw, quote.away)
        rows.append(probabilities)
        weights.append(max(0.01, quote.confidence * quote.freshness))
        overrounds.append(overround)

    values = np.array(rows, dtype=float)
    weight_array = np.array(weights, dtype=float)
    aggregate = np.average(values, axis=0, weights=weight_array)
    aggregate = aggregate / aggregate.sum()
    dispersion = float(np.average(np.std(values, axis=0), weights=np.ones(3)))
    coverage = min(1.0, 0.55 + 0.09 * len(rows))
    confidence = coverage * max(0.35, 1 - dispersion * 4)
    return MarketEstimate(
        probabilities=tuple(float(value) for value in aggregate),
        confidence=max(0.1, min(0.95, confidence)),
        bookmaker_count=len(rows),
        mean_overround=float(np.average(overrounds, weights=weight_array)),
        dispersion=dispersion,
    )
