"""
MongoDB Konfiguráció
====================

Környezeti változók:
    MONGODB_URI: Connection string (KÖTELEZŐ!)
    MONGODB_ENABLED: "true"/"false" (default: true)
"""

import os
from dataclasses import dataclass, field


@dataclass
class MongoDBConfig:
    """MongoDB konfiguráció."""

    # Connection string - MONGODB_URI env var-ból
    connection_string: str = field(
        default_factory=lambda: os.environ.get("MONGODB_URI", "")
    )

    # Database neve
    database_name: str = "nautilus"

    # MongoDB engedélyezve
    enabled: bool = field(
        default_factory=lambda: os.environ.get("MONGODB_ENABLED", "true").lower() == "true"
    )

    # Queue beállítások
    queue_maxsize: int = 100000
    num_workers: int = 5

    # Időzítések
    balance_interval_seconds: float = 60.0
    heartbeat_interval_seconds: float = 30.0
    connect_timeout_ms: int = 5000
    server_selection_timeout_ms: int = 5000

    # Collection nevek
    orders_collection: str = "orders"
    fills_collection: str = "fills"
    positions_collection: str = "positions"
    balances_collection: str = "balances"
    heartbeat_collection: str = "heartbeat"
    sessions_collection: str = "sessions"
    errors_collection: str = "errors"
    config_collection: str = "strategy_configs"  # ÚJ: config collection
