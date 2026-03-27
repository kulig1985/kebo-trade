"""
Bounce Scalper - Backtest Futtatás (MongoDB Integrációval)
==========================================================

Futtatás:
    cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade
    python run/run_backtest.py

MongoDB:
    - Alapértelmezetten KIKAPCSOLVA backtest módban
    - Bekapcsolható: export MONGODB_ENABLED="true"

Eredmények:
    backtest_results/ mappába exportálja a riportokat
"""

import asyncio
import time
from datetime import datetime, UTC
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
from nautilus_trader.persistence.wranglers import BarDataWrangler

import os
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from persistence.config import MongoDBConfig
from persistence.publisher import MongoDBPublisher
from strategies.bounce_scalper import BounceScalper
from strategies.bounce_scalper.config import BounceScalperConfig


# ============================================================================
# ÚTVONALAK
# ============================================================================

# Alap mappa (finals/)
BASE_DIR = Path(__file__).parent.parent

# Adat mappa
DATA_DIR = BASE_DIR / "data" / "bounce_data"

# Eredmények mappa
RESULTS_DIR = BASE_DIR / "backtest_results"
RESULTS_DIR.mkdir(exist_ok=True)


# ============================================================================
# KONFIGURÁCIÓ
# ============================================================================

# Timeframe a stratégiához ("1m" vagy "5m")
TIMEFRAME = "5m"

# Párok
SYMBOLS = [
    #"BTC/USDC",
    #"ETH/USDC",
    "SOL/USDC",
    "ARB/USDC",
    #"TIA/USDC",
    #"ADA/USDC",
    #"AVAX/USDC",
    #"DOGE/USDC",
]

# Backtest időszak (a fájlnevekből)
START_DATE = "20251101"
END_DATE = "20260221"

# Kezdő egyenleg
STARTING_USDC = 1000.0

# Stratégia azonosító
STRATEGY_TYPE = "bounce_scalper"
STRATEGY_ID = "bounce_scalper_backtest_001"


# ============================================================================
# RIPORT EXPORTÁLÁS
# ============================================================================

