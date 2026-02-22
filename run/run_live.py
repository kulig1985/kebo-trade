"""
Bounce Scalper - Live Trading (MongoDB + Docker támogatás)
==========================================================

FIGYELEM: Ez VALÓS pénzzel kereskedik!
Először MINDIG tesztelj TESTNET-en!

Futtatás (lokális):
    cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade

    export BINANCE_API_KEY="your_api_key"
    export BINANCE_API_SECRET="your_api_secret"
    export BINANCE_TESTNET="true"
    python run/run_live.py

Futtatás (Docker):
    docker-compose up -d

Külső config:
    Ha USE_EXTERNAL_CONFIG=true, akkor a /app/config/strategy.json-t olvassa
"""

import asyncio
import json
import os
import signal
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nautilus_trader.adapters.binance.common.enums import BinanceAccountType
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig, BinanceExecClientConfig
from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory, BinanceLiveExecClientFactory
from nautilus_trader.config import InstrumentProviderConfig, LiveExecEngineConfig, LoggingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, TraderId

from persistence.config import MongoDBConfig
from persistence.publisher import MongoDBPublisher
from persistence.sync import MongoDBSyncService
from strategies.bounce_scalper import BounceScalper
from strategies.bounce_scalper_config import BounceScalperConfig


# ============================================================================
# DEFAULT KONFIGURÁCIÓ
# ============================================================================

DEFAULT_CONFIG = {
    "strategy_type": "bounce_scalper",
    "strategy_id": "bounce_scalper_live_001",
    "symbols": [
        "BTCUSDC",
        "ETHUSDC",
        "SOLUSDC",
        "ARBUSDC",
        "TIAUSDC",
        "ADAUSDC",
        "AVAXUSDC",
        "DOGEUSDC",
    ],
    "parameters": {
        "trade_size_usdc": 5.0,
        "max_positions_per_instrument": 1,
        "take_profit_pct": 1.0,
        "stop_loss_pct": 1.5,
        "ema_period": 20,
        "atr_period": 14,
        "entry_atr_multiplier": 0.8,
        "exit_atr_multiplier": None,
        "min_free_balance_usdc": 10.0,
        "cooldown_ticks": 10,
    },
}


def load_config() -> dict:
    """
    Konfiguráció betöltése.

    Prioritás:
    1. Külső JSON fájl (/app/config/strategy.json) ha USE_EXTERNAL_CONFIG=true
    2. Környezeti változókból (STRATEGY_ID)
    3. DEFAULT_CONFIG
    """
    config = DEFAULT_CONFIG.copy()

    # Külső config fájl ellenőrzése
    use_external = os.environ.get("USE_EXTERNAL_CONFIG", "false").lower() == "true"
    external_config_path = Path("/app/config/strategy.json")

    if use_external and external_config_path.exists():
        print(f"Loading external config: {external_config_path}")
        with open(external_config_path) as f:
            external_config = json.load(f)
            # Merge config
            config["strategy_type"] = external_config.get("strategy_type", config["strategy_type"])
            config["strategy_id"] = external_config.get("strategy_id", config["strategy_id"])
            config["symbols"] = external_config.get("symbols", config["symbols"])
            if "parameters" in external_config:
                config["parameters"].update(external_config["parameters"])

    # Environment override for strategy_id
    env_strategy_id = os.environ.get("STRATEGY_ID")
    if env_strategy_id:
        config["strategy_id"] = env_strategy_id

    return config


def is_running_in_docker() -> bool:
    """Ellenőrzi, hogy Docker-ben fut-e."""
    return (
        os.path.exists("/.dockerenv") or
        os.environ.get("DOCKER_CONTAINER", "false").lower() == "true"
    )


