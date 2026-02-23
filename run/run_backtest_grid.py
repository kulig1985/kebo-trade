"""
Grid Strategy - Backtest Futtatás (MongoDB Integrációval)
==========================================================

Futtatás:
    cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade
    python run/run_backtest_grid.py

MongoDB:
    - Alapértelmezetten KIKAPCSOLVA backtest módban
    - Bekapcsolható: export MONGODB_ENABLED="true"

Eredmények:
    backtest_results/ mappába exportálja a riportokat
"""

import asyncio
import os
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.enums import (
    AccountType,
    AggregationSource,
    BarAggregation,
    OmsType,
    PriceType,
)
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency, Money, Price, Quantity
from nautilus_trader.persistence.wranglers import BarDataWrangler, QuoteTickDataWrangler

sys.path.insert(0, str(Path(__file__).parent.parent))

from persistence.config import MongoDBConfig
from persistence.publisher import MongoDBPublisher
from strategies.grid_strategy import GridStrategy
from strategies.grid_strategy_config import GridStrategyConfig


# ═══════════════════════════════════════════════════════════════════════════════
# ÚTVONALAK
# ═══════════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "grid_data"
RESULTS_DIR = BASE_DIR / "backtest_results"
RESULTS_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# KONFIGURÁCIÓ
# ═══════════════════════════════════════════════════════════════════════════════

# Timeframe - a Grid Strategy 15 perces bar-okat használ
TIMEFRAME = "15m"

# Trading pár (egyetlen instrumentum)
SYMBOL = "BTC/USDC"

# Backtest időszak
START_DATE = "20250101"
END_DATE = "20260222"

# Kezdő egyenleg
STARTING_USDC = 1000.0

# Stratégia azonosító
STRATEGY_TYPE = "grid_strategy"
STRATEGY_ID = "grid_strategy_backtest_001"


# ═══════════════════════════════════════════════════════════════════════════════
# RIPORT EXPORTÁLÁS
# ═══════════════════════════════════════════════════════════════════════════════


