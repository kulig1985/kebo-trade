"""
MongoDB Persistence Layer
=========================

Általános persistence layer NautilusTrader stratégiákhoz.
PyMongo Async API-t használ (Motor deprecated 2026 májusában).

Komponensek:
    - MongoDBConfig: Konfiguráció dataclass
    - MongoDBPublisher: Aszinkron fire-and-forget publisher
    - MongoDBSyncService: Startup szinkronizáció (crash recovery)
"""

from persistence.config import MongoDBConfig
from persistence.config_loader import load_strategy_config, save_strategy_config
from persistence.publisher import MongoDBPublisher
from persistence.sync import MongoDBSyncService

__all__ = [
    "MongoDBConfig",
    "MongoDBPublisher",
    "MongoDBSyncService",
    "load_strategy_config",
    "save_strategy_config",
]
