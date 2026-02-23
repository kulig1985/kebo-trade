"""
Grid Trading Stratégia
======================

Geometrikus grid trading stratégia Binance Futures-re.
NautilusTrader alapú implementáció MongoDB persistence-el.

Fő jellemzők:
- Geometrikus grid szintek az aktuális ár körül
- Automatikus TP/SL minden pozícióhoz
- Volatilitás alapú grid szélesség adaptáció (ATR)
- Trend érzékelés (SMA cross)
- Dinamikus grid szint számítás
- Breakout, trailing stop és drawdown védelem
- Kézi beavatkozás érzékelése
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from nautilus_trader.model.data import Bar, BarType, QuoteTick, TradeTick
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price, Quantity

from strategies.base_strategy import BaseStrategy
from strategies.grid_strategy_config import GridStrategyConfig

if TYPE_CHECKING:
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


class SimpleMovingAverage:
    """Egyszerű mozgóátlag indikátor."""

    def __init__(self, period: int):
        self.period = period
        self.prices: deque[Decimal] = deque(maxlen=period)
        self.value: Decimal | None = None
        self.initialized = False

    def update(self, price: Decimal) -> None:
        """Új ár hozzáadása és átlag frissítése."""
        self.prices.append(price)
        if len(self.prices) == self.period:
            self.value = sum(self.prices) / Decimal(self.period)
            self.initialized = True


@dataclass
class GridTrade:
    """Egyetlen grid trade nyomon követése."""

    trade_id: str
    entry_order_id: str
    entry_price: Decimal
    entry_side: OrderSide
    quantity: Decimal
    tp_order_id: str | None = None
    sl_order_id: str | None = None
    grid_level: int = 0
    entry_time: float = 0.0
    profit_pct: float = 0.0
    closed: bool = False


@dataclass
class PerformanceTracker:
    """Trade teljesítmény követő."""

    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def win_rate(self) -> float:
        """Nyerési arány."""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    def add_trade(self, profit: Decimal) -> None:
        """Trade eredmény rögzítése."""
        self.total_trades += 1
        if profit > 0:
            self.winning_trades += 1
        self.total_pnl += profit


# ═══════════════════════════════════════════════════════════════════════════════
# GRID STRATEGY
# ═══════════════════════════════════════════════════════════════════════════════


class GridStrategy(BaseStrategy):
    """
    Geometrikus Grid Trading Stratégia.

    A stratégia az aktuális ár körül geometrikus eloszlású buy és sell
    ordereket helyez el. Minden teljesült grid orderhez automatikusan
    TP és SL order kerül beállításra.

    Működés:
    1. Induláskor a grid középpontja az aktuális ár
    2. Geometrikus szinteken buy (ár alatt) és sell (ár felett) orderek
    3. Ha egy order teljesül, TP/SL páros kerül elhelyezésre
    4. A grid újraközpontosodik, ha az ár jelentősen elmozdul
    5. Kockázatkezelési szabályok figyelése (drawdown, exposure, stb.)
    """

    def __init__(self, config: GridStrategyConfig) -> None:
        """
        Grid stratégia inicializálása.

        Args:
            config: GridStrategyConfig instance
        """
        super().__init__(config)

        # NautilusTrader-ben a self.config read-only, ezért _grid_config néven tároljuk
        self._grid_config: GridStrategyConfig = config
        self.instrument_id = config.instrument_id
        self.instrument: Instrument | None = None

        # ═══════════════════════════════════════════════════════════════════
        # GRID KONFIGURÁCIÓ (Decimal konverzió)
        # ═══════════════════════════════════════════════════════════════════

        self.grid_levels = config.grid_levels
        self.order_quantity = config.order_quantity
        self.order_size_usdc = config.order_size_usdc  # USDC alapú méretezés
        self.base_grid_offset = config.grid_offset_pct / Decimal("100")
        self.take_profit_pct = config.take_profit_pct / Decimal("100")
        self.stop_loss_pct = config.stop_loss_pct / Decimal("100")

        # Újraközpontosítás
        self.recenter_drift = config.recenter_drift_threshold_pct / Decimal("100")
        self.recenter_interval = config.recenter_interval_seconds

        # Kockázatkezelés
        self.breakout_threshold = config.breakout_threshold_pct / Decimal("100")
        self.trailing_stop_threshold = config.trailing_stop_threshold_pct / Decimal("100")
        self.max_drawdown_pct = config.max_drawdown_pct / Decimal("100")
        self.max_long_notional = config.max_long_notional
        self.max_short_notional = config.max_short_notional
        self.max_total_notional = config.max_total_notional

        # Funkció kapcsolók
        self.vol_adapt = config.volatility_adapt_offset
        self.enable_breakout_stop = config.enable_breakout_stop
        self.enable_exposure_limits = config.enable_exposure_limits
        self.enable_trailing_stop = config.enable_trailing_stop
        self.enable_max_drawdown = config.enable_max_drawdown
        self.enable_auto_resume = config.enable_auto_resume
        self.enable_dynamic_grid_levels = config.enable_dynamic_grid_levels

        # Resume beállítások
        self.resume_cooldown = config.resume_cooldown_minutes * 60
        self.resume_tolerance = config.resume_price_tolerance_pct / Decimal("100")

        # Dinamikus grid
        self.min_grid_levels = config.min_grid_levels
        self.max_grid_levels = config.max_grid_levels
        self.max_position_multiplier = config.max_position_multiplier
        self.asymmetric_profit_factor = config.asymmetric_profit_factor
        self.min_order_distance = config.min_order_distance_pct / Decimal("100")

        # ═══════════════════════════════════════════════════════════════════
        # ÁLLAPOT VÁLTOZÓK
        # ═══════════════════════════════════════════════════════════════════

        self.current_mid_price: Decimal | None = None
        self.lower_price: Decimal | None = None
        self.upper_price: Decimal | None = None
        self.original_lower: Decimal | None = None
        self.original_upper: Decimal | None = None
        self.highest_mid_since_start: Decimal = Decimal("0")
        self.starting_equity: Decimal | None = None

        self.last_recenter_time: float = 0.0
        self.last_pause_time: float = 0.0
        self.grid_active = False
        self.paused_due_to_risk = False

        self.effective_grid_levels: int = config.grid_levels

        # ═══════════════════════════════════════════════════════════════════
        # ORDER TRACKING
        # ═══════════════════════════════════════════════════════════════════

        # Aktív grid orderek (entry orderek)
        self.grid_order_ids: set[str] = set()

        # TP/SL orderek
        self.tp_sl_order_ids: set[str] = set()

        # Grid level minden orderhez
        self.grid_levels_by_order_id: dict[str, int] = {}

        # Aktív trade-ek
        self.grid_trades: dict[str, GridTrade] = {}

        # Aktuális aktív pozíció TP/SL-je
        self.active_tp_order_id: str | None = None
        self.active_sl_order_id: str | None = None

        # ═══════════════════════════════════════════════════════════════════
        # TECHNIKAI INDIKÁTOROK
        # ═══════════════════════════════════════════════════════════════════

        # ATR
        self.atr_period = config.atr_period
        self.atr_values: deque[Decimal] = deque(maxlen=self.atr_period)
        self.prev_close: Decimal | None = None

        # SMA (trend)
        self.sma_fast = SimpleMovingAverage(period=config.sma_fast_period)
        self.sma_slow = SimpleMovingAverage(period=config.sma_slow_period)

        # Volatilitás történelem
        self.volatility_values: deque[Decimal] = deque(maxlen=20)
        self.price_history: deque[Decimal] = deque(maxlen=50)

        # Trend állapot
        self.trend_strength: float = 0.0
        self.is_uptrend = False
        self.is_downtrend = False

        # ═══════════════════════════════════════════════════════════════════
        # TELJESÍTMÉNY KÖVETÉS
        # ═══════════════════════════════════════════════════════════════════

        self.performance = PerformanceTracker()

        # Pozíció limitek
        self.max_grid_position = self.order_quantity * Decimal(str(self.grid_levels))
        self.max_allowed_position = self.max_grid_position * self.max_position_multiplier

        # Bar counter (logging)
        self._bar_count = 0

    # ═══════════════════════════════════════════════════════════════════════════
    # LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════════════

    def on_start(self) -> None:
        """Stratégia indítása."""
        self.instrument = self.cache.instrument(self.instrument_id)
        if not self.instrument:
            self.log.error(f"Instrument not found: {self.instrument_id}")
            self.stop()
            return

        # 15 perces bar-ok a technikai indikátorokhoz
        bar_type = BarType.from_str(f"{self.instrument_id}-15-MINUTE-LAST-EXTERNAL")
        self.subscribe_bars(bar_type)

        # Quote és trade tick-ek az azonnali árhoz
        self.subscribe_quote_ticks(self.instrument_id)
        self.subscribe_trade_ticks(self.instrument_id)

        self.log.info(
            f"GridStrategy started for {self.instrument_id} | "
            f"Levels: {self.grid_levels}, Offset: {self.base_grid_offset * 100:.1f}%, "
            f"TP: {self.take_profit_pct * 100:.1f}%, SL: {self.stop_loss_pct * 100:.1f}%"
        )

    def on_stop(self) -> None:
        """
        Stratégia leállítása.

        FONTOS: Minden nyitott order törlésre kerül (grid és TP/SL egyaránt).
        A pozíció NEM kerül automatikusan zárásra - ezt a felhasználó dönti el.
        """
        self.log.info("GridStrategy stopping - canceling ALL orders...")

        # Grid inaktiválása
        self.grid_active = False

        # ÖSSZES nyitott order törlése (grid orderek ÉS TP/SL orderek)
        cancelled_count = 0
        working_orders = self.cache.orders_open(instrument_id=self.instrument_id)
        for order in working_orders:
            if order.is_open:
                try:
                    self.cancel_order(order)
                    cancelled_count += 1
                    self.log.debug(f"Cancelled order: {order.client_order_id}")
                except Exception as e:
                    self.log.warning(f"Failed to cancel order {order.client_order_id}: {e}")

        self.log.info(f"Cancelled {cancelled_count} orders")

        # Tracking reset
        self.grid_order_ids.clear()
        self.tp_sl_order_ids.clear()
        self.grid_levels_by_order_id.clear()
        self.active_tp_order_id = None
        self.active_sl_order_id = None

        # Pozíció info (NEM zárjuk automatikusan)
        position = self._get_position()
        if position and not position.is_closed:
            qty = abs(float(position.quantity))
            side = "LONG" if float(position.quantity) > 0 else "SHORT"
            self.log.warning(
                f"Open position remains: {side} {qty} - "
                f"Manual intervention may be required!"
            )

        # Trade-ek lezárása
        for trade in self.grid_trades.values():
            trade.closed = True
        self.grid_trades.clear()

        # Teljesítmény log
        if self.performance.total_trades > 0:
            self.log.info(
                f"Performance: Trades={self.performance.total_trades}, "
                f"Win Rate={self.performance.win_rate:.1%}, "
                f"Total P&L={self.performance.total_pnl:.4f}"
            )

        self.log.info("GridStrategy stopped - all orders cancelled")

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA HANDLERS
    # ═══════════════════════════════════════════════════════════════════════════

    def on_bar(self, bar: Bar) -> None:
        """Bar adat feldolgozása (15 perces)."""
        if self.prev_close is None:
            self.prev_close = Decimal(str(bar.close.as_double()))
            return

        close_price = Decimal(str(bar.close.as_double()))
        high_price = Decimal(str(bar.high.as_double()))
        low_price = Decimal(str(bar.low.as_double()))
        open_price = Decimal(str(bar.open.as_double()))

        # True Range számítás (ATR)
        tr = max(
            high_price - low_price,
            abs(high_price - self.prev_close),
            abs(low_price - self.prev_close),
        )
        self.atr_values.append(tr)
        self.prev_close = close_price

        # Ár történelem (trend)
        self.price_history.append(close_price)

        # SMA frissítés
        self.sma_fast.update(close_price)
        self.sma_slow.update(close_price)

        # Volatilitás
        if open_price > 0:
            vol = abs((close_price - open_price) / open_price)
            self.volatility_values.append(vol)
        else:
            self.volatility_values.append(Decimal("0.01"))

        # Trend érzékelés
        self._detect_trend()

        # Dinamikus grid szint számítás
        if self.enable_dynamic_grid_levels:
            self._calculate_dynamic_grid_levels()

        # Periodic status log
        self._bar_count += 1
        if self._bar_count % 20 == 0:
            self._log_status(close_price)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        """Quote tick feldolgozása."""
        bid = Decimal(str(tick.bid_price.as_double()))
        ask = Decimal(str(tick.ask_price.as_double()))
        mid = (bid + ask) / Decimal("2")

        # Periodikus állapot log és grid recovery check (minden ~30 másodpercben)
        self._tick_count = getattr(self, "_tick_count", 0) + 1
        if self._tick_count % 30 == 0:
            self._log_grid_state(mid)
            # Ellenőrizzük, hogy a grid konzisztens állapotban van-e
            self._check_grid_consistency()

        self._process_price_update(mid)

    def on_trade_tick(self, tick: TradeTick) -> None:
        """Trade tick feldolgozása."""
        if self.current_mid_price is None:
            price = Decimal(str(tick.price.as_double()))
            self._process_price_update(price)

    def _log_grid_state(self, current_price: Decimal) -> None:
        """Részletes állapot logolása."""
        position = self._get_position()

        # Valódi nyitott orderek száma (cache-ből)
        actual_open_orders = list(self.cache.orders_open(instrument_id=self.instrument_id))
        actual_count = len(actual_open_orders)

        # Pozíció info
        if position and not position.is_closed:
            pos_side = "LONG" if float(position.quantity) > 0 else "SHORT"
            pos_qty = abs(float(position.quantity))
            pos_info = f"{pos_side} {pos_qty}"
        else:
            pos_info = "NONE"

        # Grid/TP-SL állapot
        if len(self.grid_order_ids) > 0:
            mode = "GRID"
        elif self.active_tp_order_id or self.active_sl_order_id:
            mode = "TP/SL"
        elif self.paused_due_to_risk:
            mode = "PAUSED"
        else:
            mode = "IDLE"

        self.log.info(
            f"[STATE] Price={current_price:.4f} | Position={pos_info} | "
            f"Mode={mode} | GridOrders={len(self.grid_order_ids)} (actual={actual_count}) | "
            f"TP={self.active_tp_order_id is not None} SL={self.active_sl_order_id is not None} | "
            f"P&L={float(self.performance.total_pnl):.2f}"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # PRICE PROCESSING
    # ═══════════════════════════════════════════════════════════════════════════

    def _process_price_update(self, mid_price: Decimal) -> None:
        """Ár frissítés feldolgozása."""
        # Első ár - grid indítása
        if self.current_mid_price is None:
            self._center_grid(mid_price)
            return

        self.current_mid_price = mid_price

        # Legmagasabb ár követése
        if mid_price > self.highest_mid_since_start:
            self.highest_mid_since_start = mid_price

        # Auto-resume ellenőrzés
        if self.paused_due_to_risk and self.enable_auto_resume:
            if self._should_resume_grid(mid_price):
                self.log.info("Auto-resuming grid after cooldown")
                self.paused_due_to_risk = False
                self._center_grid(mid_price)
                return

        if self.paused_due_to_risk:
            return

        # Kockázat ellenőrzések
        if self.enable_breakout_stop and self.grid_active:
            if self._check_breakout(mid_price):
                self._flatten_and_pause(f"Breakout ±{self.breakout_threshold * 100:.0f}%")
                return

        if self.enable_exposure_limits:
            if not self._check_exposure_limits():
                self._flatten_and_pause("Exposure limits exceeded")
                return

        if self.enable_max_drawdown:
            if not self._check_drawdown():
                self._flatten_and_pause("Max drawdown exceeded")
                return

        if self.enable_trailing_stop and self.grid_active:
            if self._check_trailing_stop(mid_price):
                self._flatten_and_pause(
                    f"Trailing stop {self.trailing_stop_threshold * 100:.0f}% from high"
                )
                return

        # Grid újraközpontosítás
        now = time.time()
        if now - self.last_recenter_time > self.recenter_interval:
            if self.current_mid_price and self.current_mid_price > 0:
                # Közép ár a grid-ből
                grid_center = (self.lower_price + self.upper_price) / 2 if self.lower_price and self.upper_price else self.current_mid_price
                drift = abs(mid_price - grid_center) / grid_center
                if drift > self.recenter_drift:
                    self.log.info(f"Drift {drift * 100:.1f}% → Re-centering grid")
                    self.cancel_all_orders(self.instrument_id)
                    self.grid_order_ids.clear()
                    self._center_grid(mid_price)
                    self.last_recenter_time = now

    # ═══════════════════════════════════════════════════════════════════════════
    # GRID MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    def _center_grid(self, mid_price: Decimal) -> None:
        """Grid középre állítása az adott ár körül."""
        self.current_mid_price = mid_price

        if mid_price > self.highest_mid_since_start:
            self.highest_mid_since_start = mid_price

        # ATR alapú offset adaptáció
        offset = self.base_grid_offset
        if self.vol_adapt:
            offset *= self._get_atr_multiplier()

        half = offset / Decimal("2")
        self.lower_price = mid_price * (Decimal("1") - half)
        self.upper_price = mid_price * (Decimal("1") + half)

        if self.original_lower is None:
            self.original_lower = self.lower_price
            self.original_upper = self.upper_price

        # Starting equity mentése
        if self.starting_equity is None:
            self._save_starting_equity()

        # Előző grid törlése
        self.grid_order_ids.clear()
        self.grid_levels_by_order_id.clear()

        # Grid paraméterek logolása
        if self.instrument:
            self.log.info(
                f"Grid centered at {mid_price:.{self.instrument.price_precision}f} | "
                f"Range: {self.lower_price:.{self.instrument.price_precision}f} - "
                f"{self.upper_price:.{self.instrument.price_precision}f} "
                f"(±{half * 100:.2f}%{' ATR-adapted' if self.vol_adapt else ''})"
            )

        # Grid orderek elhelyezése
        self._place_grid_orders()
        self.grid_active = True
        self.paused_due_to_risk = False

    def _place_grid_orders(self) -> None:
        """Geometrikus grid orderek elhelyezése."""
        if not self.instrument:
            return

        qty = self._make_quantity()

        # Geometrikus arány
        ratio = (self.upper_price / self.lower_price) ** (
            Decimal("1") / Decimal(str(self.effective_grid_levels * 2))
        )

        self.grid_order_ids.clear()
        self.grid_levels_by_order_id.clear()

        orders_placed = 0

        for i in range(1, self.effective_grid_levels + 1):
            # BUY order (ár alatt)
            buy_price_raw = float(
                self.current_mid_price * (ratio ** -Decimal(str(i)))
            )
            buy_price = self._make_price(buy_price_raw)

            if self._is_price_valid(buy_price, is_buy=True):
                buy_order = self.order_factory.limit(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.BUY,
                    price=buy_price,
                    quantity=qty,
                    post_only=True,
                    time_in_force=TimeInForce.GTC,
                    reduce_only=False,
                )
                self.submit_order(buy_order)
                order_id = str(buy_order.client_order_id)
                self.grid_order_ids.add(order_id)
                self.grid_levels_by_order_id[order_id] = i
                orders_placed += 1

            # SELL order (ár felett)
            sell_price_raw = float(
                self.current_mid_price * (ratio ** Decimal(str(i)))
            )
            sell_price = self._make_price(sell_price_raw)

            if self._is_price_valid(sell_price, is_buy=False):
                sell_order = self.order_factory.limit(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    price=sell_price,
                    quantity=qty,
                    post_only=True,
                    time_in_force=TimeInForce.GTC,
                    reduce_only=False,
                )
                self.submit_order(sell_order)
                order_id = str(sell_order.client_order_id)
                self.grid_order_ids.add(order_id)
                self.grid_levels_by_order_id[order_id] = i
                orders_placed += 1

        self.log.info(
            f"Placed {orders_placed} grid orders "
            f"(effective levels: {self.effective_grid_levels})"
        )

    def _place_tp_sl_orders(
        self, entry_price: Decimal, side: OrderSide, quantity: Quantity
    ) -> tuple:
        """TP és SL orderek elhelyezése egy pozícióhoz."""
        if not self.instrument:
            return None, None

        try:
            # TP és SL árak számítása
            if side == OrderSide.BUY:
                tp_price_raw = float(entry_price * (Decimal("1") + self.take_profit_pct))
                sl_price_raw = float(entry_price * (Decimal("1") - self.stop_loss_pct))
                exit_side = OrderSide.SELL
            else:  # SELL
                tp_price_raw = float(entry_price * (Decimal("1") - self.take_profit_pct))
                sl_price_raw = float(entry_price * (Decimal("1") + self.stop_loss_pct))
                exit_side = OrderSide.BUY

            tp_price = self._make_price(tp_price_raw)
            sl_price = self._make_price(sl_price_raw)

            self.log.info(
                f"Placing TP/SL for {side.name} position: "
                f"Entry={entry_price:.4f}, TP={tp_price}, SL={sl_price}"
            )

            # Take Profit order (LIMIT)
            tp_order = self.order_factory.limit(
                instrument_id=self.instrument_id,
                order_side=exit_side,
                price=tp_price,
                quantity=quantity,
                time_in_force=TimeInForce.GTC,
                post_only=True,
                reduce_only=True,
            )

            # Stop Loss order (STOP MARKET)
            sl_order = self.order_factory.stop_market(
                instrument_id=self.instrument_id,
                order_side=exit_side,
                quantity=quantity,
                trigger_price=sl_price,
                time_in_force=TimeInForce.GTC,
                reduce_only=True,
            )

            self.submit_order(tp_order)
            self.submit_order(sl_order)

            self.active_tp_order_id = str(tp_order.client_order_id)
            self.active_sl_order_id = str(sl_order.client_order_id)

            self.tp_sl_order_ids.add(self.active_tp_order_id)
            self.tp_sl_order_ids.add(self.active_sl_order_id)

            return tp_order, sl_order

        except Exception as e:
            self.log.error(f"Error placing TP/SL: {e}")
            return None, None

    def on_order_filled(self, event) -> None:
        """
        Order fill esemény kezelése.

        Grid működési logika:
        1. Grid order fill → ELŐSZÖR töröljük a többi grid ordert
        2. Majd TP/SL ordereket helyezünk el → átváltunk TP/SL módba
        3. TP vagy SL fill → újraközpontosítjuk a gridet
        """
        # Base class kezelés
        super().on_order_filled(event)

        order_id = str(event.client_order_id)
        order = self.cache.order(event.client_order_id)
        if not order:
            return

        # ═══════════════════════════════════════════════════════════════════
        # GRID ORDER FILL - Pozíció nyitás, átváltás TP/SL módba
        # ═══════════════════════════════════════════════════════════════════
        if order_id in self.grid_order_ids:
            self.grid_order_ids.discard(order_id)
            grid_level = self.grid_levels_by_order_id.get(order_id, 0)

            self.log.info(
                f"GRID ORDER FILLED: {order.side.name} at {order.price} "
                f"(level {grid_level}) → Switching to TP/SL mode"
            )

            # FONTOS: ELŐSZÖR töröljük a többi grid ordert
            self._cancel_all_grid_orders()

            # Ha már van aktív TP/SL, nem helyezünk el újat
            if self.active_tp_order_id or self.active_sl_order_id:
                self.log.warning(
                    "TP/SL already active - this should not happen in single position mode"
                )
                return

            # Pozíció quantity meghatározása
            position = self._get_position()
            if position and not position.is_closed:
                qty = Quantity(
                    value=float(abs(position.quantity)),
                    precision=self.instrument.size_precision,
                )
            else:
                qty = self._make_quantity()

            # TP/SL elhelyezése
            entry_price = Decimal(str(order.price.as_double()))
            tp_order, sl_order = self._place_tp_sl_orders(entry_price, order.side, qty)

            if tp_order and sl_order:
                # Trade rögzítése
                trade = GridTrade(
                    trade_id=f"grid_{int(time.time() * 1000)}",
                    entry_order_id=order_id,
                    entry_price=entry_price,
                    entry_side=order.side,
                    quantity=Decimal(str(qty)),
                    tp_order_id=str(tp_order.client_order_id),
                    sl_order_id=str(sl_order.client_order_id),
                    grid_level=grid_level,
                    entry_time=time.time(),
                    profit_pct=float(self.take_profit_pct * 100),
                )
                self.grid_trades[trade.trade_id] = trade

                self.log.info(
                    f"TP/SL mode active: TP at {tp_order.price}, "
                    f"SL at {sl_order.trigger_price}"
                )
            return

        # ═══════════════════════════════════════════════════════════════════
        # TP FILL - Take Profit elérve, grid újraindítás
        # ═══════════════════════════════════════════════════════════════════
        if order_id == self.active_tp_order_id:
            self.log.info(f"TAKE PROFIT FILLED at {order.price} → Re-centering grid")
            self._handle_position_close("TP")
            return

        # ═══════════════════════════════════════════════════════════════════
        # SL FILL - Stop Loss kiütötte, grid újraindítás
        # ═══════════════════════════════════════════════════════════════════
        if order_id == self.active_sl_order_id:
            # Stop market ordernek trigger_price van, nem price
            trigger_price = getattr(order, 'trigger_price', None) or getattr(order, 'price', None)
            self.log.warning(f"STOP LOSS TRIGGERED at {trigger_price} → Re-centering grid")
            self._handle_position_close("SL")
            return

        # ═══════════════════════════════════════════════════════════════════
        # EGYÉB TP/SL ORDER - valószínűleg kézi beavatkozás
        # ═══════════════════════════════════════════════════════════════════
        if order_id in self.tp_sl_order_ids:
            self.log.info(f"TP/SL order filled: {order_id}")
            self.tp_sl_order_ids.discard(order_id)

    def _cancel_all_grid_orders(self) -> None:
        """
        Összes grid order törlése.

        Ez a metódus akkor hívódik, amikor egy grid order teljesül és
        pozíció nyílik. Ilyenkor az összes többi grid ordert törölni kell
        és átváltunk TP/SL módba.
        """
        cancelled_count = 0
        working_orders = self.cache.orders_open(instrument_id=self.instrument_id)

        for order in working_orders:
            order_id = str(order.client_order_id)
            # Csak grid ordereket töröljük, TP/SL-eket nem
            if order.is_open and order_id in self.grid_order_ids:
                try:
                    self.cancel_order(order)
                    cancelled_count += 1
                except Exception as e:
                    self.log.warning(f"Failed to cancel grid order {order_id}: {e}")

        self.grid_order_ids.clear()
        self.grid_levels_by_order_id.clear()

        if cancelled_count > 0:
            self.log.info(
                f"Cancelled {cancelled_count} grid orders → switched to TP/SL mode"
            )

    def _handle_position_close(self, reason: str) -> None:
        """
        Pozíció zárás kezelése és grid újraindítása.

        Ez a metódus hívódik, amikor TP vagy SL teljesül.
        Törli az ellentétes ordert és újraközpontosítja a gridet.
        """
        from nautilus_trader.model.identifiers import ClientOrderId

        self.log.info(f"Position closed ({reason}), cleaning up and re-centering grid...")

        # Ellentétes order törlése
        if reason == "TP" and self.active_sl_order_id:
            sl_order = self.cache.order(ClientOrderId(self.active_sl_order_id))
            if sl_order and sl_order.is_open:
                try:
                    self.cancel_order(order=sl_order)
                    self.log.debug(f"Cancelled SL order: {self.active_sl_order_id}")
                except Exception as e:
                    self.log.warning(f"Failed to cancel SL order: {e}")

        elif reason == "SL" and self.active_tp_order_id:
            tp_order = self.cache.order(ClientOrderId(self.active_tp_order_id))
            if tp_order and tp_order.is_open:
                try:
                    self.cancel_order(order=tp_order)
                    self.log.debug(f"Cancelled TP order: {self.active_tp_order_id}")
                except Exception as e:
                    self.log.warning(f"Failed to cancel TP order: {e}")

        # TP/SL tracking reset
        if self.active_tp_order_id:
            self.tp_sl_order_ids.discard(self.active_tp_order_id)
        if self.active_sl_order_id:
            self.tp_sl_order_ids.discard(self.active_sl_order_id)

        self.active_tp_order_id = None
        self.active_sl_order_id = None

        # Trade-ek lezárása és teljesítmény rögzítése
        for trade in self.grid_trades.values():
            if not trade.closed:
                trade.closed = True
                # Profit rögzítése (egyszerűsített)
                if reason == "TP":
                    profit = trade.entry_price * self.take_profit_pct * trade.quantity
                    self.performance.add_trade(profit)
                    self.log.info(f"Trade closed with PROFIT: +{profit:.4f} USDC")
                else:  # SL
                    loss = trade.entry_price * self.stop_loss_pct * trade.quantity * Decimal("-1")
                    self.performance.add_trade(loss)
                    self.log.info(f"Trade closed with LOSS: {loss:.4f} USDC")

        # Grid újraközpontosítás
        if self.current_mid_price and not self.paused_due_to_risk:
            self.log.info(f"Re-centering grid at price {self.current_mid_price:.4f}")
            self._center_grid(self.current_mid_price)
        else:
            self.log.warning("Cannot re-center grid: no price or paused due to risk")

    # ═══════════════════════════════════════════════════════════════════════════
    # RISK MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_breakout(self, mid_price: Decimal) -> bool:
        """Breakout ellenőrzés."""
        if not self.lower_price or not self.upper_price:
            return False

        lower_bound = self.lower_price * (Decimal("1") - self.breakout_threshold)
        upper_bound = self.upper_price * (Decimal("1") + self.breakout_threshold)

        return mid_price < lower_bound or mid_price > upper_bound

    def _check_trailing_stop(self, mid_price: Decimal) -> bool:
        """Trailing stop ellenőrzés."""
        if self.highest_mid_since_start <= 0:
            return False

        trail_low = self.highest_mid_since_start * (
            Decimal("1") - self.trailing_stop_threshold
        )
        return mid_price < trail_low

    def _check_exposure_limits(self) -> bool:
        """Kitettség limit ellenőrzés."""
        if not self.grid_active or not self.current_mid_price:
            return True

        long_n, short_n = self._get_current_position_notional()
        total_n = long_n + short_n

        if (
            long_n > self.max_long_notional
            or short_n > self.max_short_notional
            or total_n > self.max_total_notional
        ):
            self.log.error(
                f"Exposure breach: Long={long_n}, Short={short_n}, Total={total_n}"
            )
            return False

        return True

    def _check_drawdown(self) -> bool:
        """Maximum drawdown ellenőrzés."""
        if not self.starting_equity:
            return True

        account = self.cache.account_for_venue(Venue("BINANCE"))
        if not account:
            return True

        try:
            # USDC balance
            balances = account.balances()
            current_total = Decimal("0")
            for currency, balance in balances.items():
                if str(currency) == "USDC":
                    current_total = Decimal(str(balance.total.as_double()))
                    break

            threshold = self.starting_equity * (Decimal("1") - self.max_drawdown_pct)

            if current_total < threshold:
                self.log.error(
                    f"Max drawdown breached: {current_total} < {threshold}"
                )
                return False

        except Exception as e:
            self.log.warning(f"Drawdown check error: {e}")

        return True

    def _get_current_position_notional(self) -> tuple[Decimal, Decimal]:
        """Aktuális pozíció notional értékek."""
        if not self.current_mid_price:
            return Decimal("0"), Decimal("0")

        long_n = short_n = Decimal("0")

        position = self._get_position()
        if position and not position.is_closed:
            qty = abs(float(position.quantity))
            notional = Decimal(str(qty * float(self.current_mid_price)))

            if float(position.quantity) > 0:
                long_n = notional
            else:
                short_n = notional

        return long_n, short_n

    def _flatten_and_pause(self, reason: str) -> None:
        """Pozíciók zárása és grid szüneteltetése."""
        if self.paused_due_to_risk:
            return

        self.log.warning(f"SAFETY TRIGGER: {reason} → Flattening and pausing")

        # Összes order törlése
        self.cancel_all_orders(self.instrument_id)

        self.grid_order_ids.clear()
        self.tp_sl_order_ids.clear()
        self.grid_levels_by_order_id.clear()

        # Pozíció zárása
        self.close_all_positions(self.instrument_id)

        # Trade-ek lezárása
        for trade in self.grid_trades.values():
            trade.closed = True

        self.grid_active = False
        self.paused_due_to_risk = True
        self.last_pause_time = time.time()

    def _should_resume_grid(self, mid_price: Decimal) -> bool:
        """Resume feltétel ellenőrzés."""
        if time.time() - self.last_pause_time < self.resume_cooldown:
            return False

        if not self.original_lower or not self.original_upper:
            return False

        return (
            mid_price > self.original_lower * (Decimal("1") - self.resume_tolerance)
            and mid_price < self.original_upper * (Decimal("1") + self.resume_tolerance)
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # TECHNICAL INDICATORS
    # ═══════════════════════════════════════════════════════════════════════════

    def _detect_trend(self) -> None:
        """Trend érzékelés SMA és price action alapján."""
        if len(self.price_history) < 20:
            return

        recent_prices = list(self.price_history)
        if len(recent_prices) < 10:
            return

        # Árváltozás számítása
        oldest_price = recent_prices[0]
        newest_price = recent_prices[-1]
        price_change_pct = (newest_price - oldest_price) / oldest_price

        # SMA cross
        if self.sma_fast.initialized and self.sma_slow.initialized:
            if self.sma_fast.value > self.sma_slow.value:
                self.is_uptrend = True
                self.is_downtrend = False
            else:
                self.is_uptrend = False
                self.is_downtrend = True

        # Trend erősség
        self.trend_strength = abs(float(price_change_pct)) * 100

    def _calculate_dynamic_grid_levels(self) -> None:
        """Dinamikus grid szint számítás."""
        if not self.current_mid_price or len(self.volatility_values) < 5:
            return

        avg_volatility = sum(self.volatility_values) / len(self.volatility_values)
        base_levels = self.grid_levels

        # Volatilitás alapú korrekció
        if avg_volatility > Decimal("0.03"):  # Magas volatilitás
            adjustment = max(Decimal("0.5"), Decimal("1") - (avg_volatility / Decimal("0.05")))
            adjusted = int(base_levels * float(adjustment))
        elif avg_volatility < Decimal("0.01"):  # Alacsony volatilitás
            adjustment = min(Decimal("1.5"), Decimal("1") + (Decimal("0.01") / avg_volatility))
            adjusted = int(base_levels * float(adjustment))
        else:
            adjusted = base_levels

        # Trend alapú korrekció
        if self.trend_strength > 4:  # Erős trend
            adjusted = max(self.min_grid_levels, adjusted // 2)
        elif self.trend_strength > 2:  # Közepes trend
            adjusted = max(self.min_grid_levels, int(adjusted * 2 // 3))

        # Limitek
        new_levels = max(self.min_grid_levels, min(self.max_grid_levels, adjusted))

        if new_levels != self.effective_grid_levels:
            self.log.info(
                f"Dynamic grid adjustment: {self.effective_grid_levels} -> {new_levels} "
                f"(Vol: {avg_volatility * 100:.1f}%, Trend: {self.trend_strength:.1f}%)"
            )
            self.effective_grid_levels = new_levels

    def _get_atr_multiplier(self) -> Decimal:
        """ATR alapú volatilitás szorzó."""
        if not self.atr_values or not self.current_mid_price:
            return Decimal("1")

        if len(self.atr_values) < 5:
            return Decimal("1")

        current_atr = sum(self.atr_values) / len(self.atr_values)
        atr_percent = float(current_atr) / float(self.current_mid_price)

        # Normalizálás 0.7 - 1.8 tartományba
        return min(max(Decimal(str(atr_percent / 0.01)), Decimal("0.7")), Decimal("1.8"))

    # ═══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_position(self):
        """Aktuális pozíció lekérése az instrumentumhoz."""
        positions = self.cache.positions(instrument_id=self.instrument_id)
        for pos in positions:
            if not pos.is_closed:
                return pos
        return None

    def _make_price(self, raw_price: float) -> Price:
        """Price objektum létrehozása megfelelő precizitással."""
        return Price(
            self.instrument.make_price(raw_price),
            self.instrument.price_precision,
        )

    def _make_quantity(self) -> Quantity:
        """
        Quantity objektum létrehozása megfelelő precizitással.

        Ha order_size_usdc meg van adva, akkor az aktuális ár alapján
        számítja a quantity-t: qty = order_size_usdc / current_price
        """
        if self.order_size_usdc and self.order_size_usdc > 0 and self.current_mid_price:
            # USDC alapú méretezés
            calculated_qty = self.order_size_usdc / self.current_mid_price
            qty = Quantity(
                value=float(calculated_qty),
                precision=self.instrument.size_precision,
            )
        else:
            # Hagyományos BASE currency alapú méretezés
            qty = Quantity(
                value=float(self.order_quantity),
                precision=self.instrument.size_precision,
            )

        if qty < self.instrument.min_quantity:
            self.log.warning(
                f"Quantity {qty} below min {self.instrument.min_quantity}, adjusting"
            )
            qty = self.instrument.min_quantity

        return qty

    def _is_price_valid(self, price: Price, is_buy: bool) -> bool:
        """Order ár validálás."""
        if not self.current_mid_price:
            return True

        price_val = Decimal(str(price.as_double()))
        distance_pct = abs(price_val - self.current_mid_price) / self.current_mid_price

        # Buy ordernek ár alatt kell lennie
        if is_buy and price_val >= self.current_mid_price:
            return False

        # Sell ordernek ár felett kell lennie
        if not is_buy and price_val <= self.current_mid_price:
            return False

        # Minimum távolság
        return distance_pct >= self.min_order_distance

    def _save_starting_equity(self) -> None:
        """Kezdő equity mentése."""
        account = self.cache.account_for_venue(Venue("BINANCE"))
        if account:
            try:
                balances = account.balances()
                for currency, balance in balances.items():
                    if str(currency) == "USDC":
                        self.starting_equity = Decimal(str(balance.total.as_double()))
                        self.log.info(f"Starting equity: {self.starting_equity} USDC")
                        break
            except Exception as e:
                self.log.error(f"Failed to get starting equity: {e}")

    def _log_status(self, price: Decimal) -> None:
        """Periodikus státusz log."""
        position = self._get_position()
        pos_info = "No position"
        if position and not position.is_closed:
            side = "LONG" if float(position.quantity) > 0 else "SHORT"
            pos_info = f"{side} {abs(position.quantity)}"

        self.log.info(
            f"[{self.instrument_id.symbol}] Bar #{self._bar_count} | "
            f"Price: {price:.2f} | {pos_info} | "
            f"Grid: {'ACTIVE' if self.grid_active else 'PAUSED'} | "
            f"Levels: {self.effective_grid_levels} | "
            f"Trend: {'UP' if self.is_uptrend else 'DOWN'} ({self.trend_strength:.1f}%)"
        )

    def _handle_external_cancel(self, event) -> None:
        """
        Kézi order törlés kezelése.

        Ha valaki a Binance felületen törli a TP vagy SL ordert,
        ellenőrizzük az állapotot és szükség esetén újraindítjuk a gridet.
        """
        order_id = str(event.client_order_id)

        # TP order kézzel törölve
        if order_id == self.active_tp_order_id:
            self.log.warning(f"EXTERNAL CANCEL: TP order {order_id} cancelled externally!")
            self.active_tp_order_id = None
            self.tp_sl_order_ids.discard(order_id)
            self._check_and_recover_grid_state()

        # SL order kézzel törölve
        elif order_id == self.active_sl_order_id:
            self.log.warning(f"EXTERNAL CANCEL: SL order {order_id} cancelled externally!")
            self.active_sl_order_id = None
            self.tp_sl_order_ids.discard(order_id)
            self._check_and_recover_grid_state()

        # Grid order kézzel törölve
        elif order_id in self.grid_order_ids:
            self.log.info(f"External cancel of grid order: {order_id}")
            self.grid_order_ids.discard(order_id)
            if order_id in self.grid_levels_by_order_id:
                del self.grid_levels_by_order_id[order_id]

    def _check_and_recover_grid_state(self) -> None:
        """
        Ellenőrzi az aktuális állapotot és szükség esetén újraindítja a gridet.

        Hívódik amikor:
        - Kézi order törlés történik
        - TP/SL teljesül
        """
        position = self._get_position()
        has_position = position and not position.is_closed

        # Van-e még aktív TP/SL?
        has_tp_sl = self.active_tp_order_id is not None or self.active_sl_order_id is not None

        self.log.info(
            f"Grid state check: position={has_position}, "
            f"tp_sl_active={has_tp_sl}, grid_orders={len(self.grid_order_ids)}"
        )

        if has_position:
            # Van pozíció - kellene TP/SL
            if not has_tp_sl:
                self.log.warning(
                    "Position exists but no TP/SL orders! "
                    "Manual intervention required or close position manually."
                )
                # Opcionális: újra TP/SL elhelyezése
                # self._place_tp_sl_for_existing_position()
        else:
            # Nincs pozíció
            if has_tp_sl:
                # Törölni kell a TP/SL-eket
                self.log.info("No position but TP/SL exists - cancelling orphaned orders")
                self._cancel_orphaned_tp_sl()

            # Ha nincs grid order, újraindítjuk
            if len(self.grid_order_ids) == 0 and self.current_mid_price:
                self.log.info("No position and no grid orders - re-centering grid")
                self._center_grid(self.current_mid_price)

    def _cancel_orphaned_tp_sl(self) -> None:
        """Árva TP/SL orderek törlése (nincs hozzá pozíció)."""
        from nautilus_trader.model.identifiers import ClientOrderId

        if self.active_tp_order_id:
            try:
                tp_order = self.cache.order(ClientOrderId(self.active_tp_order_id))
                if tp_order and tp_order.is_open:
                    self.cancel_order(tp_order)
                    self.log.info(f"Cancelled orphaned TP order: {self.active_tp_order_id}")
            except Exception as e:
                self.log.warning(f"Failed to cancel orphaned TP: {e}")
            self.active_tp_order_id = None

        if self.active_sl_order_id:
            try:
                sl_order = self.cache.order(ClientOrderId(self.active_sl_order_id))
                if sl_order and sl_order.is_open:
                    self.cancel_order(sl_order)
                    self.log.info(f"Cancelled orphaned SL order: {self.active_sl_order_id}")
            except Exception as e:
                self.log.warning(f"Failed to cancel orphaned SL: {e}")
            self.active_sl_order_id = None

        self.tp_sl_order_ids.clear()

    def _check_grid_consistency(self) -> None:
        """
        Periodikus grid konzisztencia ellenőrzés.

        Ez a metódus minden ~30 tick-enként lefut és ellenőrzi:
        1. Ha van pozíció, de nincs TP/SL → FIGYELMEZTETÉS
        2. Ha nincs pozíció és nincs grid order → GRID ÚJRAINDÍTÁS
        3. Ha a tárolt grid orderek már nem léteznek → TISZTÍTÁS

        Ez kezeli azt az esetet is, amikor valaki kézzel törli az ÖSSZES ordert.
        """
        if self.paused_due_to_risk:
            return

        position = self._get_position()
        has_position = position and not position.is_closed

        # Valódi nyitott orderek száma (cache-ből)
        actual_open_orders = list(self.cache.orders_open(instrument_id=self.instrument_id))
        actual_grid_orders = [o for o in actual_open_orders if str(o.client_order_id) in self.grid_order_ids]
        actual_tp_sl_orders = []

        if self.active_tp_order_id:
            for o in actual_open_orders:
                if str(o.client_order_id) == self.active_tp_order_id:
                    actual_tp_sl_orders.append(o)
        if self.active_sl_order_id:
            for o in actual_open_orders:
                if str(o.client_order_id) == self.active_sl_order_id:
                    actual_tp_sl_orders.append(o)

        # Tisztítás: ha a tárolt order ID-k már nem léteznek
        actual_order_ids = {str(o.client_order_id) for o in actual_open_orders}
        stale_grid_orders = self.grid_order_ids - actual_order_ids
        if stale_grid_orders:
            self.log.debug(f"Removing {len(stale_grid_orders)} stale grid order IDs from tracking")
            self.grid_order_ids -= stale_grid_orders

        # TP/SL tisztítás
        if self.active_tp_order_id and self.active_tp_order_id not in actual_order_ids:
            self.log.info(f"TP order {self.active_tp_order_id} no longer exists - clearing")
            self.tp_sl_order_ids.discard(self.active_tp_order_id)
            self.active_tp_order_id = None

        if self.active_sl_order_id and self.active_sl_order_id not in actual_order_ids:
            self.log.info(f"SL order {self.active_sl_order_id} no longer exists - clearing")
            self.tp_sl_order_ids.discard(self.active_sl_order_id)
            self.active_sl_order_id = None

        # ESET 1: Van pozíció, de nincs TP/SL
        if has_position and not self.active_tp_order_id and not self.active_sl_order_id:
            qty = abs(float(position.quantity))
            side = "LONG" if float(position.quantity) > 0 else "SHORT"
            self.log.warning(
                f"[INCONSISTENT] Position exists ({side} {qty}) but no TP/SL orders! "
                f"Manual intervention may be needed."
            )

        # ESET 2: Nincs pozíció, nincs grid order → újraindítás
        if not has_position and len(self.grid_order_ids) == 0:
            # Ha van árva TP/SL, töröljük
            if self.active_tp_order_id or self.active_sl_order_id:
                self.log.info("No position but orphaned TP/SL exists - cleaning up")
                self._cancel_orphaned_tp_sl()

            # Grid újraindítás
            if self.current_mid_price and self.grid_active:
                self.log.info(
                    f"[RECOVERY] No position and no grid orders - re-centering grid at {self.current_mid_price:.4f}"
                )
                self._center_grid(self.current_mid_price)

    # ═══════════════════════════════════════════════════════════════════════════
    # STATE PERSISTENCE (MongoDB)
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_state_to_save(self) -> dict:
        """Mentendő állapot összeállítása."""
        return {
            "grid_active": self.grid_active,
            "paused_due_to_risk": self.paused_due_to_risk,
            "effective_grid_levels": self.effective_grid_levels,
            "current_mid_price": str(self.current_mid_price) if self.current_mid_price else None,
            "lower_price": str(self.lower_price) if self.lower_price else None,
            "upper_price": str(self.upper_price) if self.upper_price else None,
            "highest_mid_since_start": str(self.highest_mid_since_start),
            "starting_equity": str(self.starting_equity) if self.starting_equity else None,
            "bar_count": self._bar_count,
            "performance": {
                "total_trades": self.performance.total_trades,
                "winning_trades": self.performance.winning_trades,
                "total_pnl": str(self.performance.total_pnl),
            },
        }

    def _restore_state(self, state: dict) -> None:
        """Állapot visszaállítása."""
        self.grid_active = state.get("grid_active", False)
        self.paused_due_to_risk = state.get("paused_due_to_risk", False)
        self.effective_grid_levels = state.get("effective_grid_levels", self.grid_levels)
        self._bar_count = state.get("bar_count", 0)

        if state.get("current_mid_price"):
            self.current_mid_price = Decimal(state["current_mid_price"])
        if state.get("lower_price"):
            self.lower_price = Decimal(state["lower_price"])
        if state.get("upper_price"):
            self.upper_price = Decimal(state["upper_price"])
        if state.get("highest_mid_since_start"):
            self.highest_mid_since_start = Decimal(state["highest_mid_since_start"])
        if state.get("starting_equity"):
            self.starting_equity = Decimal(state["starting_equity"])

        perf = state.get("performance", {})
        self.performance.total_trades = perf.get("total_trades", 0)
        self.performance.winning_trades = perf.get("winning_trades", 0)
        if perf.get("total_pnl"):
            self.performance.total_pnl = Decimal(perf["total_pnl"])

        self.log.info(f"State restored: grid_active={self.grid_active}, bars={self._bar_count}")

    # ═══════════════════════════════════════════════════════════════════════════
    # CALLBACKS (MongoDB)
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_balance_snapshot(self) -> dict:
        """Balance snapshot a MongoDB-hez."""
        account = self.cache.account_for_venue(Venue("BINANCE"))
        if not account:
            return {}

        balances = []
        total_usdc = Decimal("0")

        try:
            for currency, balance in account.balances().items():
                total = float(balance.total.as_double())
                free = float(balance.free.as_double())
                locked = float(balance.locked.as_double())

                balances.append({
                    "currency": str(currency),
                    "total": total,
                    "free": free,
                    "locked": locked,
                })

                if str(currency) == "USDC":
                    total_usdc = Decimal(str(total))

        except Exception as e:
            self.log.error(f"Balance snapshot error: {e}")
            return {}

        position = self._get_position()
        open_positions = 0
        if position and not position.is_closed:
            open_positions = 1

        return {
            "balances": balances,
            "total_equity_usdc": float(total_usdc),
            "open_positions_count": open_positions,
        }

    def _get_heartbeat_data(self) -> dict:
        """Heartbeat data a MongoDB-hez."""
        position = self._get_position()
        pos_info = None
        if position and not position.is_closed:
            pos_info = {
                "side": "LONG" if float(position.quantity) > 0 else "SHORT",
                "quantity": float(abs(position.quantity)),
            }

        return {
            "grid_active": self.grid_active,
            "paused_due_to_risk": self.paused_due_to_risk,
            "effective_grid_levels": self.effective_grid_levels,
            "current_mid_price": float(self.current_mid_price) if self.current_mid_price else None,
            "trend_direction": "UP" if self.is_uptrend else "DOWN",
            "trend_strength": self.trend_strength,
            "position": pos_info,
            "performance": {
                "total_trades": self.performance.total_trades,
                "win_rate": self.performance.win_rate,
                "total_pnl": float(self.performance.total_pnl),
            },
        }