def save_strategy_reports(
    engine: BacktestEngine,
    config: GridStrategyConfig,
    results_dir: Path,
):
    """
    Backtest riportok mentése CSV fájlokba.

    Fájlok:
        - {prefix}_orders.csv    - Összes order
        - {prefix}_fills.csv     - Order teljesülések
        - {prefix}_positions.csv - Pozíciók
        - {prefix}_summary.txt   - Összefoglaló
    """
    dt = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # Paraméterek a fájlnévhez
    levels = str(config.grid_levels)
    offset = str(config.grid_offset_pct).replace(".", "p")
    tp = str(config.take_profit_pct).replace(".", "p")
    sl = str(config.stop_loss_pct).replace(".", "p")

    prefix = f"grid_{dt}_L{levels}_off{offset}_tp{tp}_sl{sl}"

    # Riportok generálása
    orders_df = engine.trader.generate_orders_report()
    fills_df = engine.trader.generate_order_fills_report()
    positions_df = engine.trader.generate_positions_report()

    # CSV mentés
    orders_path = results_dir / f"{prefix}_orders.csv"
    fills_path = results_dir / f"{prefix}_fills.csv"
    positions_path = results_dir / f"{prefix}_positions.csv"

    orders_df.to_csv(orders_path, sep=";")
    fills_df.to_csv(fills_path, sep=";")
    positions_df.to_csv(positions_path, sep=";")

    # Összefoglaló mentése
    summary_path = results_dir / f"{prefix}_summary.txt"
    with open(summary_path, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("GRID STRATEGY - BACKTEST ÖSSZEFOGLALÓ\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Időpont: {datetime.now(UTC).isoformat()}\n")
        f.write(f"Időszak: {START_DATE} - {END_DATE}\n\n")

        f.write("KONFIGURÁCIÓ:\n")
        f.write(f"  Instrument: {config.instrument_id}\n")
        f.write(f"  Timeframe: {TIMEFRAME}\n")
        f.write(f"  Grid levels: {config.grid_levels}\n")
        f.write(f"  Grid offset: {config.grid_offset_pct}%\n")
        f.write(f"  Order quantity: {config.order_quantity}\n")
        f.write(f"  Take Profit: {config.take_profit_pct}%\n")
        f.write(f"  Stop Loss: {config.stop_loss_pct}%\n")
        f.write(f"  Breakout threshold: {config.breakout_threshold_pct}%\n")
        f.write(f"  Max drawdown: {config.max_drawdown_pct}%\n")
        f.write(f"  ATR period: {config.atr_period}\n")
        f.write(f"  SMA fast: {config.sma_fast_period}\n")
        f.write(f"  SMA slow: {config.sma_slow_period}\n\n")

        f.write("EREDMÉNYEK:\n")
        f.write(f"  Összes order: {len(orders_df)}\n")
        f.write(f"  Összes fill: {len(fills_df)}\n")
        f.write(f"  Összes pozíció: {len(positions_df)}\n\n")

        f.write("FÁJLOK:\n")
        f.write(f"  {orders_path.name}\n")
        f.write(f"  {fills_path.name}\n")
        f.write(f"  {positions_path.name}\n")

    print(f"\n📁 Riportok mentve: {results_dir}")
    print(f"   • {orders_path.name}")
    print(f"   • {fills_path.name}")
    print(f"   • {positions_path.name}")
    print(f"   • {summary_path.name}")

    return prefix


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def create_instrument(symbol: str, venue: Venue) -> CurrencyPair:
    """CurrencyPair instrument létrehozása."""
    base_code, quote_code = symbol.split("/")

    instrument_id = InstrumentId(
        symbol=Symbol(symbol.replace("/", "")),
        venue=venue,
    )

    base_ccy = Currency.from_str(base_code, strict=False)
    quote_ccy = Currency.from_str(quote_code, strict=False)

    ts_now = int(time.time() * 1e9)

    # Precision beállítások (BTC/USDC)
    if base_code == "BTC":
        price_precision = 2
        size_precision = 5
        price_increment = Price.from_str("0.01")
        size_increment = Quantity.from_str("0.00001")
        min_qty = Quantity.from_str("0.00001")
    elif base_code == "ETH":
        price_precision = 2
        size_precision = 4
        price_increment = Price.from_str("0.01")
        size_increment = Quantity.from_str("0.0001")
        min_qty = Quantity.from_str("0.0001")
    elif base_code in ["SOL", "AVAX"]:
        price_precision = 3
        size_precision = 3
        price_increment = Price.from_str("0.001")
        size_increment = Quantity.from_str("0.001")
        min_qty = Quantity.from_str("0.001")
    else:
        # Default kisebb coinokhoz
        price_precision = 5
        size_precision = 1
        price_increment = Price.from_str("0.00001")
        size_increment = Quantity.from_str("0.1")
        min_qty = Quantity.from_str("0.1")

    return CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=Symbol(symbol.replace("/", "")),
        base_currency=base_ccy,
        quote_currency=quote_ccy,
        price_precision=price_precision,
        size_precision=size_precision,
        price_increment=price_increment,
        size_increment=size_increment,
        lot_size=size_increment,
        min_quantity=min_qty,
        max_quantity=Quantity.from_str("1000000"),
        ts_event=ts_now,
        ts_init=ts_now,
    )


