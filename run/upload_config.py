#!/usr/bin/env python3
"""
Custom Config Feltöltése MongoDB-be
===================================

Használat:
    # JSON fájlból
    python run/upload_config.py config.json

    # Interaktív mód (kérdésekkel)
    python run/upload_config.py --interactive

Példa JSON fájl (config.json):
{
    "strategy_id": "my_custom_strategy",
    "strategy_type": "bounce_scalper",
    "symbols": ["BTCUSDC", "ETHUSDC"],
    "parameters": {
        "trade_size_usdc": 10.0,
        "take_profit_pct": 1.5,
        "stop_loss_pct": 2.0
    }
}
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from persistence.config import MongoDBConfig
from persistence.config_loader import DEFAULT_CONFIGS, save_strategy_config


def load_from_json(filepath: str) -> dict:
    """JSON fájlból tölt be configot."""
    with open(filepath) as f:
        return json.load(f)


def interactive_config() -> dict:
    """Interaktív config létrehozás."""
    print("\n=== Custom Config Létrehozás ===\n")

    # Strategy ID
    strategy_id = input("Strategy ID (pl. my_btc_scalper): ").strip()
    if not strategy_id:
        print("❌ Strategy ID kötelező!")
        sys.exit(1)

    # Strategy type
    print(f"\nElérhető strategy típusok: {list(DEFAULT_CONFIGS.keys())}")
    strategy_type = input("Strategy type [bounce_scalper]: ").strip() or "bounce_scalper"

    if strategy_type not in DEFAULT_CONFIGS:
        print(f"❌ Ismeretlen strategy type: {strategy_type}")
        sys.exit(1)

    # Symbols
    symbols_input = input("\nSymbols (vesszővel elválasztva) [BTCUSDC,ETHUSDC,SOLUSDC]: ").strip()
    if symbols_input:
        symbols = [s.strip().upper() for s in symbols_input.split(",")]
    else:
        symbols = ["BTCUSDC", "ETHUSDC", "SOLUSDC"]

    # Parameters - default értékekkel
    defaults = DEFAULT_CONFIGS[strategy_type]["parameters"]

    print("\nParaméterek (Enter = default érték):\n")

    trade_size = input(f"  trade_size_usdc [{defaults['trade_size_usdc']}]: ").strip()
    trade_size = float(trade_size) if trade_size else defaults['trade_size_usdc']

    take_profit = input(f"  take_profit_pct [{defaults['take_profit_pct']}]: ").strip()
    take_profit = float(take_profit) if take_profit else defaults['take_profit_pct']

    stop_loss = input(f"  stop_loss_pct [{defaults['stop_loss_pct']}]: ").strip()
    stop_loss = float(stop_loss) if stop_loss else defaults['stop_loss_pct']

    max_positions = input(f"  max_positions_per_instrument [{defaults['max_positions_per_instrument']}]: ").strip()
    max_positions = int(max_positions) if max_positions else defaults['max_positions_per_instrument']

    ema_period = input(f"  ema_period [{defaults['ema_period']}]: ").strip()
    ema_period = int(ema_period) if ema_period else defaults['ema_period']

    atr_period = input(f"  atr_period [{defaults['atr_period']}]: ").strip()
    atr_period = int(atr_period) if atr_period else defaults['atr_period']

    entry_mult = input(f"  entry_atr_multiplier [{defaults['entry_atr_multiplier']}]: ").strip()
    entry_mult = float(entry_mult) if entry_mult else defaults['entry_atr_multiplier']

    cooldown = input(f"  cooldown_ticks [{defaults['cooldown_ticks']}]: ").strip()
    cooldown = int(cooldown) if cooldown else defaults['cooldown_ticks']

    min_balance = input(f"  min_free_balance_usdc [{defaults['min_free_balance_usdc']}]: ").strip()
    min_balance = float(min_balance) if min_balance else defaults['min_free_balance_usdc']

    config = {
        "strategy_id": strategy_id,
        "strategy_type": strategy_type,
        "symbols": symbols,
        "parameters": {
            "trade_size_usdc": trade_size,
            "max_positions_per_instrument": max_positions,
            "take_profit_pct": take_profit,
            "stop_loss_pct": stop_loss,
            "ema_period": ema_period,
            "atr_period": atr_period,
            "entry_atr_multiplier": entry_mult,
            "exit_atr_multiplier": None,
            "min_free_balance_usdc": min_balance,
            "cooldown_ticks": cooldown,
        }
    }

    return config


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nHasználat:")
        print("  python run/upload_config.py config.json")
        print("  python run/upload_config.py --interactive")
        return

    mongo_config = MongoDBConfig()
    if not mongo_config.connection_string:
        print("❌ MONGODB_URI not set!")
        print("   export MONGODB_URI='mongodb://...'")
        return

    arg = sys.argv[1]

    if arg == "--interactive":
        config = interactive_config()
    else:
        # JSON fájlból
        if not Path(arg).exists():
            print(f"❌ Fájl nem található: {arg}")
            return
        config = load_from_json(arg)

    # Validáció
    if "strategy_id" not in config:
        print("❌ Config-ban 'strategy_id' mező kötelező!")
        return

    # Feltöltés
    print(f"\n📤 Config feltöltése: {config['strategy_id']}")
    print(json.dumps(config, indent=2, default=str))

    confirm = input("\nFeltöltöd? (y/n): ").strip().lower()
    if confirm != "y":
        print("Megszakítva.")
        return

    if save_strategy_config(config, mongo_config):
        print(f"\n✅ Config feltöltve: {config['strategy_id']}")
    else:
        print("\n❌ Feltöltés sikertelen!")


if __name__ == "__main__":
    main()
