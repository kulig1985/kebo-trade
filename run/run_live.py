"""
Live Trading Runner
===================

Futtatás:
    # Python
    MONGODB_URI="mongodb://..." python run/run_live.py

    # Docker
    docker run -e MONGODB_URI="mongodb://..." kebo-trade

Környezeti változók:
    MONGODB_URI         - MongoDB connection string (KÖTELEZŐ)
    STRATEGY_ID         - Stratégia azonosító (default: bounce_scalper_live_001)
    BINANCE_API_KEY     - Binance API key (KÖTELEZŐ)
    BINANCE_API_SECRET  - Binance API secret (KÖTELEZŐ)
    BINANCE_TESTNET     - "true"/"false" (default: true)
    LOG_LEVEL           - Logging level (default: INFO)
"""

import asyncio
import os
import signal
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nautilus_trader.adapters.binance.common.enums import BinanceAccountType, BinanceEnvironment
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig, BinanceExecClientConfig
from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory, BinanceLiveExecClientFactory
from nautilus_trader.config import InstrumentProviderConfig, LiveExecEngineConfig, LoggingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, TraderId

from persistence.config import MongoDBConfig
from persistence.config_loader import load_strategy_config
from persistence.publisher import MongoDBPublisher
from persistence.sync import MongoDBSyncService
from strategies.bounce_scalper import BounceScalper
from strategies.bounce_scalper_config import BounceScalperConfig


async def main():
    """Live trading főprogram."""
    print("=" * 60)
    print("KEBO TRADE - LIVE")
    print("=" * 60)

    # ═══════════════════════════════════════════════════════════════════════════
    # KONFIGURÁCIÓ
    # ═══════════════════════════════════════════════════════════════════════════

    # MongoDB
    mongo_config = MongoDBConfig()
    if not mongo_config.connection_string:
        print("❌ MONGODB_URI environment variable not set!")
        print("   export MONGODB_URI='mongodb://user:pass@host:27017/db'")
        return

    # Strategy ID
    strategy_id = os.environ.get("STRATEGY_ID", "bounce_scalper_live_001")

    # Config betöltése (MongoDB-ből vagy default)
    try:
        config_data = load_strategy_config(strategy_id, mongo_config)
    except ValueError as e:
        print(f"❌ {e}")
        return

    strategy_type = config_data.get("strategy_type", "bounce_scalper")
    symbols = config_data.get("symbols", ["BTCUSDC"])
    params = config_data.get("parameters", {})

    # Binance API
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")

    # Environment: TESTNET, DEMO, LIVE
    env_str = os.environ.get("BINANCE_ENV", os.environ.get("BINANCE_TESTNET", "testnet"))
    if env_str.lower() in ("true", "testnet"):
        binance_env = BinanceEnvironment.TESTNET
    elif env_str.lower() in ("demo",):
        binance_env = BinanceEnvironment.DEMO
    elif env_str.lower() in ("false", "live"):
        binance_env = BinanceEnvironment.LIVE
    else:
        binance_env = BinanceEnvironment.TESTNET

    if not api_key or not api_secret:
        print("❌ BINANCE_API_KEY and BINANCE_API_SECRET required!")
        return

    # Info
    print(f"\nStrategy: {strategy_id}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Environment: {binance_env.name}")
    print(f"Trade size: {params.get('trade_size_usdc', 5)} USDC")

    # ═══════════════════════════════════════════════════════════════════════════
    # MONGODB PUBLISHER
    # ═══════════════════════════════════════════════════════════════════════════

    publisher = MongoDBPublisher(
        config=mongo_config,
        strategy_type=strategy_type,
        strategy_id=strategy_id,
        is_backtest=False,
    )
    await publisher.start()

    sync_service = MongoDBSyncService(db=publisher.db)

    # ═══════════════════════════════════════════════════════════════════════════
    # TRADING NODE
    # ═══════════════════════════════════════════════════════════════════════════

    log_level = os.environ.get("LOG_LEVEL", "INFO")

    node_config = TradingNodeConfig(
        trader_id=TraderId("KEBO-001"),
        logging=LoggingConfig(log_level=log_level),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=60,
        ),
        data_clients={
            "BINANCE": BinanceDataClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                account_type=BinanceAccountType.SPOT,
                environment=binance_env,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
        exec_clients={
            "BINANCE": BinanceExecClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                account_type=BinanceAccountType.SPOT,
                environment=binance_env,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
    )

    node = TradingNode(config=node_config)
    node.add_data_client_factory("BINANCE", BinanceLiveDataClientFactory)
    node.add_exec_client_factory("BINANCE", BinanceLiveExecClientFactory)
    node.build()

    # Instruments
    instrument_ids = frozenset([
        InstrumentId.from_str(f"{symbol}.BINANCE")
        for symbol in symbols
    ])

    # Bar types
    bar_types = {}
    for inst_id in instrument_ids:
        bar_types[inst_id] = BarType(
            instrument_id=inst_id,
            bar_spec=BarSpecification(5, BarAggregation.MINUTE, PriceType.LAST),
            aggregation_source=AggregationSource.EXTERNAL,
        )

    # Strategy config
    strategy_config = BounceScalperConfig(
        instrument_ids=instrument_ids,
        bar_types=bar_types,
        trade_size_usdc=Decimal(str(params.get("trade_size_usdc", 5))),
        max_positions_per_instrument=params.get("max_positions_per_instrument", 1),
        ema_period=params.get("ema_period", 20),
        atr_period=params.get("atr_period", 14),
        entry_atr_multiplier=Decimal(str(params.get("entry_atr_multiplier", 0.8))),
        take_profit_pct=Decimal(str(params.get("take_profit_pct", 1.0))),
        stop_loss_pct=Decimal(str(params.get("stop_loss_pct", 1.5))),
        exit_atr_multiplier=Decimal(str(params["exit_atr_multiplier"])) if params.get("exit_atr_multiplier") else None,
        min_free_balance_usdc=Decimal(str(params.get("min_free_balance_usdc", 10))),
        cooldown_ticks=params.get("cooldown_ticks", 10),
    )

    strategy = BounceScalper(config=strategy_config)
    strategy.set_persistence(publisher)
    node.trader.add_strategy(strategy)

    # ═══════════════════════════════════════════════════════════════════════════
    # STARTUP SYNC
    # ═══════════════════════════════════════════════════════════════════════════

    print("\n" + "-" * 60)
    print("STARTUP SYNC")
    sync_stats = await sync_service.sync_on_startup(
        cache=node.cache,
        strategy_id=strategy_id,
        session_id=publisher.session_id,
    )
    print(f"  Sessions closed: {sync_stats.get('previous_sessions_closed', 0)}")
    print(f"  Positions synced: {sync_stats.get('positions_synced', 0)}")
    print("-" * 60)

    # ═══════════════════════════════════════════════════════════════════════════
    # RUN
    # ═══════════════════════════════════════════════════════════════════════════

    shutdown_event = asyncio.Event()

    def handle_signal(sig, frame):
        print(f"\nShutdown signal received...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print("\n🚀 Starting trading node...")
    node_task = asyncio.create_task(asyncio.to_thread(node.run))

    try:
        await shutdown_event.wait()
    finally:
        print("\nShutting down...")
        node.stop()
        await publisher.stop(reason="NORMAL", state_snapshot=strategy.on_save())
        node.dispose()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
