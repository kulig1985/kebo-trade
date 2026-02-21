"""
Bounce Scalper Stratégia - Konfiguráció
========================================

Mean Reversion alapú scalping stratégia.
EMA-ATR sávokról való visszapattanásra épül.
"""

from decimal import Decimal

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId


class BounceScalperConfig(StrategyConfig, frozen=True):
    """
    Bounce Scalper stratégia konfiguráció.

    LONG-only mean reversion scalping:
    - Entry: ár leesik EMA - X*ATR alá
    - Exit: Take Profit VAGY Stop Loss VAGY ár visszamegy EMA fölé
    """

    # ========================================================================
    # INSTRUMENTEK
    # ========================================================================
    instrument_ids: frozenset[InstrumentId]

    # Bar type-ok minden instrumenthez (a backtest/live script állítja össze)
    bar_types: dict[InstrumentId, BarType]  # 5m barok

    # ========================================================================
    # POZÍCIÓ MÉRET
    # ========================================================================
    # Egy trade mérete USDC-ben
    trade_size_usdc: Decimal = Decimal("5.0")

    # Maximum egyidejű pozíciók száma PÁRONKÉNT
    max_positions_per_instrument: int = 1

    # ========================================================================
    # ENTRY PARAMÉTEREK
    # ========================================================================
    # EMA periódus (az átlaghoz)
    ema_period: int = 20

    # ATR periódus (volatilitás méréshez)
    atr_period: int = 14

    # Entry zóna: EMA - (entry_atr_multiplier * ATR)
    # Ha az ár FELFELÉ keresztezi ezt a szintet → BUY (bounce)
    entry_atr_multiplier: Decimal = Decimal("0.8")

    # ========================================================================
    # EXIT PARAMÉTEREK
    # ========================================================================
    # Take Profit százalék (entry price-tól)
    # Optimalizált: 1.0% gyors scalping-hez
    take_profit_pct: Decimal = Decimal("1.0")

    # Stop Loss százalék (entry price-tól)
    # Optimalizált: 1.5% tight stop
    stop_loss_pct: Decimal = Decimal("1.5")

    # Exit zóna: ha az ár visszamegy EMA + (exit_atr_multiplier * ATR) fölé
    # None = kikapcsolva, csak TP/SL működik (ajánlott scalping-hez)
    exit_atr_multiplier: Decimal | None = None

    # ========================================================================
    # BIZTONSÁGI BEÁLLÍTÁSOK
    # ========================================================================
    # Minimum szabad egyenleg USDC-ben új pozíció nyitáshoz
    # (trade_size_usdc + buffer)
    min_free_balance_usdc: Decimal = Decimal("10.0")

    # Cooldown (bar-okban) egy pozíció zárása után
    # (megakadályozza az azonnali újra belépést)
    cooldown_ticks: int = 10
