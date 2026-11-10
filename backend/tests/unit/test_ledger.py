import pytest

from app.domain.strategies.base.ledger import Ledger


class _DummyLedger(Ledger):
    def __init__(self, cash: float, units: float):
        self.cash = cash
        self.units = units

    def equity(self, price: float) -> float:
        return self.cash + self.units * price


def test_ledger_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Ledger()


def test_dummy_ledger_reports_equity():
    ledger = _DummyLedger(cash=100.0, units=2.0)
    assert ledger.equity(price=50.0) == 200.0
