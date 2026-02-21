"""
Base Strategy - MongoDB Integrációval
======================================

Közös base class minden stratégiához.
MongoDB persistence és kézi beavatkozás kezelés.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nautilus_trader.model.events import (
    OrderAccepted,
    OrderCanceled,
    OrderFilled,
    OrderRejected,
    OrderSubmitted,
    PositionChanged,
    PositionClosed,
    PositionOpened,
)
from nautilus_trader.trading.strategy import Strategy

if TYPE_CHECKING:
    from persistence.publisher import MongoDBPublisher


class BaseStrategy(Strategy):
    """
    Base class MongoDB integrációval.

    Minden stratégia ebből származzon, hogy:
    - Order/fill/position események automatikusan MongoDB-be kerüljenek
    - Kézi beavatkozások (külső cancel/fill) érzékelhetők legyenek
    - Balance/heartbeat callback-ek működjenek
    """

    def __init__(self, config):
        """
        Base strategy inicializálása.

        Args:
            config: StrategyConfig leszármazott
        """
        super().__init__(config)

        # MongoDB publisher (opcionális - set_persistence() állítja be)
        self._mongo: MongoDBPublisher | None = None

        # Saját cancel kérések nyomon követése (kézi vs stratégia cancel megkülönböztetés)
        self._pending_cancels: set[str] = set()

    # ═══════════════════════════════════════════════════════════════════════
    # PERSISTENCE BEÁLLÍTÁS
    # ═══════════════════════════════════════════════════════════════════════

    def set_persistence(self, publisher: MongoDBPublisher) -> None:
        """
        Persistence komponens beállítása.

        Args:
            publisher: MongoDBPublisher instance
        """
        self._mongo = publisher
        publisher.set_balance_callback(self._get_balance_snapshot)
        publisher.set_heartbeat_callback(self._get_heartbeat_data)
        self.log.info("MongoDB persistence enabled")

    # ═══════════════════════════════════════════════════════════════════════
    # STATE PERSISTENCE (NautilusTrader beépített)
    # ═══════════════════════════════════════════════════════════════════════

    def on_save(self) -> dict:
        """
        Stratégia állapot mentése leálláskor.

        A NautilusTrader automatikusan hívja graceful shutdown-nál.
        Override a gyerek stratégiában a specifikus állapot mentéséhez.
        """
        return self._get_state_to_save()

    def on_load(self, state: dict) -> None:
        """
        Stratégia állapot visszaállítása induláskor.

        A NautilusTrader automatikusan hívja, ha van mentett állapot.
        Override a gyerek stratégiában a specifikus állapot visszaállításához.
        """
        self._restore_state(state)

    def _get_state_to_save(self) -> dict:
        """
        Mentendő állapot összeállítása.

        Override a gyerek osztályban.
        """
        return {}

    def _restore_state(self, state: dict) -> None:
        """
        Állapot visszaállítása.

        Override a gyerek osztályban.
        """
        pass

    # ═══════════════════════════════════════════════════════════════════════
    # ORDER ESEMÉNYEK
    # ═══════════════════════════════════════════════════════════════════════

    def on_order_submitted(self, event: OrderSubmitted) -> None:
        """
        Order elküldve a tőzsdére.

        Args:
            event: OrderSubmitted esemény
        """
        if self._mongo is None:
            return

        # Order objektum lekérése a cache-ből
        order = self.cache.order(event.client_order_id)
        if order is None:
            return

        self._mongo.publish_order({
            "client_order_id": str(event.client_order_id),
            "instrument_id": str(order.instrument_id),
            "order_side": str(order.side.name),
            "order_type": str(order.order_type.name),
            "quantity": float(order.quantity),
            "price": float(order.price) if hasattr(order, 'price') and order.price else None,
            "status": "SUBMITTED",
            "reduce_only": getattr(order, 'is_reduce_only', False),
            "ts_event": event.ts_event,
        })

    def on_order_accepted(self, event: OrderAccepted) -> None:
        """
        Order elfogadva a tőzsde által.

        Args:
            event: OrderAccepted esemény
        """
        if self._mongo is None:
            return

        self._mongo.publish_order_update({
            "client_order_id": str(event.client_order_id),
            "venue_order_id": str(event.venue_order_id) if event.venue_order_id else None,
            "status": "ACCEPTED",
        })

    def on_order_canceled(self, event: OrderCanceled) -> None:
        """
        Order törölve - lehet kézi beavatkozás is.

        Args:
            event: OrderCanceled esemény
        """
        client_order_id = str(event.client_order_id)

        # Ellenőrizzük, hogy mi küldtük-e a cancel-t
        is_external = client_order_id not in self._pending_cancels

        if is_external:
            self.log.warning(f"External cancel detected: {client_order_id}")
            self._handle_external_cancel(event)
        else:
            # Saját cancel - eltávolítjuk a pending listából
            self._pending_cancels.discard(client_order_id)

        # MongoDB-be írás
        if self._mongo is not None:
            self._mongo.publish_order_update({
                "client_order_id": client_order_id,
                "status": "CANCELED",
                "external_action": is_external,
            })

    def on_order_filled(self, event: OrderFilled) -> None:
        """
        Order teljesült.

        Args:
            event: OrderFilled esemény
        """
        if self._mongo is None:
            return

        commission = 0.0
        if event.commission:
            commission = float(event.commission.as_double())

        # Fill rögzítése
        self._mongo.publish_fill({
            "fill_id": str(event.trade_id) if event.trade_id else None,
            "client_order_id": str(event.client_order_id),
            "venue_order_id": str(event.venue_order_id) if event.venue_order_id else None,
            "instrument_id": str(event.instrument_id),
            "order_side": str(event.order_side.name),
            "quantity": float(event.last_qty),
            "price": float(event.last_px),
            "commission": commission,
            "liquidity_side": str(event.liquidity_side.name) if event.liquidity_side else None,
            "ts_event": event.ts_event,
        })

        # Order státusz frissítése
        self._mongo.publish_order_update({
            "client_order_id": str(event.client_order_id),
            "status": "FILLED",
        })

    def on_order_rejected(self, event: OrderRejected) -> None:
        """
        Order elutasítva.

        Args:
            event: OrderRejected esemény
        """
        self.log.warning(f"Order rejected: {event.client_order_id} - {event.reason}")

        if self._mongo is None:
            return

        self._mongo.publish_order_update({
            "client_order_id": str(event.client_order_id),
            "status": "REJECTED",
            "reason": str(event.reason),
        })
        self._mongo.publish_error(
            "WARNING",
            "EXCHANGE",
            f"Order rejected: {event.reason}"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # POZÍCIÓ ESEMÉNYEK
    # ═══════════════════════════════════════════════════════════════════════

    def on_event(self, event) -> None:
        """
        Általános esemény kezelés - pozíció események.

        Args:
            event: Bármilyen esemény
        """
        if isinstance(event, PositionOpened):
            self._handle_position_opened(event)
        elif isinstance(event, PositionClosed):
            self._handle_position_closed(event)
        elif isinstance(event, PositionChanged):
            self._handle_position_changed(event)

    def _handle_position_opened(self, event: PositionOpened) -> None:
        """
        Pozíció nyitás kezelése.

        Args:
            event: PositionOpened esemény
        """
        if self._mongo is None:
            return

        # Side meghatározása a signed quantity alapján
        side = "LONG" if event.signed_qty > 0 else "SHORT"

        self._mongo.publish_position({
            "position_id": str(event.position_id),
            "instrument_id": str(event.instrument_id),
            "side": side,
            "quantity": abs(float(event.signed_qty)),
            "avg_open_price": float(event.avg_px_open),
            "status": "OPEN",
            "ts_event": event.ts_event,
        })

    def _handle_position_closed(self, event: PositionClosed) -> None:
        """
        Pozíció zárás kezelése.

        Args:
            event: PositionClosed esemény
        """
        if self._mongo is None:
            return

        realized_pnl = 0.0
        if hasattr(event, 'realized_pnl') and event.realized_pnl:
            realized_pnl = float(event.realized_pnl.as_double())

        # Duration kiszámítása (ts_event nanosec-ben van)
        duration_ns = event.duration_ns if hasattr(event, 'duration_ns') else 0
        duration_seconds = duration_ns / 1_000_000_000 if duration_ns else None

        self._mongo.publish_position_update({
            "position_id": str(event.position_id),
            "avg_close_price": float(event.avg_px_close),
            "realized_pnl": realized_pnl,
            "status": "CLOSED",
            "closed_at": True,  # Flag - a publisher timestamp-eli
            "duration_seconds": duration_seconds,
            "ts_event": event.ts_event,
        })

    def _handle_position_changed(self, event: PositionChanged) -> None:
        """
        Pozíció módosulás kezelése (pl. részleges fill).

        Override a gyerek osztályban, ha szükséges.

        Args:
            event: PositionChanged esemény
        """
        pass

    # ═══════════════════════════════════════════════════════════════════════
    # KÉZI BEAVATKOZÁS KEZELÉS
    # ═══════════════════════════════════════════════════════════════════════

    def _handle_external_cancel(self, event: OrderCanceled) -> None:
        """
        Kézi order törlés kezelése.

        Override a gyerek osztályban a specifikus logikához.

        Args:
            event: OrderCanceled esemény
        """
        pass

    def cancel_order_tracked(self, order) -> None:
        """
        Order cancel, ami nyomon követhető (nem külső).

        Használd ezt a self.cancel_order() helyett, ha különbséget
        akarsz tenni a stratégia és kézi cancel között.

        Args:
            order: A törölendő order
        """
        self._pending_cancels.add(str(order.client_order_id))
        self.cancel_order(order)

    # ═══════════════════════════════════════════════════════════════════════
    # CALLBACK METÓDUSOK (publisher hívja periodikusan)
    # ═══════════════════════════════════════════════════════════════════════

    def _get_balance_snapshot(self) -> dict:
        """
        Balance adatok összeállítása a publisher számára.

        Override a gyerek osztályban a specifikus logikához.
        Alapértelmezetten üres dict (nincs balance adat).
        """
        return {}

    def _get_heartbeat_data(self) -> dict:
        """
        Heartbeat adatok összeállítása a publisher számára.

        Override a gyerek osztályban a specifikus állapot adatokhoz.
        Alapértelmezetten üres dict.
        """
        return {}
