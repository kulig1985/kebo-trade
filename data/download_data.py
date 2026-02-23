#!/usr/bin/env python3
"""
Kebo Trade - Adat Letöltő Script
================================

Letölti a szükséges OHLCV adatokat Binance-ről CCXT-vel.

Futtatás:
    # Default (bounce scalper symbolok, 5m, bounce_data mappába)
    python data/download_data.py

    # Grid Strategy-hez (15m)
    python data/download_data.py --timeframe 15m --output grid_data --symbols BTC/USDC

    # Több symbol és timeframe
    python data/download_data.py -s BTC/USDC ETH/USDC -t 5m 15m 1h

    # Egyedi dátumok
    python data/download_data.py --start 2025-01-01 --end 2026-02-21

    # Összes paraméter
    python data/download_data.py \\
        --symbols BTC/USDC ETH/USDC SOL/USDC \\
        --timeframe 5m 15m \\
        --start 2025-11-01 \\
        --end 2026-02-21 \\
        --output bounce_data \\
        --exchange binance

    # Force újraletöltés (felülírja a meglévőket)
    python data/download_data.py --force

Szükséges csomag:
    pip install ccxt pandas
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd


# ============================================================================
# DEFAULT ÉRTÉKEK
# ============================================================================

DEFAULT_SYMBOLS = [
    "BTC/USDC",
    "ETH/USDC",
    "SOL/USDC",
    "ARB/USDC",
    "TIA/USDC",
    "ADA/USDC",
    "AVAX/USDC",
    "DOGE/USDC",
]

DEFAULT_TIMEFRAMES = ["5m"]
DEFAULT_START = "2025-11-01"
DEFAULT_END = "2026-02-21"
DEFAULT_OUTPUT = "bounce_data"
DEFAULT_EXCHANGE = "binance"


# ============================================================================
# LETÖLTŐ FUNKCIÓK
# ============================================================================


def parse_date(date_str: str) -> int:
    """Date string -> milliseconds timestamp"""
    # Ha nincs idő megadva, hozzáadjuk
    if " " not in date_str and "T" not in date_str:
        date_str = f"{date_str} 00:00:00"

    dt = datetime.fromisoformat(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def format_filename(symbol: str, timeframe: str, start: str, end: str) -> str:
    """Fájlnév generálás"""
    clean_symbol = symbol.replace("/", "")

    # Parse dates
    start_dt = datetime.fromisoformat(start) if " " not in start else datetime.fromisoformat(start.split()[0])
    end_dt = datetime.fromisoformat(end) if " " not in end else datetime.fromisoformat(end.split()[0])

    start_tag = start_dt.strftime("%Y%m%d")
    end_tag = end_dt.strftime("%Y%m%d")

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
    since_ms = parse_date(start_date)
    end_ms = parse_date(end_date)

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
    parser = argparse.ArgumentParser(
        description="Kebo Trade - OHLCV adat letöltő",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Példák:
  # Default beállításokkal
  python data/download_data.py

  # Grid Strategy-hez (BTC, 15m)
  python data/download_data.py -s BTC/USDC -t 15m -o grid_data

  # Több symbol és timeframe
  python data/download_data.py -s BTC/USDC ETH/USDC -t 5m 15m 1h

  # Egyedi dátumok
  python data/download_data.py --start 2025-01-01 --end 2026-02-21
        """
    )

    parser.add_argument(
        "-s", "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help=f"Trading párok (default: {', '.join(DEFAULT_SYMBOLS[:3])}...)"
    )

    parser.add_argument(
        "-t", "--timeframe",
        nargs="+",
        default=DEFAULT_TIMEFRAMES,
        help=f"Timeframe-ek: 1m, 5m, 15m, 1h, 4h, 1d (default: {DEFAULT_TIMEFRAMES})"
    )

    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help=f"Kezdő dátum YYYY-MM-DD (default: {DEFAULT_START})"
    )

    parser.add_argument(
        "--end",
        default=DEFAULT_END,
        help=f"Vég dátum YYYY-MM-DD (default: {DEFAULT_END})"
    )

    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Kimeneti mappa neve (data/ alatt) (default: {DEFAULT_OUTPUT})"
    )

    parser.add_argument(
        "-e", "--exchange",
        default=DEFAULT_EXCHANGE,
        help=f"Exchange (default: {DEFAULT_EXCHANGE})"
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Meglévő fájlok felülírása"
    )

    parser.add_argument(
        "--list-symbols",
        action="store_true",
        help="Listázza az elérhető symbol-okat és kilép"
    )

    args = parser.parse_args()

    # Exchange inicializálás
    try:
        exchange_class = getattr(ccxt, args.exchange)
        exchange = exchange_class({"enableRateLimit": True})
    except AttributeError:
        print(f"❌ Ismeretlen exchange: {args.exchange}")
        print(f"   Elérhető exchange-ek: binance, bybit, okx, kucoin, ...")
        return

    # List symbols mode
    if args.list_symbols:
        print(f"Elérhető USDC párok a {args.exchange}-on:")
        exchange.load_markets()
        usdc_pairs = [s for s in exchange.symbols if s.endswith("/USDC")]
        for pair in sorted(usdc_pairs)[:50]:
            print(f"  {pair}")
        if len(usdc_pairs) > 50:
            print(f"  ... és még {len(usdc_pairs) - 50} db")
        return

    # Output mappa
    data_dir = Path(__file__).parent / args.output
    data_dir.mkdir(parents=True, exist_ok=True)

    # Header
    print("=" * 70)
    print("KEBO TRADE - ADAT LETÖLTÉS")
    print("=" * 70)
    print(f"Exchange:    {args.exchange}")
    print(f"Párok:       {len(args.symbols)} db")
    for s in args.symbols:
        print(f"             - {s}")
    print(f"Timeframe:   {', '.join(args.timeframe)}")
    print(f"Időszak:     {args.start} → {args.end}")
    print(f"Kimeneti mappa: {data_dir}")
    print(f"Force mode:  {'IGEN' if args.force else 'NEM'}")
    print("=" * 70)

    print("\nExchange kapcsolódás...")
    print(f"✓ {args.exchange} kapcsolódva\n")

    # Letöltés
    total_files = len(args.symbols) * len(args.timeframe)
    current = 0
    downloaded = 0
    skipped = 0

    for symbol in args.symbols:
        print(f"\n{'─' * 50}")
        print(f"📥 {symbol}")
        print(f"{'─' * 50}")

        for tf in args.timeframe:
            current += 1
            filename = format_filename(symbol, tf, args.start, args.end)
            filepath = data_dir / filename

            # Ha már létezik és nincs force, skip
            if filepath.exists() and not args.force:
                existing_df = pd.read_csv(filepath)
                print(f"  [{current}/{total_files}] {tf}: SKIP (már létezik, {len(existing_df):,} rows)")
                skipped += 1
                continue

            print(f"  [{current}/{total_files}] {tf}: letöltés...")

            df = fetch_ohlcv(exchange, symbol, tf, args.start, args.end)

            if len(df) > 0:
                df.to_csv(filepath)
                print(f"      ✓ {len(df):,} rows mentve → {filename}")
                downloaded += 1
            else:
                print(f"      ⚠ Nincs adat!")

    # Összegzés
    print("\n" + "=" * 70)
    print("LETÖLTÉS KÉSZ!")
    print("=" * 70)
    print(f"\nÖsszegzés:")
    print(f"  Letöltve:  {downloaded} fájl")
    print(f"  Kihagyva:  {skipped} fájl (már létezett)")

    csv_files = list(data_dir.glob("*.csv"))
    if csv_files:
        print(f"\nMentett fájlok ({len(csv_files)} db):")
        for f in sorted(csv_files):
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  • {f.name} ({size_mb:.1f} MB)")

    print(f"\nMappa: {data_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()
