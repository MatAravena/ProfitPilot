"""Shared numeric constants that were previously duplicated as magic numbers
across the backtest engine, backtest service, and strategy sandbox."""

# Minimum bars required to run a backtest (indicators need warm-up + signal room).
MIN_BACKTEST_BARS = 60

# Bars skipped at the start of a run before signals are generated (indicator warm-up).
DEFAULT_WARMUP_BARS = 50
