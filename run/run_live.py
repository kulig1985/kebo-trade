"""
Bounce Scalper - Live Trading
=============================

FIGYELEM: Ez VALÓS pénzzel kereskedik!
Először MINDIG tesztelj TESTNET-en!

Futtatás:
    cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade

    # Környezeti változók beállítása
    export BINANCE_API_KEY="your_api_key"
    export BINANCE_API_SECRET="your_api_secret"

    # TESTNET futtatás (ajánlott először!)
    export BINANCE_TESTNET="true"
    python run/run_live.py

    # LIVE futtatás (FIGYELEM: VALÓS PÉNZ!)
    export BINANCE_TESTNET="false"
    python run/run_live.py
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nautilus_trader.adapters.binance.common.enums import BinanceAccountType
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig, BinanceExecClientConfig
from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory, BinanceLiveExecClientFactory
from nautilus_trader.config import InstrumentProviderConfig, LoggingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, TraderId

from strategies.bounce_scalper import BounceScalper
from strategies.bounce_scalper_config import BounceScalperConfig


# ============================================================================
# KONFIGURÁCIÓ (optimalizált backtest alapján)
# ============================================================================

# Párok - SPOT piacon
SYMBOLS = [
    "BTCUSDC",
    "ETHUSDC",
    "SOLUSDC",
    "ARBUSDC",
    "TIAUSDC",
    "ADAUSDC",
    "AVAXUSDC",
    "DOGEUSDC",
]

# Stratégia paraméterek
TRADE_SIZE_USDC = Decimal("5.0")       # Trade méret USDC-ben
MAX_POSITIONS_PER_INSTRUMENT = 1        # Max pozíciók páronként
TAKE_PROFIT_PCT = Decimal("1.0")        # Take Profit % - gyors scalping
STOP_LOSS_PCT = Decimal("1.5")          # Stop Loss % - tight
EMA_PERIOD = 20
ATR_PERIOD = 14
ENTRY_ATR_MULT = Decimal("0.8")         # Entry: EMA - 0.8*ATR
EXIT_ATR_MULT = None                    # Nincs exit band, csak TP/SL
MIN_FREE_BALANCE = Decimal("10.0")      # Minimum szabad egyenleg
COOLDOWN_BARS = 10                      # Gyors újra belépés


def main():
    """Live trading indítása."""
    print("=" * 70)
    print("BOUNCE SCALPER - LIVE TRADING")
    print("=" * 70)

    # API kulcsok ellenőrzése
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    is_testnet = os.environ.get("BINANCE_TESTNET", "true").lower() == "true"

    if not api_key or not api_secret:
        print("\n❌ HIBA: Binance API kulcsok nincsenek beállítva!")
        print("\nÁllítsd be a környezeti változókat:")
        print("  export BINANCE_API_KEY='your_api_key'")
        print("  export BINANCE_API_SECRET='your_api_secret'")
        print("\nTestnet használatához:")
        print("  export BINANCE_TESTNET='true'")
        return

    mode = "TESTNET" if is_testnet else "🔴 LIVE (VALÓS PÉNZ!)"
    print(f"\nMód: {mode}")
    print(f"Trade size: {TRADE_SIZE_USDC} USDC")
    print(f"Take Profit: {TAKE_PROFIT_PCT}%")
    print(f"Stop Loss: {STOP_LOSS_PCT}%")

    if not is_testnet:
        print("\n⚠️  FIGYELMEZTETÉS: VALÓS PÉNZZEL FOGSZ KERESKEDNI!")
        confirm = input("Biztosan folytatod? (yes/no): ")
        if confirm.lower() != "yes":
            print("Megszakítva.")
            return

    # TradingNode konfiguráció
    node_config = TradingNodeConfig(
        trader_id=TraderId("BOUNCE-LIVE-001"),
        logging=LoggingConfig(
            log_level="INFO",
            log_colors=True,
        ),
        data_clients={
            "BINANCE": BinanceDataClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                account_type=BinanceAccountType.SPOT,
                testnet=is_testnet,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
        exec_clients={
            "BINANCE": BinanceExecClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                account_type=BinanceAccountType.SPOT,
                testnet=is_testnet,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
    )

    # Node létrehozása
    node = TradingNode(config=node_config)
    node.add_data_client_factory("BINANCE", BinanceLiveDataClientFactory)
    node.add_exec_client_factory("BINANCE", BinanceLiveExecClientFactory)
    node.build()

    # Instrument IDs
    instrument_ids = frozenset([
        InstrumentId.from_str(f"{symbol}.BINANCE")
        for symbol in SYMBOLS
    ])

    # Bar types (5m EXTERNAL - live adatforrás)
    bar_types = {}
    for instrument_id in instrument_ids:
        bar_types[instrument_id] = BarType(
            instrument_id=instrument_id,
            bar_spec=BarSpecification(
                step=5,
                aggregation=BarAggregation.MINUTE,
                price_type=PriceType.LAST,
            ),
            aggregation_source=AggregationSource.EXTERNAL,
        )

    # Stratégia konfiguráció
    config = BounceScalperConfig(
        instrument_ids=instrument_ids,
        bar_types=bar_types,
        trade_size_usdc=TRADE_SIZE_USDC,
        max_positions_per_instrument=MAX_POSITIONS_PER_INSTRUMENT,
        ema_period=EMA_PERIOD,
        atr_period=ATR_PERIOD,
        entry_atr_multiplier=ENTRY_ATR_MULT,
        take_profit_pct=TAKE_PROFIT_PCT,
        stop_loss_pct=STOP_LOSS_PCT,
        exit_atr_multiplier=EXIT_ATR_MULT,
        min_free_balance_usdc=MIN_FREE_BALANCE,
        cooldown_ticks=COOLDOWN_BARS,
    )

    # Stratégia hozzáadása
    strategy = BounceScalper(config=config)
    node.trader.add_strategy(strategy)

    print("\n" + "=" * 70)
    print("TRADING NODE INDÍTÁSA")
    print("=" * 70)
    print(f"\nInstrumentek: {len(instrument_ids)}")
    for inst_id in sorted(instrument_ids, key=str):
        print(f"  • {inst_id}")
    print(f"\nTimeframe: 5-MINUTE")
    print(f"Entry: EMA - {ENTRY_ATR_MULT}×ATR")
    print(f"Take Profit: {TAKE_PROFIT_PCT}%")
    print(f"Stop Loss: {STOP_LOSS_PCT}%")
    print("=" * 70)

    # Node indítása (blokkoló)
    try:
        node.run()
    except KeyboardInterrupt:
        print("\n\nLeállítás (Ctrl+C)...")
    finally:
        node.dispose()
        print("Node leállítva.")


if __name__ == "__main__":
    main()