def load_bars_and_ticks(
    instrument: CurrencyPair, timeframe: str, data_dir: Path
) -> tuple[BarType, list, list]:
    """
    CSV adatok betöltése.

    Returns:
        bar_type: BarType objektum
        bars: Bar objektumok listája (technikai indikátorokhoz)
        ticks: QuoteTick objektumok listája (grid trading-hez)

    A Grid Strategy tick adatokat vár az ár frissítésekhez (on_quote_tick).
    Backtest-ben szintetikus QuoteTick-eket generálunk a bar OHLC adatokból.
    """
    symbol_str = str(instrument.id.symbol)
    filename = f"{symbol_str}_{START_DATE}_{END_DATE}_{timeframe}.csv"
    filepath = data_dir / filename

    if not filepath.exists():
        raise FileNotFoundError(f"Data file not found: {filepath}")

    df = pd.read_csv(filepath, parse_dates=["timestamp"], index_col="timestamp")

    # Bar type létrehozása
    if timeframe == "1m":
        bar_spec = BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)
    elif timeframe == "5m":
        bar_spec = BarSpecification(5, BarAggregation.MINUTE, PriceType.LAST)
    elif timeframe == "15m":
        bar_spec = BarSpecification(15, BarAggregation.MINUTE, PriceType.LAST)
    elif timeframe == "1h":
        bar_spec = BarSpecification(1, BarAggregation.HOUR, PriceType.LAST)
    else:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    bar_type = BarType(
        instrument_id=instrument.id,
        bar_spec=bar_spec,
        aggregation_source=AggregationSource.EXTERNAL,
    )

    # Bars betöltése (technikai indikátorokhoz)
    bar_wrangler = BarDataWrangler(bar_type, instrument)
    bars = bar_wrangler.process(df)

    # Szintetikus QuoteTick-ek generálása a bar adatokból
    # A QuoteTickDataWrangler.process_bar_data() metódus 4 ticket generál minden bar-hoz:
    # Open, High, Low, Close árakon - így a grid megfelelő tick eseményeket kap
    tick_wrangler = QuoteTickDataWrangler(instrument=instrument)
    ticks = tick_wrangler.process_bar_data(
        bid_data=df,  # Ugyanaz az adat bid-hez
        ask_data=df,  # Ugyanaz az adat ask-hoz (spread nélkül)
    )

    return bar_type, bars, ticks


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════


