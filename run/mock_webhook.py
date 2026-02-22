#!/usr/bin/env python3
"""
Mock Webhook Szimulátor
=======================

Véletlenszerű trading eventeket küld a backend-nek teszteléshez.
Úgy viselkedik, mintha egy valódi trader bot futna.

Használat:
    export WEBHOOK_URL="http://localhost:3000/api/trading/webhook"
    export WEBHOOK_SECRET="your_secret"
    python run/mock_webhook.py

Vagy argumentumokkal:
    python run/mock_webhook.py --url http://localhost:3000/api/trading/webhook --secret your_secret
"""

import argparse
import asyncio
import os
import random
import uuid
from datetime import datetime, UTC
from typing import Any

import aiohttp

# ═══════════════════════════════════════════════════════════════════════════
# KONFIGURÁCIÓ
# ═══════════════════════════════════════════════════════════════════════════

SYMBOLS = ["BTCUSDC", "ETHUSDC", "SOLUSDC", "BNBUSDC"]
ORDER_SIDES = ["BUY", "SELL"]
ORDER_TYPES = ["MARKET", "LIMIT"]
POSITION_SIDES = ["LONG", "SHORT"]

# Árak (közelítő értékek)
PRICES = {
    "BTCUSDC": 95000.0,
    "ETHUSDC": 3200.0,
    "SOLUSDC": 180.0,
    "BNBUSDC": 650.0,
}


# ═══════════════════════════════════════════════════════════════════════════
# MOCK DATA GENERÁTOROK
# ═══════════════════════════════════════════════════════════════════════════

def generate_order() -> dict[str, Any]:
    """Generál egy véletlenszerű order eseményt."""
    symbol = random.choice(SYMBOLS)
    side = random.choice(ORDER_SIDES)
    order_type = random.choice(ORDER_TYPES)
    base_price = PRICES[symbol]
    price = base_price * random.uniform(0.99, 1.01)
    quantity = random.uniform(0.001, 0.1) if "BTC" in symbol else random.uniform(0.01, 1.0)

    return {
        "client_order_id": f"O-{uuid.uuid4().hex[:12].upper()}",
        "venue_order_id": str(random.randint(100000000, 999999999)),
        "instrument_id": f"{symbol}.BINANCE",
        "order_side": side,
        "order_type": order_type,
        "quantity": round(quantity, 6),
        "price": round(price, 2) if order_type == "LIMIT" else None,
        "status": "SUBMITTED",
        "submitted_at": datetime.now(UTC).isoformat(),
    }


