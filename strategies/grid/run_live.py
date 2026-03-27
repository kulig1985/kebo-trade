"""
Grid Strategy - Live Trading Runner (Binance FUTURES)
======================================================

Futtatás:
    MONGODB_URI="mongodb://..." python run/run_live_grid.py

Környezeti változók:
    MONGODB_URI         - MongoDB connection string (KÖTELEZŐ)
    STRATEGY_ID         - Stratégia azonosító (default: grid_strategy_futures_001)
    BINANCE_API_KEY     - Binance API key (KÖTELEZŐ)
    BINANCE_API_SECRET  - Binance API secret (KÖTELEZŐ)
    BINANCE_TESTNET     - "true"/"false" (default: true)
    SYMBOL              - Trading pár (default: BTCUSDC)
    LOG_LEVEL           - Logging level (default: INFO)
"""

import asyncio
import hashlib
import hmac
import os
import signal
import sys
import time
import urllib.parse
from decimal import Decimal
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent.parent))

from nautilus_trader.adapters.binance.common.enums import BinanceAccountType, BinanceEnvironment
from nautilus_trader.adapters.binance.config import (
    BinanceDataClientConfig,
    BinanceExecClientConfig,
)
from nautilus_trader.adapters.binance.factories import (
    BinanceLiveDataClientFactory,
    BinanceLiveExecClientFactory,
)
from nautilus_trader.config import (
    InstrumentProviderConfig,
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId, TraderId

from persistence.config import MongoDBConfig
from persistence.config_loader import load_strategy_config
from persistence.publisher import MongoDBPublisher
from persistence.sync import MongoDBSyncService
from strategies.grid import GridStrategy
from strategies.grid.config import GridStrategyConfig


# ═══════════════════════════════════════════════════════════════════════════════
# BINANCE API - Direct cancel all orders (bypass NautilusTrader)
# ═══════════════════════════════════════════════════════════════════════════════


async def cancel_all_orders_binance(
    api_key: str,
    api_secret: str,
    symbol: str,
    environment: str = "TESTNET",
) -> None:
    """
    Cancel ALL open orders for a symbol using direct Binance API call.

    This is more reliable than using NautilusTrader during shutdown because
    it doesn't depend on the trading node being in a working state.

    Args:
        api_key: Binance API key
        api_secret: Binance API secret
        symbol: Trading symbol (e.g., "SOLUSDC")
        environment: "TESTNET", "DEMO", or "LIVE"
    """
    if environment == "TESTNET":
        base_url = "https://testnet.binancefuture.com"
    elif environment == "DEMO":
        # Binance DEMO uses the same API as testnet for futures
        base_url = "https://testnet.binancefuture.com"
    else:  # LIVE
        base_url = "https://fapi.binance.com"

    print(f"  Using Binance API: {base_url}")

    endpoint = "/fapi/v1/allOpenOrders"
    url = f"{base_url}{endpoint}"

    # Create signature
    timestamp = int(time.time() * 1000)
    query_string = f"symbol={symbol}&timestamp={timestamp}"
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers = {"X-MBX-APIKEY": api_key}
    params = {"symbol": symbol, "timestamp": timestamp, "signature": signature}

    try:
        async with aiohttp.ClientSession() as session:
            # First, get open orders to show what we're cancelling
            get_endpoint = "/fapi/v1/openOrders"
            get_url = f"{base_url}{get_endpoint}"
            get_query = f"symbol={symbol}&timestamp={timestamp}"
            get_signature = hmac.new(
                api_secret.encode("utf-8"),
                get_query.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            async with session.get(
                get_url,
                headers=headers,
                params={"symbol": symbol, "timestamp": timestamp, "signature": get_signature},
            ) as resp:
                if resp.status == 200:
                    orders = await resp.json()
                    if orders:
                        print(f"  Found {len(orders)} open orders to cancel:")
                        for order in orders:
                            print(f"    - {order.get('orderId')}: {order.get('side')} {order.get('origQty')} @ {order.get('price') or order.get('stopPrice', 'MARKET')}")
                    else:
                        print("  No open orders found.")
                        return

            # Cancel all orders with DELETE request
            async with session.delete(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"  Successfully cancelled {len(result)} orders via Binance API")
                else:
                    error = await resp.text()
                    print(f"  Binance API error: {resp.status} - {error}")

                    # If batch cancel failed, try individual cancels
                    if orders:
                        print("  Trying individual order cancellation...")
                        for order in orders:
                            await cancel_single_order_binance(
                                session, base_url, api_key, api_secret,
                                symbol, order.get("orderId"),
                            )

    except Exception as e:
        print(f"  Error cancelling orders via Binance API: {e}")


async def cancel_single_order_binance(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    api_secret: str,
    symbol: str,
    order_id: int,
) -> bool:
    """Cancel a single order via Binance API."""
    endpoint = "/fapi/v1/order"
    url = f"{base_url}{endpoint}"

    timestamp = int(time.time() * 1000)
    query_string = f"symbol={symbol}&orderId={order_id}&timestamp={timestamp}"
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers = {"X-MBX-APIKEY": api_key}
    params = {
        "symbol": symbol,
        "orderId": order_id,
        "timestamp": timestamp,
        "signature": signature,
    }

    try:
        async with session.delete(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                print(f"    Cancelled order {order_id}")
                return True
            else:
                error = await resp.text()
                print(f"    Failed to cancel {order_id}: {error}")
                return False
    except Exception as e:
        print(f"    Error cancelling {order_id}: {e}")
        return False


async def main():
    """Grid Strategy Live Trading - Futures USDC Margin."""
    print("=" * 60)
    print("KEBO TRADE - GRID STRATEGY (FUTURES USDC MARGIN)")
    print("=" * 60)

    # ═══════════════════════════════════════════════════════════════════════
    # MONGODB CONFIG
    # ═══════════════════════════════════════════════════════════════════════

    mongo_config = MongoDBConfig()
    if mongo_config.enabled and not mongo_config.connection_string:
        print("❌ MONGODB_URI not set!")
        return

    # ═══════════════════════════════════════════════════════════════════════
    # STRATEGY CONFIG (from MongoDB or defaults)
    # ═══════════════════════════════════════════════════════════════════════

    strategy_id = os.environ.get("STRATEGY_ID", "grid_strategy_futures_001")

    try:
        config_data = load_strategy_config(strategy_id, mongo_config)
    except ValueError as e:
        print(f"❌ {e}")
        return

    # Symbol (pl. BTCUSDC)
    symbol = os.environ.get("SYMBOL", config_data.get("symbol", "BTCUSDC"))
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
    print(f"Symbol: {symbol}")
    print(f"Environment: {binance_env.name}")
    print(f"Account Type: USDC MARGIN (Futures)")
    print(f"Grid levels: {params.get('grid_levels', 15)}")
    if params.get("order_size_usdc"):
        print(f"Order size: {params.get('order_size_usdc')} USDC")
    else:
        print(f"Order quantity: {params.get('order_quantity', 0.001)}")

    # ═══════════════════════════════════════════════════════════════════════
    # MONGODB PUBLISHER
    # ═══════════════════════════════════════════════════════════════════════

    publisher = MongoDBPublisher(
        config=mongo_config,
        strategy_type="grid_strategy",
        strategy_id=strategy_id,
        is_backtest=False,
    )
    await publisher.start()

    sync_service = MongoDBSyncService(db=publisher.db)

    # ═══════════════════════════════════════════════════════════════════════
    # TRADING NODE - FUTURES
    # ═══════════════════════════════════════════════════════════════════════

    log_level = os.environ.get("LOG_LEVEL", "INFO")

    node_config = TradingNodeConfig(
        trader_id=TraderId("KEBO-GRID-001"),
        logging=LoggingConfig(log_level=log_level),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=60,
        ),
        data_clients={
            "BINANCE": BinanceDataClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                account_type=BinanceAccountType.USDT_FUTURES,
                environment=binance_env,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
        exec_clients={
            "BINANCE": BinanceExecClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                account_type=BinanceAccountType.USDT_FUTURES,
                environment=binance_env,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
    )

    node = TradingNode(config=node_config)
    node.add_data_client_factory("BINANCE", BinanceLiveDataClientFactory)
    node.add_exec_client_factory("BINANCE", BinanceLiveExecClientFactory)
    node.build()

    # Instrument - Futures perpetual format
    instrument_id = InstrumentId.from_str(f"{symbol}-PERP.BINANCE")

    # Strategy config
    # USDC alapú order méretezés (ha meg van adva)
    order_size_usdc = params.get("order_size_usdc")
    if order_size_usdc:
        order_size_usdc = Decimal(str(order_size_usdc))

    strategy_config = GridStrategyConfig(
        instrument_id=instrument_id,
        # Grid paraméterek
        grid_levels=params.get("grid_levels", 15),
        order_quantity=Decimal(str(params.get("order_quantity", 0.001))),
        order_size_usdc=order_size_usdc,  # USDC alapú méretezés
        grid_offset_pct=Decimal(str(params.get("grid_offset_pct", 8.0))),
        take_profit_pct=Decimal(str(params.get("take_profit_pct", 1.2))),
        stop_loss_pct=Decimal(str(params.get("stop_loss_pct", 2.0))),
        # Újraközpontosítás
        recenter_drift_threshold_pct=Decimal(
            str(params.get("recenter_drift_threshold_pct", 3.0))
        ),
        recenter_interval_seconds=params.get("recenter_interval_seconds", 300),
        # Kockázatkezelés
        breakout_threshold_pct=Decimal(
            str(params.get("breakout_threshold_pct", 6.0))
        ),
        trailing_stop_threshold_pct=Decimal(
            str(params.get("trailing_stop_threshold_pct", 8.0))
        ),
        max_drawdown_pct=Decimal(str(params.get("max_drawdown_pct", 15.0))),
        max_long_notional=Decimal(str(params.get("max_long_notional", 800.0))),
        max_short_notional=Decimal(str(params.get("max_short_notional", 800.0))),
        max_total_notional=Decimal(str(params.get("max_total_notional", 1200.0))),
        # Funkciók
        volatility_adapt_offset=params.get("volatility_adapt_offset", True),
        enable_breakout_stop=params.get("enable_breakout_stop", True),
        enable_exposure_limits=params.get("enable_exposure_limits", True),
        enable_trailing_stop=params.get("enable_trailing_stop", True),
        enable_max_drawdown=params.get("enable_max_drawdown", True),
        enable_auto_resume=params.get("enable_auto_resume", True),
        enable_dynamic_grid_levels=params.get("enable_dynamic_grid_levels", True),
        # Dinamikus grid
        min_grid_levels=params.get("min_grid_levels", 5),
        max_grid_levels=params.get("max_grid_levels", 30),
        # Indikátorok
        atr_period=params.get("atr_period", 14),
        sma_fast_period=params.get("sma_fast_period", 9),
        sma_slow_period=params.get("sma_slow_period", 21),
    )

    # Create strategy
    strategy = GridStrategy(config=strategy_config)
    strategy.set_persistence(publisher)

    node.trader.add_strategy(strategy)

    # ═══════════════════════════════════════════════════════════════════════
    # STARTUP SYNC
    # ═══════════════════════════════════════════════════════════════════════

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

    # ═══════════════════════════════════════════════════════════════════════
    # RUN
    # ═══════════════════════════════════════════════════════════════════════

    shutdown_event = asyncio.Event()
    shutdown_reason = "NORMAL"

    def handle_shutdown(sig_name: str):
        nonlocal shutdown_reason
        print(f"\n⚠️ Received {sig_name}, initiating graceful shutdown...")
        shutdown_reason = sig_name
        shutdown_event.set()

    # Register signal handlers using asyncio (works properly in async context)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_shutdown, sig.name)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: handle_shutdown(signal.Signals(s).name))

    print("\n" + "=" * 60)
    print("🚀 STARTING - Grid Strategy Futures USDC Margin")
    print("=" * 60)

    # Start node in background thread
    node_task = asyncio.create_task(asyncio.to_thread(node.run))

    print("✅ RUNNING - Grid Strategy")
    print("Press Ctrl+C to stop")

    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        shutdown_reason = "CANCELLED"

    # ═══════════════════════════════════════════════════════════════════════
    # SHUTDOWN - CRITICAL: Cancel all orders using direct Binance API
    # ═══════════════════════════════════════════════════════════════════════

    print("\n" + "-" * 60)
    print("SHUTDOWN - Cancelling ALL orders via Binance API...")

    # FONTOS: Közvetlen Binance API hívás - ez MINDIG működik!
    # A NautilusTrader cancel nem megbízható shutdown alatt.
    await cancel_all_orders_binance(
        api_key=api_key,
        api_secret=api_secret,
        symbol=symbol,
        environment=binance_env.name,
    )

    # Get final state
    state_snapshot = strategy.on_save() if hasattr(strategy, "on_save") else {}

    # Stop publisher
    await publisher.stop(reason=shutdown_reason, state_snapshot=state_snapshot)

    # Stop node (this should also trigger strategy.on_stop())
    print("Stopping trading node...")
    node.stop()
    await asyncio.sleep(2)
    node.dispose()

    print("✅ Shutdown complete")
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
