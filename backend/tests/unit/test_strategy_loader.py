"""Unit tests for the dynamic strategy loader."""
from __future__ import annotations

import sys
import textwrap
import tempfile
from pathlib import Path

import pytest

from app.domain.strategy.loader import get_all_strategy_classes, load_user_strategies
from app.domain.strategy.base import StrategyRegistry


class TestGetAllStrategyClasses:
    def test_returns_list_of_dicts(self):
        classes = get_all_strategy_classes()
        assert isinstance(classes, list)
        assert len(classes) >= 2

    def test_builtin_strategies_present(self):
        names = {c["class_name"] for c in get_all_strategy_classes()}
        assert "SmaCrossover" in names
        assert "RsiMeanReversion" in names

    def test_each_entry_has_required_keys(self):
        for c in get_all_strategy_classes():
            assert "class_name" in c
            assert "display_name" in c
            assert "description" in c
            assert "parameters" in c
            assert isinstance(c["parameters"], list)

    def test_builtin_parameters_have_defaults(self):
        classes = {c["class_name"]: c for c in get_all_strategy_classes()}
        for p in classes["SmaCrossover"]["parameters"]:
            assert "key" in p
            assert "default" in p
            assert "label" in p


class TestLoadUserStrategies:
    def test_skips_underscore_files(self, tmp_path: Path):
        # A file starting with _ must NOT be loaded
        skip_file = tmp_path / "_private.py"
        skip_file.write_text("raise RuntimeError('should not load')")
        load_user_strategies(tmp_path)  # must not raise

    def test_loads_valid_strategy_file(self, tmp_path: Path):
        code = textwrap.dedent("""
            from app.domain.strategy.base import StrategyRegistry, StrategyBase
            from app.core.enums import MarketType, Timeframe
            from app.core.types import RiskConfig, MarketData, Signal, Tick, Fill
            from uuid import uuid4
            from typing import List, Optional

            @StrategyRegistry.register
            class _TestLoaderStrategy(StrategyBase):
                def __init__(self, parameters, **kw):
                    super().__init__(
                        strategy_id=uuid4(), name="_TestLoaderStrategy", version="1",
                        market_type=MarketType.CRYPTO, timeframe=Timeframe.D1,
                        parameters=parameters, risk_config=RiskConfig(),
                    )
                async def generate_signals(self, data: MarketData) -> List[Signal]: return []
                async def on_tick(self, tick: Tick) -> Optional[Signal]: return None
                async def on_fill(self, fill: Fill) -> None: pass
                def get_required_symbols(self): return ["BTCUSDT"]
                def validate_parameters(self): pass
        """)
        (tmp_path / "loader_test_strat.py").write_text(code)

        before = set(StrategyRegistry.list_all())
        load_user_strategies(tmp_path)
        after = set(StrategyRegistry.list_all())

        assert "_TestLoaderStrategy" in after - before

    def test_bad_syntax_does_not_crash_loader(self, tmp_path: Path):
        (tmp_path / "broken.py").write_text("def foo(: pass")
        load_user_strategies(tmp_path)  # must not raise

    def test_nonexistent_dir_is_a_noop(self):
        load_user_strategies(Path("/nonexistent/path/xyz"))  # must not raise
