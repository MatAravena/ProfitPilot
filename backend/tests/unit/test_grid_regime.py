from app.domain.strategies.grid.params import RegimeParams
from app.domain.strategies.grid.regime import GridDirection, compute_regime


def _flat_series(n, price=100.0):
    return [price] * n, [price] * n, [price] * n


# Absolute (not price-proportional) half-spreads: a proportional spread on a linear ramp makes
# ATR monotonic, which pins its rolling percentile to ~1.0/~0.0 and gates every bar to FLAT.
# Cycling absolute offsets keep ATR oscillating so its percentile lands inside the vol band.
_SPREADS = [0.1, 1.0, 0.3, 0.7, 0.45]


def _trending(n, start, step):
    closes = [start + step * i for i in range(n)]
    highs = [c + _SPREADS[i % len(_SPREADS)] for i, c in enumerate(closes)]
    lows = [c - _SPREADS[i % len(_SPREADS)] for i, c in enumerate(closes)]
    return highs, lows, closes


def test_uptrend_with_normal_volatility_is_long_biased():
    highs, lows, closes = _trending(120, 100.0, 0.5)
    regime = compute_regime(highs, lows, closes, RegimeParams())
    assert regime.direction[-1] == GridDirection.LONG_BIASED


def test_downtrend_with_normal_volatility_is_short_biased():
    highs, lows, closes = _trending(120, 200.0, -0.5)
    regime = compute_regime(highs, lows, closes, RegimeParams())
    assert regime.direction[-1] == GridDirection.SHORT_BIASED


def test_sideways_with_normal_volatility_is_neutral():
    # Oscillate around 100 so EMAs never diverge trend-wise, but ATR stays non-trivial.
    closes = [100.0 + (5 if i % 2 == 0 else -5) for i in range(120)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    regime = compute_regime(highs, lows, closes, RegimeParams())
    assert regime.direction[-1] in (GridDirection.NEUTRAL, GridDirection.FLAT)


def test_dead_flat_market_gates_to_flat_on_vol():
    highs, lows, closes = _flat_series(250)
    regime = compute_regime(highs, lows, closes, RegimeParams())
    assert regime.direction[-1] == GridDirection.FLAT   # zero volatility never clears atr_vol_low


def test_regime_series_lengths_match_input():
    highs, lows, closes = _trending(50, 100.0, 0.2)
    regime = compute_regime(highs, lows, closes, RegimeParams())
    assert len(regime.direction) == len(regime.supertrend_dir) == len(regime.bb_mid) == 50
