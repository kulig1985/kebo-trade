#!/usr/bin/env python3
"""
Cancel All Orders - Emergency Script
=====================================

Ez a script törli az ÖSSZES nyitott ordert a Binance-en.
Használd, ha a stratégia leállása után orderek maradtak bent.

Használat:
    BINANCE_API_KEY="..." BINANCE_API_SECRET="..." python run/cancel_all_orders.py

    Vagy TESTNET-en:
    BINANCE_API_KEY="..." BINANCE_API_SECRET="..." BINANCE_ENV=TESTNET python run/cancel_all_orders.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def cancel_all_orders():
    """Cancel all open orders using ccxt."""
    try:
        import ccxt.async_support as ccxt
    except ImportError:
        print("Installing ccxt...")
        os.system("pip install ccxt")
        import ccxt.async_support as ccxt

    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    env = os.environ.get("BINANCE_ENV", "TESTNET").upper()
    symbol = os.environ.get("SYMBOL", "SOL/USDC")

    if not api_key or not api_secret:
        print("ERROR: BINANCE_API_KEY and BINANCE_API_SECRET required!")
        return

    print("=" * 60)
    print("CANCEL ALL ORDERS")
    print("=" * 60)
    print(f"Environment: {env}")
    print(f"Symbol: {symbol}")
    print("=" * 60)

    # Create exchange instance
    exchange_params = {
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
        },
    }

    if env == "TESTNET":
        exchange_params["options"]["sandboxMode"] = True

    exchange = ccxt.binance(exchange_params)

    if env == "TESTNET":
        exchange.set_sandbox_mode(True)

    try:
        # Fetch open orders
        print("\nFetching open orders...")
        open_orders = await exchange.fetch_open_orders(symbol)

        if not open_orders:
            print("No open orders found!")
            return

        print(f"Found {len(open_orders)} open orders:")
        for order in open_orders:
            print(f"  - {order['id']}: {order['side']} {order['amount']} @ {order['price']}")

        # Cancel all orders
        print("\nCancelling orders...")
        cancelled = 0
        for order in open_orders:
            try:
                await exchange.cancel_order(order["id"], symbol)
                print(f"  Cancelled: {order['id']}")
                cancelled += 1
            except Exception as e:
                print(f"  Failed to cancel {order['id']}: {e}")

        print(f"\nCancelled {cancelled}/{len(open_orders)} orders")

        # Verify
        remaining = await exchange.fetch_open_orders(symbol)
        if remaining:
            print(f"\nWARNING: {len(remaining)} orders still open!")
        else:
            print("\nAll orders cancelled successfully!")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(cancel_all_orders())
