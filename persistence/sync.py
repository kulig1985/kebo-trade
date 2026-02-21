"""
MongoDB Sync Service
====================

Startup szinkronizáció a NautilusTrader cache és MongoDB között.

Crash recovery:
    - NautilusTrader reconciliation helyreállítja a tőzsde állapotát
    - MongoDB-ben ELAVULT adatok maradhatnak (pl. OPEN pozíciók, amik már CLOSED)
    - Ez a service szinkronizálja a MongoDB-t a NautilusTrader cache-ből
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase


logger = logging.getLogger(__name__)


class MongoDBSyncService:
    """
    MongoDB szinkronizálás a NautilusTrader cache-ből.

    Induláskor (MIUTÁN a NautilusTrader reconciliation lefutott):
    1. Lezárja az előző (crashelt) session-t
    2. MongoDB pozíciókat szinkronizálja a cache-ből
    3. MongoDB ordereket szinkronizálja a cache-ből
    """

    def __init__(self, db: AsyncDatabase | None):
        """
        Sync service inicializálása.

        Args:
            db: MongoDB database referencia (publisher.db-ből)
        """
        self._db = db

    async def sync_on_startup(
        self,
        cache,
        strategy_id: str,
        session_id: str,
    ) -> dict:
        """
        Induláskor lefut - MongoDB szinkronizálás a NautilusTrader cache-ből.

        Args:
            cache: NautilusTrader Cache objektum
            strategy_id: Stratégia azonosító
            session_id: Új session azonosító

        Returns:
            Szinkronizálási statisztikák
        """
        if not self._db:
            logger.info("MongoDB sync skipped (not connected)")
            return {"skipped": True}

        logger.info(f"Starting MongoDB sync for {strategy_id}...")

        stats = {
            "previous_sessions_closed": 0,
            "positions_synced": 0,
            "orders_synced": 0,
        }

        try:
            # 1. Előző session(ök) lezárása
            stats["previous_sessions_closed"] = await self._close_previous_sessions(
                strategy_id, session_id
            )

            # 2. Pozíciók szinkronizálása
            stats["positions_synced"] = await self._sync_positions(
                cache, strategy_id
            )

            # 3. Orderek szinkronizálása
            stats["orders_synced"] = await self._sync_orders(
                cache, strategy_id
            )

            logger.info(
                f"MongoDB sync completed: "
                f"{stats['previous_sessions_closed']} sessions closed, "
                f"{stats['positions_synced']} positions synced, "
                f"{stats['orders_synced']} orders synced"
            )

        except Exception as e:
            logger.error(f"MongoDB sync failed: {e}")
            stats["error"] = str(e)

        return stats

    async def _close_previous_sessions(
        self,
        strategy_id: str,
        current_session_id: str,
    ) -> int:
        """
        Lezárja az előző (crashelt) session-öket.

        Returns:
            Lezárt session-ök száma
        """
        result = await self._db.sessions.update_many(
            {
                "strategy_id": strategy_id,
                "ended_at": None,
                "session_id": {"$ne": current_session_id},
            },
            {
                "$set": {
                    "ended_at": datetime.now(UTC),
                    "end_reason": "CRASH_RECOVERY",
                }
            }
        )

        if result.modified_count > 0:
            logger.info(
                f"Closed {result.modified_count} previous session(s) "
                f"(crash recovery)"
            )

        return result.modified_count

    async def _sync_positions(self, cache, strategy_id: str) -> int:
        """
        MongoDB pozíciók szinkronizálása a NautilusTrader cache-ből.

        Ha egy pozíció MongoDB-ben OPEN, de NautilusTrader-ben már nincs,
        akkor lezárjuk SYNC_RECOVERY státusszal.

        Returns:
            Szinkronizált (lezárt) pozíciók száma
        """
        # NautilusTrader-ben nyitott pozíciók ID-i
        nt_open_positions = set()
        for position in cache.positions_open():
            nt_open_positions.add(str(position.id))

        # MongoDB-ben OPEN státuszú pozíciók
        mongo_open_cursor = self._db.positions.find({
            "strategy_id": strategy_id,
            "status": "OPEN",
        })

        synced_count = 0
        async for pos in mongo_open_cursor:
            position_id = pos.get("position_id")

            if position_id and position_id not in nt_open_positions:
                # MongoDB-ben OPEN, de NautilusTrader-ben már nincs
                await self._db.positions.update_one(
                    {"_id": pos["_id"]},
                    {
                        "$set": {
                            "status": "CLOSED",
                            "exit_reason": "SYNC_RECOVERY",
                            "closed_at": datetime.now(UTC),
                            "updated_at": datetime.now(UTC),
                        }
                    }
                )
                synced_count += 1
                logger.info(f"Position synced (closed): {position_id}")

        return synced_count

    async def _sync_orders(self, cache, strategy_id: str) -> int:
        """
        MongoDB orderek szinkronizálása a NautilusTrader cache-ből.

        Ha egy order MongoDB-ben aktív (SUBMITTED, ACCEPTED), de
        NautilusTrader-ben már nincs, akkor lezárjuk SYNC_CLOSED státusszal.

        Returns:
            Szinkronizált (lezárt) orderek száma
        """
        # NautilusTrader-ben nyitott orderek ID-i
        nt_open_orders = set()
        for order in cache.orders_open():
            nt_open_orders.add(str(order.client_order_id))

        # MongoDB-ben aktív státuszú orderek
        mongo_open_cursor = self._db.orders.find({
            "strategy_id": strategy_id,
            "status": {"$in": ["SUBMITTED", "ACCEPTED", "PENDING"]},
        })

        synced_count = 0
        async for order in mongo_open_cursor:
            client_order_id = order.get("client_order_id")

            if client_order_id and client_order_id not in nt_open_orders:
                # MongoDB-ben aktív, de NautilusTrader-ben már nincs
                await self._db.orders.update_one(
                    {"_id": order["_id"]},
                    {
                        "$set": {
                            "status": "SYNC_CLOSED",
                            "updated_at": datetime.now(UTC),
                        }
                    }
                )
                synced_count += 1
                logger.info(f"Order synced (closed): {client_order_id}")

        return synced_count

    async def get_previous_session(
        self,
        strategy_id: str,
    ) -> dict | None:
        """
        Legutóbbi session lekérdezése (recovery információhoz).

        Args:
            strategy_id: Stratégia azonosító

        Returns:
            Session dokumentum vagy None
        """
        if not self._db:
            return None

        return await self._db.sessions.find_one(
            {"strategy_id": strategy_id},
            sort=[("started_at", -1)]
        )

    async def get_open_positions_from_db(
        self,
        strategy_id: str,
    ) -> list[dict]:
        """
        MongoDB-ben OPEN státuszú pozíciók lekérdezése.

        Args:
            strategy_id: Stratégia azonosító

        Returns:
            Pozíció dokumentumok listája
        """
        if not self._db:
            return []

        cursor = self._db.positions.find({
            "strategy_id": strategy_id,
            "status": "OPEN",
        })

        return await cursor.to_list(length=None)
