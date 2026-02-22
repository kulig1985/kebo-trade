"""
Strategy Config Loader
======================

Stratégia konfigurációt tölt be MongoDB-ből.
Ha nincs DB-ben, default értékeket használ.
"""

import logging
from typing import Any

from pymongo import MongoClient

from persistence.config import MongoDBConfig

logger = logging.getLogger(__name__)


# Default stratégia konfigurációk
DEFAULT_CONFIGS = {
    "bounce_scalper": {
        "strategy_type": "bounce_scalper",
        "symbols": ["BTCUSDC", "ETHUSDC", "SOLUSDC"],
        "parameters": {
            "trade_size_usdc": 5.0,
            "max_positions_per_instrument": 1,
            "take_profit_pct": 1.0,
            "stop_loss_pct": 1.5,
            "ema_period": 20,
            "atr_period": 14,
            "entry_atr_multiplier": 0.8,
            "exit_atr_multiplier": None,
            "min_free_balance_usdc": 10.0,
            "cooldown_ticks": 10,
        },
    }
}


def load_strategy_config(
    strategy_id: str,
    mongo_config: MongoDBConfig | None = None,
) -> dict[str, Any]:
    """
    Stratégia konfiguráció betöltése.

    Prioritás:
    1. MongoDB config collection (ha elérhető)
    2. DEFAULT_CONFIGS (fallback)

    Args:
        strategy_id: Stratégia azonosító (pl. "bounce_scalper_live_001")
        mongo_config: MongoDB konfiguráció (opcionális)

    Returns:
        Stratégia konfiguráció dict
    """
    # Strategy type kinyerése az ID-ból (pl. "bounce_scalper_live_001" -> "bounce_scalper")
    strategy_type = strategy_id.rsplit("_", 2)[0] if "_" in strategy_id else strategy_id

    # Próbáljunk MongoDB-ből tölteni
    if mongo_config and mongo_config.enabled and mongo_config.connection_string:
        try:
            config = _load_from_mongodb(strategy_id, mongo_config)
            if config:
                logger.info(f"Config loaded from MongoDB: {strategy_id}")
                return config
        except Exception as e:
            logger.warning(f"Failed to load config from MongoDB: {e}")

    # Fallback: default config
    default = DEFAULT_CONFIGS.get(strategy_type, {}).copy()
    if default:
        default["strategy_id"] = strategy_id
        logger.info(f"Using default config for: {strategy_type}")
        return default

    # Nincs config
    raise ValueError(f"No config found for strategy: {strategy_id}")


def _load_from_mongodb(strategy_id: str, mongo_config: MongoDBConfig) -> dict | None:
    """MongoDB-ből tölt be konfigurációt."""
    client = MongoClient(
        mongo_config.connection_string,
        connectTimeoutMS=mongo_config.connect_timeout_ms,
        serverSelectionTimeoutMS=mongo_config.server_selection_timeout_ms,
    )

    try:
        db = client[mongo_config.database_name]
        collection = db[mongo_config.config_collection]

        # Keresés strategy_id alapján
        config = collection.find_one({"strategy_id": strategy_id})

        if config:
            # _id eltávolítása (nem serializálható)
            config.pop("_id", None)
            return config

        return None

    finally:
        client.close()


def save_strategy_config(
    config: dict,
    mongo_config: MongoDBConfig,
) -> bool:
    """
    Stratégia konfiguráció mentése MongoDB-be.

    Args:
        config: Konfiguráció dict (strategy_id kötelező mező!)
        mongo_config: MongoDB konfiguráció

    Returns:
        True ha sikeres
    """
    if not mongo_config.enabled or not mongo_config.connection_string:
        logger.warning("MongoDB not configured, cannot save config")
        return False

    strategy_id = config.get("strategy_id")
    if not strategy_id:
        raise ValueError("config must contain 'strategy_id'")

    client = MongoClient(
        mongo_config.connection_string,
        connectTimeoutMS=mongo_config.connect_timeout_ms,
        serverSelectionTimeoutMS=mongo_config.server_selection_timeout_ms,
    )

    try:
        db = client[mongo_config.database_name]
        collection = db[mongo_config.config_collection]

        # Upsert - ha létezik frissít, ha nem beszúr
        collection.update_one(
            {"strategy_id": strategy_id},
            {"$set": config},
            upsert=True,
        )

        logger.info(f"Config saved to MongoDB: {strategy_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False

    finally:
        client.close()


def list_strategy_configs(mongo_config: MongoDBConfig) -> list[dict]:
    """Összes stratégia konfiguráció listázása."""
    if not mongo_config.enabled or not mongo_config.connection_string:
        return []

    try:
        client = MongoClient(
            mongo_config.connection_string,
            connectTimeoutMS=mongo_config.connect_timeout_ms,
            serverSelectionTimeoutMS=mongo_config.server_selection_timeout_ms,
        )

        db = client[mongo_config.database_name]
        collection = db[mongo_config.config_collection]

        configs = []
        for doc in collection.find():
            doc.pop("_id", None)
            configs.append(doc)

        client.close()
        return configs

    except Exception as e:
        logger.error(f"Failed to list configs: {e}")
        return []
