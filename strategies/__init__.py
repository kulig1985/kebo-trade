"""
Kebo Trade Strategies
=====================

Elérhető stratégiák:
- bounce_scalper: Mean Reversion alapú LONG-only scalping
- grid: Grid trading (SPOT only - fejlesztés alatt)
"""

from strategies.base import BaseStrategy

__all__ = ["BaseStrategy"]
