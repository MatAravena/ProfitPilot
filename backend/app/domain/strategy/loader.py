from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Built-in metadata — keeps UI-facing info out of the strategy classes themselves
_BUILTIN_META: dict[str, dict[str, Any]] = {
    "SmaCrossover": {
        "display_name": "SMA Crossover",
        "description": "Golden/death cross using two simple moving averages",
        "parameters": [
            {"key": "fast_period", "type": "int", "default": 20, "label": "Fast Period"},
            {"key": "slow_period", "type": "int", "default": 50, "label": "Slow Period"},
        ],
    },
    "RsiMeanReversion": {
        "display_name": "RSI Mean Reversion",
        "description": "Buy oversold, sell overbought using RSI",
        "parameters": [
            {"key": "rsi_period", "type": "int", "default": 14, "label": "RSI Period"},
            {"key": "oversold",    "type": "int", "default": 30, "label": "Oversold Level"},
            {"key": "overbought",  "type": "int", "default": 70, "label": "Overbought Level"},
        ],
    },
    "MacdCrossover": {
        "display_name": "MACD Crossover",
        "description": "Buy/close when MACD line crosses the signal line",
        "parameters": [
            {"key": "fast_period",   "type": "int", "default": 12, "label": "Fast EMA"},
            {"key": "slow_period",   "type": "int", "default": 26, "label": "Slow EMA"},
            {"key": "signal_period", "type": "int", "default": 9,  "label": "Signal EMA"},
        ],
    },
    "BollingerBandsMeanReversion": {
        "display_name": "Bollinger Bands",
        "description": "Mean reversion — buy below lower band, close above middle",
        "parameters": [
            {"key": "period",   "type": "int",   "default": 20,  "label": "Period"},
            {"key": "std_mult", "type": "float", "default": 2.0, "label": "Std Multiplier"},
        ],
    },
}

# user_strategies/ lives at backend/user_strategies/ (four levels up from this file)
_USER_STRATEGIES_DIR = Path(__file__).parents[3] / "user_strategies"


def load_user_strategies(strategies_dir: Path | None = None) -> None:
    """Import every *.py file in strategies_dir that isn't prefixed with _.

    Files that use @StrategyRegistry.register are auto-registered on import.
    Already-loaded modules are skipped so this is safe to call repeatedly.
    """
    directory = strategies_dir or _USER_STRATEGIES_DIR
    if not directory.exists():
        return

    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"user_strategies.{path.stem}"
        if module_name in sys.modules:
            continue
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            logger.info("strategy.user_loaded", file=path.name)
        except Exception as exc:
            logger.error("strategy.user_load_failed", file=path.name, error=str(exc))


def get_all_strategy_classes() -> list[dict[str, Any]]:
    """Return rich metadata for every registered strategy (built-ins + user-defined).

    Each entry:
        class_name   str
        display_name str
        description  str
        parameters   list[{key, type, default, label}]
    """
    # Ensure built-ins and user files are loaded
    importlib.import_module("app.domain.strategy.examples.sma_crossover")
    load_user_strategies()

    from app.domain.strategy.base import StrategyRegistry

    result: list[dict[str, Any]] = []
    for class_name in StrategyRegistry.list_all():
        if class_name in _BUILTIN_META:
            meta = dict(_BUILTIN_META[class_name])
        else:
            klass = StrategyRegistry.get(class_name)
            module = sys.modules.get(klass.__module__)
            module_meta: dict[str, Any] | None = getattr(module, "STRATEGY_META", None)
            if module_meta:
                meta = dict(module_meta)
            else:
                first_line = (klass.__doc__ or "").strip().split("\n")[0]
                meta = {
                    "display_name": class_name,
                    "description": first_line,
                    "parameters": [],
                }
        meta["class_name"] = class_name
        result.append(meta)
    return result
