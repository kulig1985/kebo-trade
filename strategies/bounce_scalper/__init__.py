"""
Bounce Scalper Strategy
=======================

Mean Reversion alapú LONG-only scalping stratégia.
EMA-ATR sávokról való visszapattanásra épül.

Futtatás:
    # Live (spot)
    python -m strategies.bounce_scalper.run_live_spot

    # Live (futures)
    python -m strategies.bounce_scalper.run_live_futures

    # Backtest
    python -m strategies.bounce_scalper.run_backtest
"""

from strategies.bounce_scalper.config import BounceScalperConfig
from strategies.bounce_scalper.strategy import BounceScalper

__all__ = ["BounceScalper", "BounceScalperConfig"]
