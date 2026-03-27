"""
Strategy Config Management
==========================

Config feltöltése/listázása MongoDB-ben.

Használat:
    # Config feltöltése
    python run/manage_config.py upload bounce_scalper_live_001

    # Config listázása
    python run/manage_config.py list

    # Config letöltése
    python run/manage_config.py get bounce_scalper_live_001
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from persistence.config import MongoDBConfig
from persistence.config_loader import (
    DEFAULT_CONFIGS,
    list_strategy_configs,
    load_strategy_config,
    save_strategy_config,
)


def cmd_upload(strategy_id: str):
    """Default config feltöltése MongoDB-be."""
    mongo_config = MongoDBConfig()

    if not mongo_config.connection_string:
        print("❌ MONGODB_URI not set!")
        return

    # Strategy type kinyerése
    strategy_type = strategy_id.rsplit("_", 2)[0] if "_" in strategy_id else strategy_id

    if strategy_type not in DEFAULT_CONFIGS:
        print(f"❌ Unknown strategy type: {strategy_type}")
        print(f"   Available: {list(DEFAULT_CONFIGS.keys())}")
        return

    config = DEFAULT_CONFIGS[strategy_type].copy()
    config["strategy_id"] = strategy_id

    if save_strategy_config(config, mongo_config):
        print(f"✅ Config uploaded: {strategy_id}")
        print(json.dumps(config, indent=2, default=str))
    else:
        print("❌ Upload failed")


def cmd_list():
    """Összes config listázása."""
    mongo_config = MongoDBConfig()

    if not mongo_config.connection_string:
        print("❌ MONGODB_URI not set!")
        return

    configs = list_strategy_configs(mongo_config)

    if not configs:
        print("No configs found in MongoDB.")
        print("\nDefault configs available:")
        for name in DEFAULT_CONFIGS:
            print(f"  - {name}")
        return

    print(f"Found {len(configs)} config(s):\n")
    for cfg in configs:
        print(f"  • {cfg.get('strategy_id')}")
        print(f"    Type: {cfg.get('strategy_type')}")
        print(f"    Symbols: {cfg.get('symbols', [])}")
        print()


def cmd_get(strategy_id: str):
    """Config lekérése."""
    mongo_config = MongoDBConfig()

    if not mongo_config.connection_string:
        print("❌ MONGODB_URI not set!")
        return

    try:
        config = load_strategy_config(strategy_id, mongo_config)
        print(json.dumps(config, indent=2, default=str))
    except ValueError as e:
        print(f"❌ {e}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "upload" and len(sys.argv) >= 3:
        cmd_upload(sys.argv[2])
    elif cmd == "list":
        cmd_list()
    elif cmd == "get" and len(sys.argv) >= 3:
        cmd_get(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
