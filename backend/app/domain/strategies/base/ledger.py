"""Minimal contract shared across strategy-family ledgers. Deliberately the ONLY shared
abstraction shipped with the grid family (see docs/superpowers/specs/2026-08-28-grid-bot-design.md,
"Abstraction level") — StrategyFamily/SimulationEngine/FamilyRegistry are deferred until a second
family exists to prove their shape.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Ledger(ABC):
    """Anything that can report its mark-to-market equity at a given price.

    Both a moving-average-cost-basis ledger (accumulation.py's shape) and a per-rung-lot ledger
    (grid's shape) implement this despite completely different internal accounting — it's the one
    piece metrics.compute_metrics / monte_carlo.run_monte_carlo actually need in common.
    """

    @abstractmethod
    def equity(self, price: float) -> float:
        ...
