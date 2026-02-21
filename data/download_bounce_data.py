#!/usr/bin/env python3
"""
Bounce Scalper Stratégia - Adat Letöltő Script
==============================================

Letölti a szükséges OHLCV adatokat Binance-ről CCXT-vel.

Futtatás:
    cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade
    python -m kebo_trade.data.download_bounce_data

Szükséges csomag:
    pip install ccxt pandas
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import ccxt
import pandas as pd


# ============================================================================
# KONFIGURÁCIÓ - SZÜKSÉG ESETÉN MÓDOSÍTSD
# ============================================================================

# Párok amiket letöltünk
SYMBOLS = [
    "BTC/USDC",
    "ETH/USDC",
    "SOL/USDC",
    "ARB/USDC",
    "TIA/USDC",
    "ADA/USDC",
    "AVAX/USDC",
    "DOGE/USDC",
]

# Timeframe-ek (módosítsd ha mást akarsz: "1m", "5m", "15m", "1h", stb.)
TIMEFRAMES = ["5m"]

# Időszak
START_DATE = "2025-01-01 00:00:00"
END_DATE = "2026-02-21 00:00:00"

# Exchange
EXCHANGE_ID = "binance"

# Adat mappa (ide menti a CSV-ket)
DATA_DIR = Path(__file__).parent / "bounce_data"


# ============================================================================
# LETÖLTŐ FUNKCIÓK
# ============================================================================

def parse_iso_utc(dt_str: str) -> int:
    """ISO datetime string -> milliseconds timestamp"""
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def format_filename(symbol: str, timeframe: str, start: str, end: str) -> str:
    """Fájlnév generálás"""
    clean_symbol = symbol.replace("/", "")
    start_tag = datetime.fromisoformat(start).strftime("%Y%m%d")
    end_tag = datetime.fromisoformat(end).strftime("%Y%m%d")
    return f"{clean_symbol}_{start_tag}_{end_tag}_{timeframe}.csv"


def fetch_ohlcv(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    limit_per_call: int = 1000,
) -> pd.DataFrame:
    """
    OHLCV adatok letöltése az exchange-ről.
    Automatikusan kezeli a pagination-t nagy adathalmazokhoz.
    """
    since_ms = parse_iso_utc(start_date)
    end_ms = parse_iso_utc(end_date)

    all_rows = []
    call_count = 0

    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(
                symbol,
                timeframe,
                since=since_ms,
                limit=limit_per_call
            )
            call_count += 1

            if not ohlcv:
                break

            all_rows.extend(ohlcv)
            last_ts = ohlcv[-1][0]

            # Progress
            if call_count % 10 == 0:
                last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
                print(f"      ... {len(all_rows):,} rows, utolsó: {last_dt.strftime('%Y-%m-%d %H:%M')}")

            # Elértük a végét?
            if last_ts >= end_ms:
                break

            # Nem haladtunk előre?
            if last_ts <= since_ms:
                break

            since_ms = last_ts + 1

        except Exception as e:
            print(f"      HIBA: {e}")
            break

    if not all_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(
        all_rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()

    # Szűrés end date-ig
    end_dt = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
    df = df[df.index <= end_dt]

    # Duplikátumok eltávolítása
    df = df[~df.index.duplicated(keep='first')]

    return df


def main():
    print("=" * 70)
    print("BOUNCE SCALPER - ADAT LETÖLTÉS")
    print("=" * 70)
    print(f"Exchange: {EXCHANGE_ID}")
    print(f"Párok: {len(SYMBOLS)} db")
    print(f"Timeframe-ek: {TIMEFRAMES}")
    print(f"Időszak: {START_DATE} → {END_DATE}")
    print(f"Mentés ide: {DATA_DIR}")
    print("=" * 70)

    # Mappa létrehozása
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Exchange inicializálás
    print("\nExchange kapcsolódás...")
    exchange_class = getattr(ccxt, EXCHANGE_ID)
    exchange = exchange_class({"enableRateLimit": True})
    print(f"✓ {EXCHANGE_ID} kapcsolódva\n")

    # Letöltés
    total_files = len(SYMBOLS) * len(TIMEFRAMES)
    current = 0

    for symbol in SYMBOLS:
        print(f"\n{'─' * 50}")
        print(f"📥 {symbol}")
        print(f"{'─' * 50}")

        for tf in TIMEFRAMES:
            current += 1
            filename = format_filename(symbol, tf, START_DATE, END_DATE)
            filepath = DATA_DIR / filename

            # Ha már létezik, skip
            if filepath.exists():
                existing_df = pd.read_csv(filepath)
                print(f"  [{current}/{total_files}] {tf}: SKIP (már létezik, {len(existing_df):,} rows)")
                continue

            print(f"  [{current}/{total_files}] {tf}: letöltés...")

            df = fetch_ohlcv(exchange, symbol, tf, START_DATE, END_DATE)

            if len(df) > 0:
                df.to_csv(filepath)
                print(f"      ✓ {len(df):,} rows mentve → {filename}")
            else:
                print(f"      ⚠ Nincs adat!")

    # Összegzés
    print("\n" + "=" * 70)
    print("LETÖLTÉS KÉSZ!")
    print("=" * 70)

    csv_files = list(DATA_DIR.glob("*.csv"))
    print(f"\nMentett fájlok ({len(csv_files)} db):")
    for f in sorted(csv_files):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  • {f.name} ({size_mb:.1f} MB)")

    print(f"\nMappa: {DATA_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
