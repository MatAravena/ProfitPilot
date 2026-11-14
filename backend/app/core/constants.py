"""Shared numeric constants that were previously duplicated as magic numbers
across the backtest engine, backtest service, and strategy sandbox."""

# Minimum bars required to run a backtest (indicators need warm-up + signal room).
MIN_BACKTEST_BARS = 60

# Bars skipped at the start of a run before signals are generated (indicator warm-up).
DEFAULT_WARMUP_BARS = 50

# How much price history a strategy sees per decision — the SAME number in live and in
# backtest (parity: a backtest must show the strategy exactly what live would). It also keeps
# a backtest linear in bar count instead of quadratic. A strategy whose parameters need more
# bars than this (e.g. a 600-bar SMA) can never signal, live or backtest — raise this first.
STRATEGY_LOOKBACK_BARS = 500
