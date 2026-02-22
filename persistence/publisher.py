"""
MongoDB Publisher
=================

Aszinkron, nem-blokkoló MongoDB publisher.
Fire-and-forget működés: a stratégia soha nem vár a DB írásokra.

PyMongo Async API-t használ (Motor deprecated 2026 májusában).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, UTC
from typing import Any, Callable

import aiohttp
from pymongo import AsyncMongoClient

from persistence.config import MongoDBConfig


logger = logging.getLogger(__name__)


class MongoDBPublisher:
    """
    Aszinkron MongoDB publisher fire-and-forget működéssel.

    A stratégia hívja a publish_* metódusokat, amelyek:
    1. Az adatot beteszi egy asyncio Queue-ba (nem blokkoló)
    2. Háttér worker-ek feldolgozzák és MongoDB-be írják

    Ha a queue megtelik, a legrégebbi események eldobódnak
    (inkább veszítsünk el adatot, mint blokkoljuk a stratégiát).
    """

    def __init__(
        self,
        config: MongoDBConfig,
        strategy_type: str,
        strategy_id: str,
        is_backtest: bool = False,
    ):
        """
        Publisher inicializálása.

        Args:
            config: MongoDB konfiguráció
            strategy_type: Stratégia típus (pl. "bounce_scalper")
            strategy_id: Egyedi stratégia azonosító (pl. "bounce_scalper_live_001")
            is_backtest: True ha backtest mód
        """
        self.config = config
        self.strategy_type = strategy_type
        self.strategy_id = strategy_id
        self.is_backtest = is_backtest
        self.session_id = str(uuid.uuid4())

        # Kapcsolat állapot
        self._client: AsyncMongoClient | None = None
        self._db: Any = None

        # Háttér feldolgozás
        self._queue: asyncio.Queue | None = None
        self._workers: list[asyncio.Task] = []
        self._running = False

        # Időzített task-ok
        self._balance_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None

        # Callback-ek (a stratégia állítja be)
        self._balance_callback: Callable[[], dict] | None = None
        self._heartbeat_callback: Callable[[], dict] | None = None

        # Indulási idő (uptime számításhoz)
        self._started_at: datetime | None = None

        # HTTP session (webhook-hoz)
        self._http_session: aiohttp.ClientSession | None = None

    # ═══════════════════════════════════════════════════════════════════════
    # LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════════

    async def start(self) -> None:
        """Publisher indítása - kapcsolat és workerek."""
        if not self.config.enabled:
            logger.info("MongoDB persistence disabled")
            return

        # Connection string ellenőrzése
        if not self.config.connection_string:
            logger.error(
                "MongoDB connection string not configured! "
                "Set MONGODB_URI environment variable."
            )
            return

        try:
            # PyMongo Async client létrehozása
            self._client = AsyncMongoClient(
                self.config.connection_string,
                connectTimeoutMS=self.config.connect_timeout_ms,
                serverSelectionTimeoutMS=self.config.server_selection_timeout_ms,
            )
            self._db = self._client[self.config.database_name]

            # Kapcsolat tesztelése
            await self._client.admin.command("ping")
            logger.info(f"MongoDB connected: {self.config.database_name}")

        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            self._client = None
            self._db = None
            return

        # Queue és workerek
        self._queue = asyncio.Queue(maxsize=self.config.queue_maxsize)

        for i in range(self.config.num_workers):
            worker = asyncio.create_task(
                self._worker_loop(i),
                name=f"mongo-worker-{i}"
            )
            self._workers.append(worker)

        self._running = True
        self._started_at = datetime.now(UTC)

        # HTTP session (webhook-hoz) - CSAK LIVE módban!
        # Backtest-ben nincs értelme webhook-ot küldeni (túl sok esemény)
        if self.config.webhook_url and not self.is_backtest:
            timeout = aiohttp.ClientTimeout(
                total=self.config.webhook_timeout_ms / 1000
            )
            self._http_session = aiohttp.ClientSession(timeout=timeout)
            logger.info(f"Webhook enabled: {self.config.webhook_url}")
        elif self.config.webhook_url and self.is_backtest:
            logger.info("Webhook disabled in backtest mode")

        # Session rögzítése
        await self._record_session_start()

        # Időzített task-ok indítása
        self._balance_task = asyncio.create_task(
            self._balance_loop(),
            name="mongo-balance"
        )
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name="mongo-heartbeat"
        )

        logger.info(
            f"MongoDB publisher started: {self.strategy_id} "
            f"(session: {self.session_id[:8]}...)"
        )

    async def stop(
        self,
        reason: str = "NORMAL",
        state_snapshot: dict | None = None,
    ) -> None:
        """
        Graceful shutdown.

        Args:
            reason: Leállás oka ("NORMAL", "ERROR", "CRASH_RECOVERY")
            state_snapshot: Stratégia állapot mentése
        """
        if not self._running:
            return

        self._running = False
        logger.info(f"MongoDB publisher stopping (reason: {reason})...")

        # Időzített task-ok leállítása
        for task in [self._balance_task, self._heartbeat_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Queue kiürítése (backtest-nél sok esemény lehet, 60 sec timeout)
        if self._queue is not None and not self._queue.empty():
            queue_size = self._queue.qsize()
            logger.info(f"Draining queue ({queue_size} events remaining)...")

            try:
                # Sentinel értékek a workereknek
                for _ in self._workers:
                    await self._queue.put(None)

                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=60.0
                )
                logger.info("Queue drained successfully")
            except asyncio.TimeoutError:
                logger.warning(f"Queue drain timeout, {self._queue.qsize()} events may be lost")

        # Workerek leállítása
        for worker in self._workers:
            if not worker.done():
                worker.cancel()

        # Session vége rögzítése
        await self._record_session_end(reason, state_snapshot)

        # HTTP session bezárása
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None

        # Kapcsolat bezárása
        if self._client is not None:
            await self._client.close()
            self._client = None

        logger.info("MongoDB publisher stopped")

    # ═══════════════════════════════════════════════════════════════════════
    # CALLBACK BEÁLLÍTÁS
    # ═══════════════════════════════════════════════════════════════════════

    def set_balance_callback(self, callback: Callable[[], dict]) -> None:
        """Balance adatokat szolgáltató callback beállítása."""
        self._balance_callback = callback

    def set_heartbeat_callback(self, callback: Callable[[], dict]) -> None:
        """Heartbeat adatokat szolgáltató callback beállítása."""
        self._heartbeat_callback = callback

    # ═══════════════════════════════════════════════════════════════════════
    # PUBLISH METÓDUSOK (fire-and-forget)
    # ═══════════════════════════════════════════════════════════════════════

    def publish_order(self, data: dict) -> None:
        """
        Order esemény publikálása.

        Args:
            data: Order adatok (client_order_id, instrument_id, stb.)
        """
        self._enqueue("orders", data)

    def publish_order_update(self, data: dict) -> None:
        """
        Order státusz frissítés publikálása.

        Args:
            data: Frissítés adatok (client_order_id, status, stb.)
        """
        self._enqueue("order_update", data)

    def publish_fill(self, data: dict) -> None:
        """
        Fill esemény publikálása.

        Args:
            data: Fill adatok (fill_id, client_order_id, price, qty, stb.)
        """
        self._enqueue("fills", data)

    def publish_position(self, data: dict) -> None:
        """
        Pozíció nyitás publikálása.

        Args:
            data: Pozíció adatok (position_id, instrument_id, side, stb.)
        """
        self._enqueue("positions", data)

    def publish_position_update(self, data: dict) -> None:
        """
        Pozíció frissítés publikálása.

        Args:
            data: Frissítés adatok (position_id, status, pnl, stb.)
        """
        self._enqueue("position_update", data)

    def publish_balance(self, data: dict) -> None:
        """
        Balance snapshot publikálása.

        Args:
            data: Balance adatok (balances lista, total_equity, stb.)
        """
        self._enqueue("balances", data)

    def publish_heartbeat(self, data: dict) -> None:
        """
        Heartbeat publikálása.

        Args:
            data: Heartbeat adatok (status, uptime, state, stb.)
        """
        self._enqueue("heartbeat", data)

    def publish_error(self, level: str, source: str, message: str) -> None:
        """
        Hiba/figyelmeztetés publikálása.

        Args:
            level: "INFO", "WARNING", "ERROR"
            source: Forrás ("STRATEGY", "EXCHANGE", "SYSTEM")
            message: Hibaüzenet
        """
        self._enqueue("errors", {
            "level": level,
            "source": source,
            "message": message,
        })

    # ═══════════════════════════════════════════════════════════════════════
    # BELSŐ METÓDUSOK
    # ═══════════════════════════════════════════════════════════════════════

    def _enqueue(self, event_type: str, data: dict) -> None:
        """
        Esemény berakása a queue-ba (nem blokkoló).

        Ha a queue tele van, eldobjuk az eseményt (stratégia nem blokkolódik).
        """
        if not self._running or not self._queue:
            return

        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(UTC),
        }

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Queue tele - eldobjuk, de logoljuk
            logger.warning(f"MongoDB queue full, dropping {event_type} event")

    async def _worker_loop(self, worker_id: int) -> None:
        """Háttér worker - queue feldolgozás és DB írás."""
        logger.debug(f"MongoDB worker {worker_id} started")

        while self._running or (self._queue and not self._queue.empty()):
            try:
                event = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )

                if event is None:
                    # Sentinel - shutdown
                    break

                await self._process_event(event)
                self._queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"MongoDB worker {worker_id} error: {e}")

        logger.debug(f"MongoDB worker {worker_id} stopped")

    async def _process_event(self, event: dict) -> None:
        """Esemény feldolgozása és MongoDB-be írása."""
        if self._db is None:
            return

        event_type = event["type"]
        data = event["data"]
        timestamp = event["timestamp"]

        # Közös mezők hozzáadása
        base_doc = {
            "strategy_type": self.strategy_type,
            "strategy_id": self.strategy_id,
            "is_backtest": self.is_backtest,
            "session_id": self.session_id,
        }

        try:
            if event_type == "orders":
                doc = {
                    **base_doc,
                    **data,
                    "submitted_at": timestamp,
                    "updated_at": timestamp,
                }
                await self._db[self.config.orders_collection].insert_one(doc)

            elif event_type == "order_update":
                # Order frissítése client_order_id alapján
                await self._db[self.config.orders_collection].update_one(
                    {
                        "strategy_id": self.strategy_id,
                        "client_order_id": data.get("client_order_id"),
                    },
                    {"$set": {**data, "updated_at": timestamp}}
                )

            elif event_type == "fills":
                doc = {
                    **base_doc,
                    **data,
                    "filled_at": timestamp,
                }
                await self._db[self.config.fills_collection].insert_one(doc)

            elif event_type == "positions":
                doc = {
                    **base_doc,
                    **data,
                    "opened_at": timestamp,
                }
                await self._db[self.config.positions_collection].insert_one(doc)

            elif event_type == "position_update":
                # Pozíció frissítése
                position_id = data.pop("position_id", None)
                if position_id:
                    update_data = {**data, "updated_at": timestamp}

                    # Ha closed_at flag True, cseréljük timestamp-re
                    if update_data.get("closed_at") is True:
                        update_data["closed_at"] = timestamp

                    await self._db[self.config.positions_collection].update_one(
                        {
                            "strategy_id": self.strategy_id,
                            "position_id": position_id,
                        },
                        {"$set": update_data}
                    )

            elif event_type == "balances":
                doc = {
                    **base_doc,
                    **data,
                    "timestamp": timestamp,
                }
                await self._db[self.config.balances_collection].insert_one(doc)

            elif event_type == "heartbeat":
                # Heartbeat - upsert (mindig csak 1 dokumentum/session)
                doc = {
                    **base_doc,
                    **data,
                    "timestamp": timestamp,
                }
                await self._db[self.config.heartbeat_collection].update_one(
                    {"session_id": self.session_id},
                    {"$set": doc},
                    upsert=True
                )

            elif event_type == "errors":
                doc = {
                    **base_doc,
                    **data,
                    "timestamp": timestamp,
                }
                await self._db[self.config.errors_collection].insert_one(doc)

            # Webhook notification (fire-and-forget)
            if self._http_session and self.config.webhook_url:
                asyncio.create_task(
                    self._send_webhook(event_type, base_doc, data, timestamp)
                )

        except Exception as e:
            logger.error(f"MongoDB write error ({event_type}): {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # WEBHOOK NOTIFICATION
    # ═══════════════════════════════════════════════════════════════════════

    async def _send_webhook(
        self,
        event_type: str,
        base_doc: dict,
        data: dict,
        timestamp: datetime,
    ) -> None:
        """
        Webhook notification küldése a backend-nek.

        Fire-and-forget: ha nem sikerül, csak logolunk, nem retry-olunk.
        """
        if self._http_session is None:
            return

        # Payload összeállítása
        payload = {
            "event": event_type,
            "collection": self._get_collection_name(event_type),
            "strategy_id": self.strategy_id,
            "session_id": self.session_id,
            "is_backtest": self.is_backtest,
            "timestamp": timestamp.isoformat(),
            "data": data,
        }

        # Headers (X-Webhook-Secret ha be van állítva)
        headers = {"Content-Type": "application/json"}
        if self.config.webhook_secret:
            headers["X-Webhook-Secret"] = self.config.webhook_secret

        try:
            async with self._http_session.post(
                self.config.webhook_url,
                json=payload,
                headers=headers,
            ) as response:
                if response.status >= 400:
                    logger.warning(
                        f"Webhook failed: {response.status} for {event_type}"
                    )
        except asyncio.TimeoutError:
            logger.debug(f"Webhook timeout for {event_type}")
        except Exception as e:
            logger.debug(f"Webhook error for {event_type}: {e}")

    def _get_collection_name(self, event_type: str) -> str:
        """Event type -> collection név."""
        mapping = {
            "orders": self.config.orders_collection,
            "order_update": self.config.orders_collection,
            "fills": self.config.fills_collection,
            "positions": self.config.positions_collection,
            "position_update": self.config.positions_collection,
            "balances": self.config.balances_collection,
            "heartbeat": self.config.heartbeat_collection,
            "errors": self.config.errors_collection,
        }
        return mapping.get(event_type, event_type)

    # ═══════════════════════════════════════════════════════════════════════
    # IDŐZÍTETT TASK-OK
    # ═══════════════════════════════════════════════════════════════════════

    async def _balance_loop(self) -> None:
        """Periodikus balance snapshot."""
        while self._running:
            try:
                await asyncio.sleep(self.config.balance_interval_seconds)

                if self._balance_callback:
                    data = self._balance_callback()
                    if data:
                        self.publish_balance(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Balance loop error: {e}")

    async def _heartbeat_loop(self) -> None:
        """Periodikus heartbeat."""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_seconds)

                uptime = 0.0
                if self._started_at:
                    uptime = (datetime.now(UTC) - self._started_at).total_seconds()

                data = {
                    "status": "RUNNING",
                    "uptime_seconds": uptime,
                }

                if self._heartbeat_callback:
                    extra = self._heartbeat_callback()
                    if extra:
                        data["state"] = extra

                self.publish_heartbeat(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # SESSION KEZELÉS
    # ═══════════════════════════════════════════════════════════════════════

    async def _record_session_start(self) -> None:
        """Session indulás rögzítése."""
        if self._db is None:
            return

        doc = {
            "session_id": self.session_id,
            "strategy_type": self.strategy_type,
            "strategy_id": self.strategy_id,
            "is_backtest": self.is_backtest,
            "started_at": datetime.now(UTC),
            "ended_at": None,
            "end_reason": None,
            "open_positions": [],
            "open_orders": [],
            "recovered_from": None,
            "state_snapshot": None,
        }

        try:
            await self._db[self.config.sessions_collection].insert_one(doc)
            logger.info(f"Session started: {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to record session start: {e}")

    async def _record_session_end(
        self,
        reason: str,
        state_snapshot: dict | None,
    ) -> None:
        """Session befejezés rögzítése."""
        if self._db is None:
            return

        try:
            await self._db[self.config.sessions_collection].update_one(
                {"session_id": self.session_id},
                {
                    "$set": {
                        "ended_at": datetime.now(UTC),
                        "end_reason": reason,
                        "state_snapshot": state_snapshot,
                    }
                }
            )
            logger.info(f"Session ended: {self.session_id} ({reason})")
        except Exception as e:
            logger.error(f"Failed to record session end: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # PROPERTY-K
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def db(self):
        """MongoDB database referencia (sync service-nek)."""
        return self._db

    @property
    def is_connected(self) -> bool:
        """Kapcsolat állapota."""
        return self._client is not None and self._running