def save_strategy_reports(
    engine: BacktestEngine,
    config: BounceScalperConfig,
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
    # Időbélyeg a fájlnévhez
    dt = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # Paraméterek a fájlnévhez
    entry_mult = str(config.entry_atr_multiplier).replace(".", "p")
    tp = str(config.take_profit_pct).replace(".", "p")
    sl = str(config.stop_loss_pct).replace(".", "p")

    prefix = f"bounce_{dt}_entry{entry_mult}_tp{tp}_sl{sl}"

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
        f.write("BOUNCE SCALPER - BACKTEST ÖSSZEFOGLALÓ\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Időpont: {datetime.now(UTC).isoformat()}\n")
        f.write(f"Időszak: {START_DATE} - {END_DATE}\n\n")

        f.write("KONFIGURÁCIÓ:\n")
        f.write(f"  Timeframe: {TIMEFRAME}\n")
        f.write(f"  Instrumentek: {len(config.instrument_ids)}\n")
        f.write(f"  Trade size: {config.trade_size_usdc} USDC\n")
        f.write(f"  EMA period: {config.ema_period}\n")
        f.write(f"  ATR period: {config.atr_period}\n")
        f.write(f"  Entry ATR mult: {config.entry_atr_multiplier}\n")
        f.write(f"  Take Profit: {config.take_profit_pct}%\n")
        f.write(f"  Stop Loss: {config.stop_loss_pct}%\n")
        f.write(f"  Cooldown: {config.cooldown_ticks} bars\n\n")

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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

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

    # Precision beállítások coin típus szerint
    if base_code in ["BTC", "ETH"]:
        price_precision = 2
        size_precision = 5
        price_increment = Price.from_str("0.01")
        size_increment = Quantity.from_str("0.00001")
        min_qty = Quantity.from_str("0.00001")
    elif base_code in ["SOL", "AVAX"]:
        price_precision = 3
        size_precision = 3
        price_increment = Price.from_str("0.001")
        size_increment = Quantity.from_str("0.001")
        min_qty = Quantity.from_str("0.001")
    else:
        # ARB, TIA, ADA, DOGE - kis értékű coinok
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


def load_bars(
    instrument: CurrencyPair, timeframe: str, data_dir: Path
) -> tuple[BarType, list]:
    """CSV adatok betöltése és Bar objektumokká alakítása."""
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
    else:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    bar_type = BarType(
        instrument_id=instrument.id,
        bar_spec=bar_spec,
        aggregation_source=AggregationSource.EXTERNAL,
    )

    wrangler = BarDataWrangler(bar_type, instrument)
    bars = wrangler.process(df)

    return bar_type, bars


# ============================================================================
# MAIN
# ============================================================================

async def run_backtest_async():
    """Backtest futtatása MongoDB integrációval (opcionális)."""
    print("=" * 70)
    print("BOUNCE SCALPER - BACKTEST")
    print("=" * 70)

    # ═══════════════════════════════════════════════════════════════════════
    # MONGODB SETUP (alapértelmezetten kikapcsolva backtest-nél)
    # ═══════════════════════════════════════════════════════════════════════

    # Backtest-nél alapértelmezetten kikapcsoljuk a MongoDB-t
    # Ha mégis kell, állítsd be: MONGODB_ENABLED=true
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

    # Engine létrehozása
    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id=TraderId("BOUNCE-001"),
            logging=LoggingConfig(
                log_level="INFO",
                log_colors=True,
            ),
        )
    )

    # Venue hozzáadása
    venue = Venue("BINANCE")

    # Kezdő egyenlegek
    starting_balances = [Money(STARTING_USDC, USDC)]
    for symbol in SYMBOLS:
        base_code = symbol.split("/")[0]
        base_ccy = Currency.from_str(base_code, strict=False)
        starting_balances.append(Money(0, base_ccy))

    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=starting_balances,
        default_leverage=Decimal(1),
    )

    print(f"\n1. Venue: {venue}")
    print(f"   Starting USDC: {STARTING_USDC}")

    # Instrumentek és adatok betöltése
    print("\n2. Instrumentek és adatok betöltése...")

    instruments = {}
    bar_types = {}
    all_bars = []

    for symbol in SYMBOLS:
        print(f"\n   {symbol}:")

        instrument = create_instrument(symbol, venue)
        engine.add_instrument(instrument)
        instruments[instrument.id] = instrument

        try:
            bar_type, bars = load_bars(instrument, TIMEFRAME, DATA_DIR)
            all_bars.extend(bars)
            bar_types[instrument.id] = bar_type
            print(f"     ✓ {TIMEFRAME}: {len(bars):,} bars")
        except FileNotFoundError as e:
            print(f"     ✗ {TIMEFRAME}: {e}")
            continue

    # Adatok hozzáadása
    print("\n3. Adatok hozzáadása az engine-hez...")
    engine.add_data(all_bars)
    print(f"   ✓ {TIMEFRAME} bars: {len(all_bars):,}")

    # Stratégia konfiguráció
    print("\n4. Stratégia konfiguráció...")

    instrument_ids = frozenset(bar_types.keys())

    config = BounceScalperConfig(
        instrument_ids=instrument_ids,
        bar_types=bar_types,
        # Pozíció méret
        trade_size_usdc=Decimal("5.0"),
        max_positions_per_instrument=1,
        # Indikátorok
        ema_period=20,
        atr_period=14,
        entry_atr_multiplier=Decimal("0.8"),
        # Exit
        take_profit_pct=Decimal("1.0"),
        stop_loss_pct=Decimal("1.5"),
        exit_atr_multiplier=None,
        # Biztonság
        min_free_balance_usdc=Decimal("10.0"),
        cooldown_ticks=10,
    )

    print(f"   ✓ Instrumentek: {len(instrument_ids)}")
    print(f"   ✓ Trade size: {config.trade_size_usdc} USDC")
    print(f"   ✓ EMA period: {config.ema_period}")
    print(f"   ✓ ATR period: {config.atr_period}")
    print(f"   ✓ Entry ATR mult: {config.entry_atr_multiplier}")
    print(f"   ✓ Take Profit: {config.take_profit_pct}%")
    print(f"   ✓ Stop Loss: {config.stop_loss_pct}%")
    print(f"   ✓ Cooldown: {config.cooldown_ticks} bars")

    # Stratégia hozzáadása
    strategy = BounceScalper(config=config)

    # MongoDB persistence beállítása (ha engedélyezve van)
    if publisher:
        strategy.set_persistence(publisher)

    engine.add_strategy(strategy)

    # Backtest futtatása
    print("\n5. Backtest futtatása...")
    print("=" * 70)

    engine.run()

    # Riportok exportálása
    print("\n6. Riportok exportálása...")
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
    print("BACKTEST BEFEJEZVE")
    print("=" * 70)


def run_backtest():
    """Szinkron wrapper a backtest futtatásához."""
    asyncio.run(run_backtest_async())


if __name__ == "__main__":
    run_backtest()
