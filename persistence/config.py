"""
MongoDB Konfiguráció
====================

Központi konfiguráció a MongoDB persistence layer-hez.
"""

import os
from dataclasses import dataclass, field


@dataclass
class MongoDBConfig:
    """
    MongoDB kapcsolat és működési konfiguráció.

    Környezeti változók:
        MONGODB_URI: Teljes connection string (felülírja a többi beállítást)
        MONGODB_ENABLED: "true"/"false" - MongoDB engedélyezése

    Példa használat:
        config = MongoDBConfig()  # Alapértelmezett értékekkel
        config = MongoDBConfig(enabled=False)  # Kikapcsolva (backtest)
    """

    # ═══════════════════════════════════════════════════════════════════════
    # KAPCSOLAT
    # ═══════════════════════════════════════════════════════════════════════

    # MongoDB connection string
    # KÖTELEZŐ: MONGODB_URI környezeti változóból!
    # Példa: mongodb://user:password@host:27017/database?authSource=admin
    connection_string: str = field(
        default_factory=lambda: os.environ.get("MONGODB_URI", "")
    )

    # Adatbázis neve
    database_name: str = "nautilus"

    # ═══════════════════════════════════════════════════════════════════════
    # MŰKÖDÉS
    # ═══════════════════════════════════════════════════════════════════════

    # MongoDB engedélyezve (False = backtest módban kikapcsolható)
    enabled: bool = field(
        default_factory=lambda: os.environ.get("MONGODB_ENABLED", "true").lower() == "true"
    )

    # Háttér queue max mérete (ha megtelik, régebbi események eldobódnak)
    # Backtest-nél nagy méret kell (25k+ order)
    queue_maxsize: int = 100000

    # Háttér worker-ek száma (párhuzamos írók)
    num_workers: int = 5

    # ═══════════════════════════════════════════════════════════════════════
    # IDŐZÍTÉSEK
    # ═══════════════════════════════════════════════════════════════════════

    # Balance snapshot időköz (másodperc)
    balance_interval_seconds: float = 60.0

    # Heartbeat időköz (másodperc)
    heartbeat_interval_seconds: float = 30.0

    # Connection timeout (másodperc)
    connect_timeout_ms: int = 5000

    # Server selection timeout (másodperc)
    server_selection_timeout_ms: int = 5000

    # ═══════════════════════════════════════════════════════════════════════
    # COLLECTION NEVEK
    # ═══════════════════════════════════════════════════════════════════════

    orders_collection: str = "orders"
    fills_collection: str = "fills"
    positions_collection: str = "positions"
    balances_collection: str = "balances"
    heartbeat_collection: str = "heartbeat"
    sessions_collection: str = "sessions"
    errors_collection: str = "errors"