async def run_backtest_async():
    """Backtest futtatása MongoDB integrációval (opcionális)."""
    print("=" * 70)
    print("GRID STRATEGY - BACKTEST")
    print("=" * 70)

    # ═══════════════════════════════════════════════════════════════════════
    # MONGODB SETUP
    # ═══════════════════════════════════════════════════════════════════════

    mongo_enabled = os.environ.get("MONGODB_ENABLED", "true").lower() == "true"

    publisher = None
    if mongo_enabled:
        mongo_config = MongoDBConfig(enabled=True)
        publisher = MongoDBPublisher(
            config=mongo_config,
            strategy_type=STRATEGY_TYPE,
            strategy_id=STRATEGY_ID,
            is_backtest=True,
        )
        await publisher.start()
        print(f"\nMongoDB: enabled (backtest mode)")
        print(f"  Session: {publisher.session_id[:8]}...")
    else:
        print(f"\nMongoDB: disabled (set MONGODB_ENABLED=true to enable)")

    # ═══════════════════════════════════════════════════════════════════════
    # ENGINE SETUP
    # ═══════════════════════════════════════════════════════════════════════

    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id=TraderId("GRID-001"),
            logging=LoggingConfig(
                log_level="INFO",
                log_colors=True,
            ),
        )
    )

    # Venue hozzáadása
    venue = Venue("BINANCE")

    # Kezdő egyenlegek
    base_code = SYMBOL.split("/")[0]
    base_ccy = Currency.from_str(base_code, strict=False)

    starting_balances = [
        Money(STARTING_USDC, USDC),
        Money(0, base_ccy),
    ]

    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,  # Grid strategy uses margin
        base_currency=None,
        starting_balances=starting_balances,
        default_leverage=Decimal(1),
    )

    print(f"\n1. Venue: {venue}")
    print(f"   Starting USDC: {STARTING_USDC}")
    print(f"   Account type: MARGIN (Futures simulation)")

    # ═══════════════════════════════════════════════════════════════════════
    # INSTRUMENT & DATA
    # ═══════════════════════════════════════════════════════════════════════

    print(f"\n2. Instrument: {SYMBOL}")

    instrument = create_instrument(SYMBOL, venue)
    engine.add_instrument(instrument)

    try:
        bar_type, bars, ticks = load_bars_and_ticks(instrument, TIMEFRAME, DATA_DIR)
        print(f"   ✓ {TIMEFRAME}: {len(bars):,} bars loaded")
        print(f"   ✓ Synthetic ticks: {len(ticks):,} quote ticks generated")
    except FileNotFoundError as e:
        print(f"   ✗ {e}")
        print(f"\n   Hozz létre adat fájlt: {DATA_DIR}/{instrument.id.symbol}_{START_DATE}_{END_DATE}_{TIMEFRAME}.csv")
        print("   Formátum: timestamp,open,high,low,close,volume")
        return

    # FONTOS: Mindkét adattípust hozzáadjuk!
    # - Bars: 15 perces technikai indikátorokhoz (on_bar)
    # - Ticks: Valós idejű ár események (on_quote_tick) - ugyanúgy mint live-ban
    engine.add_data(bars)
    engine.add_data(ticks)

    # ═══════════════════════════════════════════════════════════════════════
    # STRATEGY CONFIG
    # ═══════════════════════════════════════════════════════════════════════

    print("\n3. Strategy configuration...")

    config = GridStrategyConfig(
        instrument_id=instrument.id,
        # Grid paraméterek
        grid_levels=15,
        order_quantity=Decimal("0.001"),  # 0.001 BTC per grid order
        grid_offset_pct=Decimal("8.0"),  # ±4% az aktuális ár körül
        take_profit_pct=Decimal("1.2"),
        stop_loss_pct=Decimal("2.0"),
        # Újraközpontosítás
        recenter_drift_threshold_pct=Decimal("3.0"),
        recenter_interval_seconds=300,
        # Kockázatkezelés
        breakout_threshold_pct=Decimal("6.0"),
        trailing_stop_threshold_pct=Decimal("8.0"),
        max_drawdown_pct=Decimal("15.0"),
        max_long_notional=Decimal("800.0"),
        max_short_notional=Decimal("800.0"),
        max_total_notional=Decimal("1200.0"),
        # Funkciók
        volatility_adapt_offset=True,
        enable_breakout_stop=True,
        enable_exposure_limits=True,
        enable_trailing_stop=True,
        enable_max_drawdown=True,
        enable_auto_resume=True,
        enable_dynamic_grid_levels=True,
        # Dinamikus grid
        min_grid_levels=5,
        max_grid_levels=30,
        # Indikátorok
        atr_period=14,
        sma_fast_period=9,
        sma_slow_period=21,
    )

    print(f"   ✓ Grid levels: {config.grid_levels}")
    print(f"   ✓ Grid offset: ±{config.grid_offset_pct / 2}%")
    print(f"   ✓ Order quantity: {config.order_quantity}")
    print(f"   ✓ Take Profit: {config.take_profit_pct}%")
    print(f"   ✓ Stop Loss: {config.stop_loss_pct}%")
    print(f"   ✓ ATR period: {config.atr_period}")
    print(f"   ✓ Dynamic grid: {config.enable_dynamic_grid_levels}")

    # ═══════════════════════════════════════════════════════════════════════
    # STRATEGY
    # ═══════════════════════════════════════════════════════════════════════

    strategy = GridStrategy(config=config)

    if publisher:
        strategy.set_persistence(publisher)

    engine.add_strategy(strategy)

    # ═══════════════════════════════════════════════════════════════════════
    # RUN BACKTEST
    # ═══════════════════════════════════════════════════════════════════════

    print("\n4. Running backtest...")
    print("=" * 70)

    engine.run()

    # ═══════════════════════════════════════════════════════════════════════
    # REPORTS
    # ═══════════════════════════════════════════════════════════════════════

    print("\n5. Exporting reports...")
    save_strategy_reports(engine, config, RESULTS_DIR)

    # MongoDB leállítása
    if publisher:
        await publisher.stop(
            reason="NORMAL",
            state_snapshot=strategy.on_save(),
        )

    # Cleanup
    engine.dispose()

    print("\n" + "=" * 70)
    print("BACKTEST COMPLETE")
    print("=" * 70)


def run_backtest():
    """Szinkron wrapper."""
    asyncio.run(run_backtest_async())


if __name__ == "__main__":
    run_backtest()
