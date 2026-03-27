"""
Grid Trading Stratégia - Konfiguráció
======================================

Geometrikus grid trading stratégia Binance Futures-re.
Automatikus rácskezelés volatilitás adaptációval.
"""

from decimal import Decimal

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.identifiers import InstrumentId


class GridStrategyConfig(StrategyConfig, frozen=True):
    """
    Grid Trading stratégia konfiguráció.

    LONG & SHORT grid trading:
    - Geometrikus grid szintek az aktuális ár körül
    - Automatikus TP/SL minden pozícióhoz
    - Volatilitás alapú grid szélesség adaptáció
    - Trend érzékelés és dinamikus grid szint számítás
    """

    # ========================================================================
    # INSTRUMENT
    # ========================================================================
    # Egyetlen instrumentumra működik
    instrument_id: InstrumentId

    # ========================================================================
    # GRID PARAMÉTEREK
    # ========================================================================
    # Grid szintek száma (mindkét irányba)
    grid_levels: int = 15

    # Order mennyiség (BASE currency-ben, pl. BTC, SOL)
    # Ha order_size_usdc meg van adva, ez ignorálva lesz!
    order_quantity: Decimal = Decimal("1.0")

    # Order méret QUOTE currency-ben (USDC)
    # Ha meg van adva (> 0), akkor az order_quantity automatikusan számítódik
    # az aktuális ár alapján: quantity = order_size_usdc / current_price
    order_size_usdc: Decimal | None = None

    # Grid szélesség (offset) százalékban
    # A teljes grid az ár ±(grid_offset/2)%-a körül helyezkedik el
    grid_offset_pct: Decimal = Decimal("8.0")  # 8% széles grid

    # Take Profit százalék (az entry price-tól)
    take_profit_pct: Decimal = Decimal("1.2")

    # Stop Loss százalék (az entry price-tól)
    stop_loss_pct: Decimal = Decimal("2.0")

    # ========================================================================
    # GRID ÚJRAKÖZPONTOSÍTÁS
    # ========================================================================
    # Újraközpontosítási küszöb - ha az ár ennyire elmozdul a középtől
    recenter_drift_threshold_pct: Decimal = Decimal("3.0")  # 3%

    # Újraközpontosítás minimum időköze (másodpercben)
    recenter_interval_seconds: int = 300  # 5 perc

    # ========================================================================
    # KOCKÁZATKEZELÉS
    # ========================================================================
    # Breakout stop - ha az ár ennyivel kimegy a grid tartományból
    breakout_threshold_pct: Decimal = Decimal("6.0")  # 6%

    # Trailing stop - maximum drawdown a csúcstól
    trailing_stop_threshold_pct: Decimal = Decimal("8.0")  # 8%

    # Maximum drawdown százalék (a kezdő equity-től)
    max_drawdown_pct: Decimal = Decimal("15.0")  # 15%

    # Maximum long oldali kitettség (notional)
    max_long_notional: Decimal = Decimal("800.0")

    # Maximum short oldali kitettség (notional)
    max_short_notional: Decimal = Decimal("800.0")

    # Maximum összes kitettség (notional)
    max_total_notional: Decimal = Decimal("1200.0")

    # ========================================================================
    # FUNKCIÓK BE/KIKAPCSOLÁSA
    # ========================================================================
    # Volatilitás alapú grid szélesség adaptáció
    volatility_adapt_offset: bool = True

    # Breakout stop engedélyezése
    enable_breakout_stop: bool = True

    # Kitettség limit engedélyezése
    enable_exposure_limits: bool = True

    # Trailing stop engedélyezése
    enable_trailing_stop: bool = True

    # Maximum drawdown stop engedélyezése
    enable_max_drawdown: bool = True

    # Automatikus újraindítás pause után
    enable_auto_resume: bool = True

    # Dinamikus grid szint számítás (volatilitás + trend alapján)
    enable_dynamic_grid_levels: bool = True

    # ========================================================================
    # AUTOMATIKUS ÚJRAINDÍTÁS
    # ========================================================================
    # Resume cooldown idő (percben)
    resume_cooldown_minutes: int = 30

    # Resume ár tolerancia - újraindítás csak ha az ár közel van az eredetihez
    resume_price_tolerance_pct: Decimal = Decimal("3.0")

    # ========================================================================
    # DINAMIKUS GRID BEÁLLÍTÁSOK
    # ========================================================================
    # Minimum és maximum grid szintek dinamikus adaptációnál
    min_grid_levels: int = 5
    max_grid_levels: int = 30

    # Maximum pozíció szorzó (max qty = order_quantity * grid_levels * multiplier)
    max_position_multiplier: Decimal = Decimal("3.0")

    # Asszimetrikus profit faktor (trend irányú trade-ekhez)
    asymmetric_profit_factor: Decimal = Decimal("1.5")

    # Minimum távolság az aktuális ártól (order validáció)
    min_order_distance_pct: Decimal = Decimal("0.1")  # 0.1%

    # ========================================================================
    # TECHNIKAI INDIKÁTOROK
    # ========================================================================
    # ATR periódus (volatilitás méréshez)
    atr_period: int = 14

    # SMA periódusok (trend érzékeléshez)
    sma_fast_period: int = 9
    sma_slow_period: int = 21
