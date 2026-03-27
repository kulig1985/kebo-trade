"""
Grid Strategy
=============

FIGYELEM: Ez a stratégia JELENLEG NEM VALÓDI GRID!
A klasszikus grid stratégia csak SPOT piacon működik.

Jelenlegi működés:
- Grid orderek elhelyezése
- Ha egy teljesül → összes többi törlés → TP/SL mód
- TP vagy SL fill → grid újraindítás

Ez inkább egy "Range Entry + TP/SL" stratégia.

Futtatás:
    # Live (futures)
    python -m strategies.grid.run_live

    # Backtest
    python -m strategies.grid.run_backtest
"""

from strategies.grid.config import GridStrategyConfig
from strategies.grid.strategy import GridStrategy

__all__ = ["GridStrategy", "GridStrategyConfig"]