def generate_order_update(order: dict) -> dict[str, Any]:
    """Generál egy order update eseményt."""
    statuses = ["ACCEPTED", "FILLED", "PARTIALLY_FILLED", "CANCELLED"]
    weights = [0.3, 0.5, 0.1, 0.1]
    new_status = random.choices(statuses, weights=weights)[0]

    return {
        "client_order_id": order["client_order_id"],
        "venue_order_id": order["venue_order_id"],
        "status": new_status,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def generate_fill(order: dict) -> dict[str, Any]:
    """Generál egy fill eseményt."""
    symbol = order["instrument_id"].split(".")[0]
    base_price = PRICES.get(symbol, 1000.0)
    fill_price = base_price * random.uniform(0.999, 1.001)

    return {
        "fill_id": f"F-{uuid.uuid4().hex[:12].upper()}",
        "client_order_id": order["client_order_id"],
        "venue_order_id": order["venue_order_id"],
        "instrument_id": order["instrument_id"],
        "order_side": order["order_side"],
        "quantity": order["quantity"],
        "price": round(fill_price, 2),
        "commission": round(order["quantity"] * fill_price * 0.001, 4),
        "commission_currency": "USDC",
        "liquidity_side": random.choice(["MAKER", "TAKER"]),
        "filled_at": datetime.now(UTC).isoformat(),
    }


def generate_position() -> dict[str, Any]:
    """Generál egy pozíció eseményt."""
    symbol = random.choice(SYMBOLS)
    side = random.choice(POSITION_SIDES)
    base_price = PRICES[symbol]
    entry_price = base_price * random.uniform(0.98, 1.02)
    quantity = random.uniform(0.001, 0.05) if "BTC" in symbol else random.uniform(0.01, 0.5)

    return {
        "position_id": f"P-{uuid.uuid4().hex[:12].upper()}",
        "instrument_id": f"{symbol}.BINANCE",
        "side": side,
        "quantity": round(quantity, 6),
        "avg_open_price": round(entry_price, 2),
        "unrealized_pnl": round(random.uniform(-50, 100), 2),
        "status": "OPEN",
        "opened_at": datetime.now(UTC).isoformat(),
    }


def generate_position_update(position: dict) -> dict[str, Any]:
    """Generál egy pozíció zárás eseményt."""
    symbol = position["instrument_id"].split(".")[0]
    base_price = PRICES.get(symbol, 1000.0)
    close_price = base_price * random.uniform(0.98, 1.02)

    entry_price = position["avg_open_price"]
    quantity = position["quantity"]

    if position["side"] == "LONG":
        pnl = (close_price - entry_price) * quantity
    else:
        pnl = (entry_price - close_price) * quantity

    pnl_pct = (pnl / (entry_price * quantity)) * 100

    return {
        "position_id": position["position_id"],
        "instrument_id": position["instrument_id"],
        "avg_close_price": round(close_price, 2),
        "realized_pnl": round(pnl, 2),
        "realized_pnl_pct": round(pnl_pct, 2),
        "status": "CLOSED",
        "exit_reason": random.choice(["TAKE_PROFIT", "STOP_LOSS", "SIGNAL"]),
        "closed_at": datetime.now(UTC).isoformat(),
    }


def generate_balance() -> dict[str, Any]:
    """Generál egy balance snapshot eseményt."""
    usdc_total = random.uniform(900, 1100)
    usdc_locked = random.uniform(0, usdc_total * 0.3)

    return {
        "balances": [
            {
                "currency": "USDC",
                "total": round(usdc_total, 2),
                "free": round(usdc_total - usdc_locked, 2),
                "locked": round(usdc_locked, 2),
            },
            {
                "currency": "BTC",
                "total": round(random.uniform(0, 0.01), 6),
                "free": round(random.uniform(0, 0.01), 6),
                "locked": 0.0,
            },
        ],
        "total_equity_usdc": round(usdc_total + random.uniform(-50, 50), 2),
        "open_positions_count": random.randint(0, 3),
        "timestamp": datetime.now(UTC).isoformat(),
    }


def generate_heartbeat(uptime_seconds: int) -> dict[str, Any]:
    """Generál egy heartbeat eseményt."""
    return {
        "status": "RUNNING",
        "uptime_seconds": uptime_seconds,
        "open_positions": random.randint(0, 3),
        "pending_orders": random.randint(0, 2),
        "last_trade_at": datetime.now(UTC).isoformat() if random.random() > 0.5 else None,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def generate_error() -> dict[str, Any]:
    """Generál egy hiba eseményt."""
    errors = [
        ("WARNING", "EXCHANGE", "Rate limit approaching"),
        ("WARNING", "STRATEGY", "Low balance, skipping trade"),
        ("ERROR", "EXCHANGE", "Order rejected: Insufficient balance"),
        ("ERROR", "NETWORK", "Connection timeout, retrying..."),
        ("INFO", "STRATEGY", "Cooldown active, waiting..."),
    ]
    level, source, message = random.choice(errors)

    return {
        "level": level,
        "source": source,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOK KÜLDŐ
# ═══════════════════════════════════════════════════════════════════════════

class MockWebhookSender:
    """Webhook események küldése a backend-nek."""

    def __init__(self, url: str, secret: str, strategy_id: str = "mock_strategy_001", verbose: bool = False):
        self.url = url
        self.secret = secret
        self.strategy_id = strategy_id
        self.session_id = str(uuid.uuid4())
        self.session: aiohttp.ClientSession | None = None
        self.sent_count = 0
        self.error_count = 0
        self.verbose = verbose

    async def start(self):
        """HTTP session indítása."""
        timeout = aiohttp.ClientTimeout(total=5)
        self.session = aiohttp.ClientSession(timeout=timeout)
        print(f"Mock webhook sender started")
        print(f"  URL: {self.url}")
        print(f"  Strategy ID: {self.strategy_id}")
        print(f"  Session ID: {self.session_id[:8]}...")
        print()

    async def stop(self):
        """HTTP session leállítása."""
        if self.session:
            await self.session.close()
        print(f"\nMock sender stopped. Sent: {self.sent_count}, Errors: {self.error_count}")

    async def send_event(self, event_type: str, data: dict) -> bool:
        """Egy webhook esemény küldése."""
        if not self.session:
            return False

        payload = {
            "event": event_type,
            "strategy_id": self.strategy_id,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        headers = {"Content-Type": "application/json"}
        if self.secret:
            headers["X-Webhook-Secret"] = self.secret

        try:
            async with self.session.post(self.url, json=payload, headers=headers) as response:
                self.sent_count += 1
                status_icon = "✓" if response.status < 400 else "✗"
                print(f"  {status_icon} [{response.status}] {event_type}: {self._summarize(event_type, data)}")

                # Verbose: teljes response body kiírása hiba esetén
                if self.verbose or response.status >= 400:
                    try:
                        body = await response.text()
                        if body:
                            print(f"      Response: {body[:500]}")
                    except:
                        pass

                # Verbose: payload kiírása
                if self.verbose:
                    import json
                    print(f"      Payload: {json.dumps(payload, default=str)[:500]}")

                return response.status < 400
        except Exception as e:
            self.error_count += 1
            print(f"  ✗ [ERR] {event_type}: {e}")
            return False

    def _get_collection(self, event_type: str) -> str:
        """Event type -> collection név."""
        mapping = {
            "orders": "orders",
            "order_update": "orders",
            "fills": "fills",
            "positions": "positions",
            "position_update": "positions",
            "balances": "balances",
            "heartbeat": "heartbeat",
            "errors": "errors",
        }
        return mapping.get(event_type, event_type)

    def _summarize(self, event_type: str, data: dict) -> str:
        """Rövid összefoglaló az eseményről."""
        if event_type == "orders":
            return f"{data.get('order_side')} {data.get('instrument_id')}"
        elif event_type == "order_update":
            return f"{data.get('client_order_id', '')[:12]} → {data.get('status')}"
        elif event_type == "fills":
            return f"{data.get('instrument_id')} @ {data.get('price')}"
        elif event_type == "positions":
            return f"{data.get('side')} {data.get('instrument_id')}"
        elif event_type == "position_update":
            return f"{data.get('position_id', '')[:12]} → {data.get('status')} ({data.get('realized_pnl')} USDC)"
        elif event_type == "balances":
            return f"Equity: {data.get('total_equity_usdc')} USDC"
        elif event_type == "heartbeat":
            return f"Uptime: {data.get('uptime_seconds')}s"
        elif event_type == "errors":
            return f"[{data.get('level')}] {data.get('message')}"
        return str(data)[:50]


# ═══════════════════════════════════════════════════════════════════════════
# SZIMULÁCIÓ
# ═══════════════════════════════════════════════════════════════════════════

async def run_simulation(sender: MockWebhookSender, duration_seconds: int = 60):
    """
    Futtat egy szimulációt ami véletlenszerű eventeket küld.

    Args:
        sender: Webhook küldő
        duration_seconds: Futás időtartama másodpercben
    """
    print(f"Starting simulation for {duration_seconds} seconds...")
    print("=" * 60)

    start_time = asyncio.get_event_loop().time()
    uptime = 0

    # Aktív pozíciók és orderek nyomon követése
    active_orders: list[dict] = []
    active_positions: list[dict] = []

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= duration_seconds:
            break

        uptime = int(elapsed)

        # Véletlenszerű esemény generálása
        event_type = random.choices(
            ["order", "position", "balance", "heartbeat", "error"],
            weights=[0.35, 0.25, 0.15, 0.15, 0.10],
        )[0]

        if event_type == "order":
            # Új order vagy meglévő frissítése
            if active_orders and random.random() > 0.4:
                # Order update vagy fill
                order = random.choice(active_orders)

                if random.random() > 0.3:
                    # Fill
                    fill = generate_fill(order)
                    await sender.send_event("fills", fill)

                    # Order update (FILLED)
                    update = generate_order_update(order)
                    update["status"] = "FILLED"
                    await sender.send_event("order_update", update)
                    active_orders.remove(order)
                else:
                    # Csak update
                    update = generate_order_update(order)
                    await sender.send_event("order_update", update)
                    if update["status"] in ["FILLED", "CANCELLED"]:
                        active_orders.remove(order)
            else:
                # Új order
                order = generate_order()
                await sender.send_event("orders", order)
                active_orders.append(order)

        elif event_type == "position":
            # Új pozíció vagy meglévő zárása
            if active_positions and random.random() > 0.5:
                # Pozíció zárás
                position = random.choice(active_positions)
                update = generate_position_update(position)
                await sender.send_event("position_update", update)
                active_positions.remove(position)
            else:
                # Új pozíció
                position = generate_position()
                await sender.send_event("positions", position)
                active_positions.append(position)

        elif event_type == "balance":
            balance = generate_balance()
            await sender.send_event("balances", balance)

        elif event_type == "heartbeat":
            heartbeat = generate_heartbeat(uptime)
            await sender.send_event("heartbeat", heartbeat)

        elif event_type == "error":
            error = generate_error()
            await sender.send_event("errors", error)

        # Várakozás a következő eseményig (0.5-3 másodperc)
        await asyncio.sleep(random.uniform(0.5, 3.0))

    print("=" * 60)
    print("Simulation completed!")


async def main():
    """Fő belépési pont."""
    parser = argparse.ArgumentParser(description="Mock webhook szimulátor")
    parser.add_argument("--url", default=os.environ.get("WEBHOOK_URL", ""), help="Webhook URL")
    parser.add_argument("--secret", default=os.environ.get("WEBHOOK_SECRET", ""), help="Webhook secret")
    parser.add_argument("--strategy-id", default="mock_strategy_001", help="Strategy ID")
    parser.add_argument("--duration", type=int, default=60, help="Szimuláció időtartama (másodperc)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Részletes kimenet (payload + response)")
    args = parser.parse_args()

    if not args.url:
        print("ERROR: WEBHOOK_URL nincs beállítva!")
        print()
        print("Használat:")
        print("  export WEBHOOK_URL='http://localhost:3000/api/trading/webhook'")
        print("  export WEBHOOK_SECRET='your_secret'")
        print("  python run/mock_webhook.py")
        print()
        print("Vagy:")
        print("  python run/mock_webhook.py --url http://localhost:3000/api/trading/webhook --secret your_secret")
        return

    sender = MockWebhookSender(args.url, args.secret, args.strategy_id, verbose=args.verbose)

    try:
        await sender.start()
        await run_simulation(sender, args.duration)
    except KeyboardInterrupt:
        print("\nMegszakítva...")
    finally:
        await sender.stop()


if __name__ == "__main__":
    asyncio.run(main())