async def run_with_mongodb():
    """Live trading indítása MongoDB integrációval."""
    print("=" * 70)
    print("BOUNCE SCALPER - LIVE TRADING")
    print("=" * 70)

    in_docker = is_running_in_docker()
    if in_docker:
        print("Running in Docker container")

    # Konfiguráció betöltése
    config_data = load_config()
    strategy_type = config_data["strategy_type"]
    strategy_id = config_data["strategy_id"]
    symbols = config_data["symbols"]
    params = config_data["parameters"]

    # API kulcsok ellenőrzése
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    is_testnet = os.environ.get("BINANCE_TESTNET", "true").lower() == "true"

    if not api_key or not api_secret:
        print("\n❌ HIBA: Binance API kulcsok nincsenek beállítva!")
        print("\nÁllítsd be a környezeti változókat:")
        print("  export BINANCE_API_KEY='your_api_key'")
        print("  export BINANCE_API_SECRET='your_api_secret'")
        if in_docker:
            print("\nDocker használatához: .env fájl vagy -e flag")
        return

    mode = "TESTNET" if is_testnet else "🔴 LIVE (VALÓS PÉNZ!)"
    print(f"\nMód: {mode}")
    print(f"Strategy ID: {strategy_id}")
    print(f"Trade size: {params['trade_size_usdc']} USDC")
    print(f"Take Profit: {params['take_profit_pct']}%")
    print(f"Stop Loss: {params['stop_loss_pct']}%")

    # Docker-ben NEM kérünk megerősítést (nem interaktív)
    if not is_testnet and not in_docker:
        print("\n⚠️  FIGYELMEZTETÉS: VALÓS PÉNZZEL FOGSZ KERESKEDNI!")
        confirm = input("Biztosan folytatod? (yes/no): ")
        if confirm.lower() != "yes":
            print("Megszakítva.")
            return

    # ═══════════════════════════════════════════════════════════════════════
    # MONGODB SETUP
    # ═══════════════════════════════════════════════════════════════════════
    mongo_config = MongoDBConfig()
    publisher = MongoDBPublisher(
        config=mongo_config,
        strategy_type=strategy_type,
        strategy_id=strategy_id,
        is_backtest=False,
    )

    print(f"\nMongoDB: {'enabled' if mongo_config.enabled else 'disabled'}")
    if mongo_config.enabled:
        print(f"  Database: {mongo_config.database_name}")
        print(f"  Session: {publisher.session_id[:8]}...")

    # MongoDB indítása
    await publisher.start()

    # Sync service (startup sync-hez)
    sync_service = MongoDBSyncService(db=publisher.db)

    # ═══════════════════════════════════════════════════════════════════════
    # TRADING NODE SETUP
    # ═══════════════════════════════════════════════════════════════════════

    log_level = os.environ.get("LOG_LEVEL", "INFO")

    # TradingNode konfiguráció - RECONCILIATION ENABLED
    node_config = TradingNodeConfig(
        trader_id=TraderId("BOUNCE-LIVE-001"),
        logging=LoggingConfig(
            log_level=log_level,
            log_colors=not in_docker,  # Docker-ben nincs szín
        ),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=60,
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
        for symbol in symbols
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
    strategy_config = BounceScalperConfig(
        instrument_ids=instrument_ids,
        bar_types=bar_types,
        trade_size_usdc=Decimal(str(params["trade_size_usdc"])),
        max_positions_per_instrument=params["max_positions_per_instrument"],
        ema_period=params["ema_period"],
        atr_period=params["atr_period"],
        entry_atr_multiplier=Decimal(str(params["entry_atr_multiplier"])),
        take_profit_pct=Decimal(str(params["take_profit_pct"])),
        stop_loss_pct=Decimal(str(params["stop_loss_pct"])),
        exit_atr_multiplier=Decimal(str(params["exit_atr_multiplier"])) if params["exit_atr_multiplier"] else None,
        min_free_balance_usdc=Decimal(str(params["min_free_balance_usdc"])),
        cooldown_ticks=params["cooldown_ticks"],
    )

    # Stratégia hozzáadása
    strategy = BounceScalper(config=strategy_config)

    # MongoDB persistence beállítása
    strategy.set_persistence(publisher)

    node.trader.add_strategy(strategy)

    # ═══════════════════════════════════════════════════════════════════════
    # STARTUP SYNC (MongoDB ↔ NautilusTrader)
    # ═══════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("STARTUP SYNC")
    print("=" * 70)

    sync_stats = await sync_service.sync_on_startup(
        cache=node.trader.cache,
        strategy_id=strategy_id,
        session_id=publisher.session_id,
    )

    if sync_stats.get("skipped"):
        print("MongoDB sync skipped (not connected)")
    else:
        print(f"  Previous sessions closed: {sync_stats.get('previous_sessions_closed', 0)}")
        print(f"  Positions synced: {sync_stats.get('positions_synced', 0)}")
        print(f"  Orders synced: {sync_stats.get('orders_synced', 0)}")

    # ═══════════════════════════════════════════════════════════════════════
    # SIGNAL HANDLERS
    # ═══════════════════════════════════════════════════════════════════════

    shutdown_event = asyncio.Event()

    def handle_signal(sig, frame):
        print(f"\n\nSignal received ({sig}), shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # ═══════════════════════════════════════════════════════════════════════
    # NODE INDÍTÁSA
    # ═══════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("TRADING NODE INDÍTÁSA")
    print("=" * 70)
    print(f"\nInstrumentek: {len(instrument_ids)}")
    for inst_id in sorted(instrument_ids, key=str):
        print(f"  • {inst_id}")
    print(f"\nTimeframe: 5-MINUTE")
    print(f"Entry: EMA - {params['entry_atr_multiplier']}×ATR")
    print(f"Take Profit: {params['take_profit_pct']}%")
    print(f"Stop Loss: {params['stop_loss_pct']}%")
    print("=" * 70)

    # Háttérben futtatjuk a node-ot
    node_task = asyncio.create_task(
        asyncio.to_thread(node.run),
        name="trading-node"
    )

    try:
        # Várakozás shutdown jelzésre
        await shutdown_event.wait()

    except Exception as e:
        print(f"\nError: {e}")
        await publisher.stop(reason="ERROR", state_snapshot=strategy.on_save())
        raise

    finally:
        # Graceful shutdown
        print("\nShutting down...")

        # Node leállítása
        node.stop()

        # MongoDB publisher leállítása
        await publisher.stop(
            reason="NORMAL",
            state_snapshot=strategy.on_save(),
        )

        node.dispose()
        print("Node leállítva.")


def main():
    """Entry point."""
    asyncio.run(run_with_mongodb())


if __name__ == "__main__":
    main()
