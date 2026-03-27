"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         BOUNCE SCALPER STRATÉGIA                            ║
║                                                                              ║
║  Mean Reversion alapú LONG-only scalping stratégia NautilusTrader-hez.      ║
║                                                                              ║
║  MŰKÖDÉSI ELV:                                                               ║
║  - Figyeli az árat az EMA (mozgóátlag) körül                                ║
║  - Ha az ár leesik az EMA alá egy bizonyos távolságra (ATR-el mérve),       ║
║    majd visszapattan → VÁSÁROL                                               ║
║  - A profit/veszteség szinteknél automatikusan zár                          ║
║                                                                              ║
║  Ez a "bounce" (visszapattanás) stratégia - a támaszról való                ║
║  visszapattanásra játszik.                                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from decimal import Decimal
from typing import Optional

import pandas as pd
from nautilus_trader.indicators import AverageTrueRange, ExponentialMovingAverage
from nautilus_trader.model import Bar, TradeTick
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import PositionClosed, PositionOpened
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency

from strategies.base import BaseStrategy
from strategies.bounce_scalper.config import BounceScalperConfig


class BounceScalper(BaseStrategy):
    """
    Bounce Scalper - Mean Reversion Scalping Stratégia.

    ┌─────────────────────────────────────────────────────────────────┐
    │ LONG-only, multi-instrument, alacsony kockázatú scalping       │
    │                                                                 │
    │ Minden instrumenthez (pl. BTC, ETH, SOL) külön:                │
    │   - EMA indikátor (exponenciális mozgóátlag)                   │
    │   - ATR indikátor (átlagos valós tartomány - volatilitás)      │
    │   - Saját pozíció követés                                       │
    └─────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, config: BounceScalperConfig):
        """
        Stratégia inicializálása.

        Args:
            config: BounceScalperConfig objektum az összes beállítással
        """
        # ═══════════════════════════════════════════════════════════════
        # SZÜLŐ OSZTÁLY INICIALIZÁLÁSA
        # ═══════════════════════════════════════════════════════════════
        # A NautilusTrader Strategy osztályból származunk
        # A config automatikusan beállítódik a self.config-ba
        super().__init__(config)

        # ═══════════════════════════════════════════════════════════════
        # PER-INSTRUMENT ÁLLAPOT TÁROLÁS
        # ═══════════════════════════════════════════════════════════════
        # Minden instrumenthez (pl. BTCUSDC, ETHUSDC) külön dictionary
        # Ez tárolja az indikátorokat, árakat, pozíció infókat
        self.instrument_states: dict[InstrumentId, dict] = {}

        # USDC currency referencia (egyenleg ellenőrzéshez)
        self.usdc: Optional[Currency] = None

        # ═══════════════════════════════════════════════════════════════
        # INICIALIZÁLÁS MINDEN INSTRUMENTHEZ
        # ═══════════════════════════════════════════════════════════════
        for instrument_id in config.instrument_ids:
            self.instrument_states[instrument_id] = {
                # ─────────────────────────────────────────────────────────
                # INDIKÁTOROK
                # ─────────────────────────────────────────────────────────
                # EMA = Exponential Moving Average (exponenciális mozgóátlag)
                # Ez az "átlagár" amit figyel a stratégia
                "ema": ExponentialMovingAverage(config.ema_period),

                # ATR = Average True Range (átlagos valós tartomány)
                # Ez méri a volatilitást - mennyit mozog az ár tipikusan
                "atr": AverageTrueRange(config.atr_period),

                # ─────────────────────────────────────────────────────────
                # SZÁMÍTOTT SÁVOK
                # ─────────────────────────────────────────────────────────
                # Entry band = EMA - X*ATR
                # Ha az ár ez ALÁ esik, majd visszapattan → VÁSÁRLÁS
                "entry_band": None,

                # Exit band = EMA + Y*ATR (opcionális)
                # Ha az ár ez FÖLÉ megy → ELADÁS (profit taking)
                "exit_band": None,

                # ─────────────────────────────────────────────────────────
                # ÁR KÖVETÉS
                # ─────────────────────────────────────────────────────────
                # Előző bar záróára (cross detection-höz)
                "last_close": None,

                # Belépési ár (TP/SL számításhoz)
                "entry_price": None,

                # ─────────────────────────────────────────────────────────
                # POZÍCIÓ KÖVETÉS
                # ─────────────────────────────────────────────────────────
                # Aktív pozíció azonosítója
                "position_id": None,

                # Hány aktív pozíció van ezen az instrumenten
                "position_count": 0,

                # ─────────────────────────────────────────────────────────
                # COOLDOWN (VÁRAKOZÁS)
                # ─────────────────────────────────────────────────────────
                # Pozíció zárása után ennyi bar-t várunk az újra belépés előtt
                # Megakadályozza a túl gyors "ide-oda" kereskedést
                "cooldown_remaining": 0,

                # ─────────────────────────────────────────────────────────
                # INSTRUMENT REFERENCIA
                # ─────────────────────────────────────────────────────────
                # Magát az instrumentet tárolja (precision, min qty, stb.)
                "instrument": None,
            }

    # ═══════════════════════════════════════════════════════════════════════
    # LIFECYCLE METÓDUSOK
    # ═══════════════════════════════════════════════════════════════════════

    def on_start(self):
        """
        ┌─────────────────────────────────────────────────────────────────┐
        │ STRATÉGIA INDÍTÁSA                                             │
        │                                                                 │
        │ Ez fut le amikor a stratégia elindul.                          │
        │ Itt regisztráljuk az indikátorokat és feliratkozunk az adatokra│
        └─────────────────────────────────────────────────────────────────┘
        """
        self.log.info("BounceScalper starting...")

        # USDC currency referencia (egyenleg ellenőrzéshez)
        self.usdc = Currency.from_str("USDC", strict=False)

        # ═══════════════════════════════════════════════════════════════
        # MINDEN INSTRUMENTHEZ KÜLÖN BEÁLLÍTÁS
        # ═══════════════════════════════════════════════════════════════
        for instrument_id in self.config.instrument_ids:

            # Instrument lekérése a cache-ből
            # (a NautilusTrader tárolja az instrumentek adatait)
            instrument = self.cache.instrument(instrument_id)
            if instrument is None:
                self.log.error(f"Instrument {instrument_id} not found in cache!")
                continue

            state = self.instrument_states[instrument_id]
            state["instrument"] = instrument

            # Bar type a configból (pl. 5-MINUTE barok)
            bar_type = self.config.bar_types[instrument_id]

            # ─────────────────────────────────────────────────────────────
            # INDIKÁTOR REGISZTRÁLÁS
            # ─────────────────────────────────────────────────────────────
            # A NautilusTrader AUTOMATIKUSAN frissíti az indikátorokat
            # minden új bar-nál, ha regisztráljuk őket
            self.register_indicator_for_bars(bar_type, state["ema"])
            self.register_indicator_for_bars(bar_type, state["atr"])

            # ─────────────────────────────────────────────────────────────
            # HISTORICAL WARMUP
            # ─────────────────────────────────────────────────────────────
            # Historikus adatok kérése, hogy az indikátorok "bemelegedjenek"
            # Kell nekik múltbeli adat, hogy értelmesen működjenek
            self.request_bars(
                bar_type=bar_type,
                start=self._clock.utc_now() - pd.Timedelta(days=30),
                callback=None,
            )

            # ─────────────────────────────────────────────────────────────
            # BAR SUBSCRIPTION
            # ─────────────────────────────────────────────────────────────
            # Feliratkozás az új barokra - minden 5 percben kapunk egyet
            self.subscribe_bars(bar_type)

            self.log.info(f"Subscribed: {instrument_id} → {bar_type}")

        self.log.info(
            f"BounceScalper started with {len(self.config.instrument_ids)} instruments. "
            f"Trade size: {self.config.trade_size_usdc} USDC, "
            f"TP: {self.config.take_profit_pct}%, SL: {self.config.stop_loss_pct}%"
        )

    def on_stop(self):
        """
        ┌─────────────────────────────────────────────────────────────────┐
        │ STRATÉGIA LEÁLLÍTÁSA                                           │
        │                                                                 │
        │ Minden nyitott pozíciót bezárunk a leállítás előtt.            │
        └─────────────────────────────────────────────────────────────────┘
        """
        self.log.info("BounceScalper stopping...")

        for instrument_id, state in self.instrument_states.items():
            # Ellenőrizzük, van-e nyitott pozíció
            net_pos = self.portfolio.net_position(instrument_id)

            if net_pos > 0 and state["instrument"] is not None:
                # MARKET SELL order a pozíció zárásához
                qty = state["instrument"].make_qty(net_pos)
                order = self.order_factory.market(
                    instrument_id=instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                    reduce_only=True,  # Csak meglévő pozíciót zár
                    time_in_force=TimeInForce.GTC,
                )
                self.submit_order(order)
                self.log.info(f"Closing position on stop: {instrument_id}")

    # ═══════════════════════════════════════════════════════════════════════
    # BAR EVENT - FŐ LOGIKA
    # ═══════════════════════════════════════════════════════════════════════

    def on_bar(self, bar: Bar) -> None:
        """
        ┌─────────────────────────────────────────────────────────────────┐
        │ BAR ESEMÉNY - A STRATÉGIA MAGJA                                │
        │                                                                 │
        │ Minden új bar-nál (pl. 5 percenként) lefut.                    │
        │                                                                 │
        │ 1. Frissíti az entry/exit bandeket az indikátorokból           │
        │ 2. Ellenőrzi az entry feltételeket (ha nincs pozíció)          │
        │ 3. Ellenőrzi az exit feltételeket (ha van pozíció)             │
        └─────────────────────────────────────────────────────────────────┘
        """
        instrument_id = bar.bar_type.instrument_id

        # Csak a mi instrumentjeinkre reagálunk
        if instrument_id not in self.instrument_states:
            return

        state = self.instrument_states[instrument_id]

        # A bar záróára (close) - ez az aktuális "ár"
        close_price = bar.close.as_double()

        # ═══════════════════════════════════════════════════════════════
        # COOLDOWN KEZELÉS
        # ═══════════════════════════════════════════════════════════════
        # Ha még várakozási időben vagyunk, csökkentjük a számlálót
        if state["cooldown_remaining"] > 0:
            state["cooldown_remaining"] -= 1

        # ═══════════════════════════════════════════════════════════════
        # INDIKÁTOR ELLENŐRZÉS
        # ═══════════════════════════════════════════════════════════════
        # Az indikátoroknak kell idő (történelmi adat), hogy inicializálódjanak
        if not state["ema"].initialized or not state["atr"].initialized:
            state["last_close"] = close_price
            # Log waiting for warmup (every 10 bars)
            warmup_count = state.get("warmup_count", 0) + 1
            state["warmup_count"] = warmup_count
            if warmup_count % 10 == 1:
                self.log.info(f"[{instrument_id.symbol}] Waiting for indicator warmup...")
            return

        ema_value = state["ema"].value  # EMA aktuális értéke
        atr_value = state["atr"].value  # ATR aktuális értéke (volatilitás)

        # ═══════════════════════════════════════════════════════════════
        # ENTRY BAND SZÁMÍTÁSA
        # ═══════════════════════════════════════════════════════════════
        # entry_band = EMA - (szorzó × ATR)
        #
        # Példa: Ha EMA = 100, ATR = 5, szorzó = 0.8:
        #        entry_band = 100 - (0.8 × 5) = 100 - 4 = 96
        #
        # Ez azt jelenti: ha az ár 96 alá esik, majd visszamegy fölé,
        # az egy "bounce" (visszapattanás) - VÁSÁRLÁSI jel!
        entry_band = float(
            ema_value - float(self.config.entry_atr_multiplier) * atr_value
        )
        state["entry_band"] = entry_band

        # ═══════════════════════════════════════════════════════════════
        # EXIT BAND SZÁMÍTÁSA (opcionális)
        # ═══════════════════════════════════════════════════════════════
        if self.config.exit_atr_multiplier is not None:
            state["exit_band"] = float(
                ema_value + float(self.config.exit_atr_multiplier) * atr_value
            )

        # ═══════════════════════════════════════════════════════════════
        # ENTRY / EXIT LOGIKA
        # ═══════════════════════════════════════════════════════════════

        # Periodic status log (every 20 bars per instrument)
        bar_count = state.get("bar_count", 0) + 1
        state["bar_count"] = bar_count
        if bar_count % 20 == 0:
            pos_status = "FLAT" if self.portfolio.is_flat(instrument_id) else f"POS: {self.portfolio.net_position(instrument_id)}"
            self.log.info(
                f"[{instrument_id.symbol}] Bar #{bar_count} | "
                f"Close: {close_price:.2f} | EMA: {ema_value:.2f} | ATR: {atr_value:.2f} | "
                f"Entry band: {entry_band:.2f} | {pos_status}"
            )

        if self.portfolio.is_flat(instrument_id):
            # 🟢 NINCS POZÍCIÓ → Entry ellenőrzés
            self._check_entry(instrument_id, close_price, state)
        else:
            # 🔴 VAN POZÍCIÓ → Exit ellenőrzés
            self._check_exit(instrument_id, close_price, state)

        # Utolsó close mentése (következő bar-nál a cross detection-höz)
        state["last_close"] = close_price

    # ═══════════════════════════════════════════════════════════════════════
    # ENTRY LOGIKA
    # ═══════════════════════════════════════════════════════════════════════

    def _check_entry(self, instrument_id: InstrumentId, close_price: float, state: dict):
        """
        ┌─────────────────────────────────────────────────────────────────┐
        │ BELÉPÉSI FELTÉTELEK ELLENŐRZÉSE                                │
        │                                                                 │
        │ ENTRY JEL: Az ár FELFELÉ keresztezi az entry_band-et           │
        │                                                                 │
        │     ▲ ár                                                        │
        │     │      ╭─────╮                                              │
        │     │     ╱       ╲  ← ár visszapattan                          │
        │ ────┼────╳─────────╳─── EMA                                     │
        │     │   ╱           ╲                                           │
        │ ────┼──╳─────────────── entry_band (EMA - X*ATR)               │
        │     │ ╱                                                         │
        │     │╱  ← előző bar itt volt (ALATTA)                          │
        │     └──────────────────────────────────► idő                    │
        │                                                                 │
        │ Ha az előző bar ALATT volt, a mostani FELETTE → BOUNCE!        │
        └─────────────────────────────────────────────────────────────────┘
        """
        # ─────────────────────────────────────────────────────────────────
        # ELŐFELTÉTELEK ELLENŐRZÉSE
        # ─────────────────────────────────────────────────────────────────

        # Cooldown aktív? (nemrég zártunk pozíciót)
        if state["cooldown_remaining"] > 0:
            return

        # Entry band kész? (indikátorok inicializálódtak)
        if state["entry_band"] is None or state["last_close"] is None:
            return

        # Max pozíciók ellenőrzése (alapból 1 / instrument)
        if state["position_count"] >= self.config.max_positions_per_instrument:
            return

        # Egyenleg ellenőrzése (van elég USDC a vásárláshoz?)
        if not self._has_sufficient_balance():
            self.log.warning(
                f"Insufficient balance for {instrument_id}. "
                f"Required: {self.config.min_free_balance_usdc} USDC"
            )
            return

        # ─────────────────────────────────────────────────────────────────
        # CROSS UP DETEKTÁLÁS
        # ─────────────────────────────────────────────────────────────────
        # crossed_up = True, ha:
        #   - Előző bar close ALATT volt az entry_band-nek
        #   - Mostani bar close FELETTE vagy EGYENLŐ az entry_band-del
        #
        # Ez a "bounce" - az ár visszapattant a támaszról!
        crossed_up = state["last_close"] < state["entry_band"] <= close_price

        if crossed_up:
            self._submit_buy_order(instrument_id, close_price, state)

    def _submit_buy_order(
        self, instrument_id: InstrumentId, price: float, state: dict
    ):
        """
        ┌─────────────────────────────────────────────────────────────────┐
        │ VÁSÁRLÁSI ORDER KÜLDÉSE                                        │
        │                                                                 │
        │ MARKET ORDER = azonnal teljesül az aktuális piaci áron         │
        └─────────────────────────────────────────────────────────────────┘
        """
        instrument = state["instrument"]
        if instrument is None:
            return

        # ─────────────────────────────────────────────────────────────────
        # MENNYISÉG SZÁMÍTÁSA
        # ─────────────────────────────────────────────────────────────────
        # trade_size_usdc (pl. 5 USDC) / ár = mennyiség
        #
        # Példa: 5 USDC / 100 USDC/BTC = 0.05 BTC
        usd_value = self.config.trade_size_usdc
        raw_qty = usd_value / Decimal(str(price))

        # make_qty() = az instrument precision-jéhez igazítja a mennyiséget
        qty = instrument.make_qty(raw_qty)

        if qty.as_double() == 0.0:
            self.log.warning(
                f"Computed qty is zero for {instrument_id} @ {price}, skipping."
            )
            return

        # ─────────────────────────────────────────────────────────────────
        # MARKET BUY ORDER
        # ─────────────────────────────────────────────────────────────────
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
            time_in_force=TimeInForce.GTC,  # Good Till Cancelled
        )
        self.submit_order(order)

        self.log.info(
            f"🟢 ENTRY {instrument_id} | BUY {qty} @ {price:.4f} | "
            f"Entry band: {state['entry_band']:.4f}"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # EXIT LOGIKA
    # ═══════════════════════════════════════════════════════════════════════

    def _check_exit(self, instrument_id: InstrumentId, close_price: float, state: dict):
        """
        ┌─────────────────────────────────────────────────────────────────┐
        │ KILÉPÉSI FELTÉTELEK ELLENŐRZÉSE                                │
        │                                                                 │
        │ 3 kilépési ok:                                                  │
        │   1. TAKE PROFIT - elértük a profit célt (+X%)                 │
        │   2. STOP LOSS - elértük a veszteség limitet (-Y%)             │
        │   3. EXIT BAND - ár visszament az EMA fölé (opcionális)        │
        └─────────────────────────────────────────────────────────────────┘
        """
        # Nettó pozíció (mennyiségi coinban, pl. 0.05 BTC)
        net_pos = self.portfolio.net_position(instrument_id)
        if net_pos <= 0:
            return

        entry_price = state["entry_price"]
        if entry_price is None:
            return

        # ─────────────────────────────────────────────────────────────────
        # 1) TAKE PROFIT ELLENŐRZÉS
        # ─────────────────────────────────────────────────────────────────
        # tp_price = entry_price × (1 + TP%)
        #
        # Példa: entry = 100, TP = 1% → tp_price = 100 × 1.01 = 101
        # Ha az ár eléri a 101-et → PROFIT, zárjuk!
        tp_price = entry_price * (1.0 + float(self.config.take_profit_pct) / 100.0)
        if close_price >= tp_price:
            self._submit_sell_order(instrument_id, net_pos, state, "TAKE PROFIT", close_price)
            return

        # ─────────────────────────────────────────────────────────────────
        # 2) STOP LOSS ELLENŐRZÉS
        # ─────────────────────────────────────────────────────────────────
        # sl_price = entry_price × (1 - SL%)
        #
        # Példa: entry = 100, SL = 1.5% → sl_price = 100 × 0.985 = 98.5
        # Ha az ár lemegy 98.5-re → VESZTESÉG, zárjuk, hogy ne legyen nagyobb!
        sl_price = entry_price * (1.0 - float(self.config.stop_loss_pct) / 100.0)
        if close_price <= sl_price:
            self._submit_sell_order(instrument_id, net_pos, state, "STOP LOSS", close_price)
            return

        # ─────────────────────────────────────────────────────────────────
        # 3) EXIT BAND ELLENŐRZÉS (opcionális)
        # ─────────────────────────────────────────────────────────────────
        # Ha az ár átmegy az EMA + ATR fölé → profit taking
        if self.config.exit_atr_multiplier is not None and state["exit_band"] is not None:
            if close_price >= state["exit_band"]:
                self._submit_sell_order(instrument_id, net_pos, state, "EXIT BAND", close_price)
                return

    def _submit_sell_order(
        self,
        instrument_id: InstrumentId,
        net_pos: float,
        state: dict,
        reason: str,
        exit_price: float,
    ):
        """
        ┌─────────────────────────────────────────────────────────────────┐
        │ ELADÁSI ORDER KÜLDÉSE (POZÍCIÓ ZÁRÁS)                          │
        │                                                                 │
        │ reduce_only=True = csak meglévő pozíciót zár, nem nyit újat    │
        └─────────────────────────────────────────────────────────────────┘
        """
        instrument = state["instrument"]
        if instrument is None:
            return

        qty = instrument.make_qty(net_pos)

        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
            reduce_only=True,  # FONTOS: csak zár, nem nyit short-ot!
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

        # ─────────────────────────────────────────────────────────────────
        # PNL SZÁMÍTÁS (profit/loss)
        # ─────────────────────────────────────────────────────────────────
        entry_price = state["entry_price"] or 0
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        self.log.info(
            f"{emoji} EXIT {instrument_id} | {reason} | SELL {qty} | "
            f"Entry: {entry_price:.4f}, Exit: {exit_price:.4f}, PnL: {pnl_pct:+.2f}%"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # EGYENLEG ELLENŐRZÉS
    # ═══════════════════════════════════════════════════════════════════════

    def _has_sufficient_balance(self) -> bool:
        """
        ┌─────────────────────────────────────────────────────────────────┐
        │ EGYENLEG ELLENŐRZÉS                                            │
        │                                                                 │
        │ Ellenőrzi, hogy van-e elég szabad USDC új pozíció nyitásához.  │
        │                                                                 │
        │ Példa: Ha min_free_balance = 10 USDC, és van 8 USDC → FALSE    │
        │        Ha min_free_balance = 10 USDC, és van 15 USDC → TRUE    │
        └─────────────────────────────────────────────────────────────────┘
        """
        if self.usdc is None:
            return True  # Ha nem tudjuk ellenőrizni, engedjük

        # Account lekérése
        accounts = self.cache.accounts()
        if not accounts:
            return True

        account = accounts[0]

        # USDC egyenleg
        balance = account.balance(self.usdc)
        if balance is None:
            return True

        # Szabad egyenleg (nem zárolt)
        free_balance = balance.free.as_double()
        required = float(self.config.min_free_balance_usdc)

        return free_balance >= required

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT HANDLING
    # ═══════════════════════════════════════════════════════════════════════

    def on_event(self, event):
        """
        ┌─────────────────────────────────────────────────────────────────┐
        │ ESEMÉNYEK KEZELÉSE                                             │
        │                                                                 │
        │ A NautilusTrader különböző eseményeket küld:                   │
        │   - PositionOpened: új pozíció nyílt                           │
        │   - PositionClosed: pozíció bezárult                           │
        │                                                                 │
        │ Ezeket használjuk a belső állapot frissítésére.                │
        └─────────────────────────────────────────────────────────────────┘
        """
        # Szülő osztály esemény kezelése (MongoDB)
        super().on_event(event)

        if isinstance(event, PositionOpened):
            # ─────────────────────────────────────────────────────────────
            # ÚJ POZÍCIÓ NYÍLT
            # ─────────────────────────────────────────────────────────────
            instrument_id = event.instrument_id
            if instrument_id in self.instrument_states:
                state = self.instrument_states[instrument_id]

                # Pozíció azonosító mentése
                state["position_id"] = event.position_id

                # Belépési ár mentése (TP/SL számításhoz)
                # avg_px_open = átlagos nyitó ár
                state["entry_price"] = event.avg_px_open

                # Pozíció számláló növelése
                state["position_count"] += 1

                self.log.info(
                    f"Position opened: {instrument_id} @ {event.avg_px_open:.4f}"
                )

        elif isinstance(event, PositionClosed):
            # ─────────────────────────────────────────────────────────────
            # POZÍCIÓ BEZÁRULT
            # ─────────────────────────────────────────────────────────────
            instrument_id = event.instrument_id
            if instrument_id in self.instrument_states:
                state = self.instrument_states[instrument_id]

                # Állapot reset
                state["position_id"] = None
                state["entry_price"] = None
                state["position_count"] = max(0, state["position_count"] - 1)

                # COOLDOWN indítása
                # Ennyi bar-t várunk az újra belépés előtt
                state["cooldown_remaining"] = self.config.cooldown_ticks

                self.log.info(
                    f"Position closed: {instrument_id} | "
                    f"Cooldown: {self.config.cooldown_ticks} bars"
                )

    # ═══════════════════════════════════════════════════════════════════════
    # MONGODB CALLBACK METÓDUSOK
    # ═══════════════════════════════════════════════════════════════════════

    def _get_balance_snapshot(self) -> dict:
        """
        Balance adatok a MongoDB publisher számára.

        Returns:
            Balance információk dictionary-je
        """
        if self.usdc is None:
            return {}

        accounts = self.cache.accounts()
        if not accounts:
            return {}

        account = accounts[0]
        balances = []

        # USDC egyenleg
        usdc_balance = account.balance(self.usdc)
        if usdc_balance:
            balances.append({
                "currency": "USDC",
                "total": float(usdc_balance.total.as_double()),
                "free": float(usdc_balance.free.as_double()),
                "locked": float(usdc_balance.locked.as_double()),
            })

        # Nyitott pozíciók száma
        open_positions = len(self.cache.positions_open())

        return {
            "balances": balances,
            "total_equity_usdc": float(usdc_balance.total.as_double()) if usdc_balance else 0,
            "open_positions_count": open_positions,
        }

    def _get_heartbeat_data(self) -> dict:
        """
        Heartbeat adatok a MongoDB publisher számára.

        Returns:
            Stratégia állapot dictionary
        """
        # Összesített állapot
        active_positions = 0
        instruments_in_cooldown = 0

        for instrument_id, state in self.instrument_states.items():
            if state["position_count"] > 0:
                active_positions += 1
            if state["cooldown_remaining"] > 0:
                instruments_in_cooldown += 1

        return {
            "active_positions": active_positions,
            "instruments_tracked": len(self.instrument_states),
            "instruments_in_cooldown": instruments_in_cooldown,
        }

    def _get_state_to_save(self) -> dict:
        """
        Stratégia állapot mentése (NautilusTrader + MongoDB).

        Returns:
            Mentendő állapot
        """
        # Per-instrument állapotok, amik fontosak recovery-hez
        states = {}
        for instrument_id, state in self.instrument_states.items():
            states[str(instrument_id)] = {
                "entry_price": state["entry_price"],
                "position_id": str(state["position_id"]) if state["position_id"] else None,
                "position_count": state["position_count"],
                "cooldown_remaining": state["cooldown_remaining"],
            }

        return {"instrument_states": states}

    def _restore_state(self, state: dict) -> None:
        """
        Stratégia állapot visszaállítása.

        Args:
            state: Mentett állapot
        """
        saved_states = state.get("instrument_states", {})

        for instrument_id_str, saved in saved_states.items():
            # Instrument ID visszaalakítása
            for instrument_id in self.instrument_states:
                if str(instrument_id) == instrument_id_str:
                    current = self.instrument_states[instrument_id]
                    current["entry_price"] = saved.get("entry_price")
                    current["position_count"] = saved.get("position_count", 0)
                    current["cooldown_remaining"] = saved.get("cooldown_remaining", 0)
                    self.log.info(f"State restored for {instrument_id}")
                    break
