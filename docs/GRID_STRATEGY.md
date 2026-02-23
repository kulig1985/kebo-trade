# Grid Trading Stratégia

Geometrikus grid trading stratégia Binance Futures-re, NautilusTrader alapon MongoDB persistence-el.

---

## Tartalomjegyzék

1. [Áttekintés](#1-áttekintés)
2. [Működési Ciklus](#2-működési-ciklus)
3. [Konfiguráció - Részletes Magyarázat](#3-konfiguráció---részletes-magyarázat)
4. [Kockázatkezelés](#4-kockázatkezelés)
5. [Futtatás](#5-futtatás)
6. [Példa Konfiguráció](#6-példa-konfiguráció)
7. [Mit Fogsz Látni](#7-mit-fogsz-látni)

---

## 1. Áttekintés

A Grid Strategy egy geometrikus eloszlású ordereket használó kereskedési stratégia, amely az aktuális ár körül helyez el buy és sell ordereket.

### Fő jellemzők

- **Single Position Mode** - Egyszerre csak egy pozíció lehet nyitva
- **Geometrikus grid szintek** - Az orderek geometrikus eloszlásban helyezkednek el
- **Automatikus TP/SL** - Minden pozícióhoz TP és SL kerül elhelyezésre
- **USDC alapú méretezés** - Order méret USDC-ben megadva
- **Kockázatkezelési védelmek** - Breakout stop, trailing stop, max drawdown

---

## 2. Működési Ciklus

### 2.1 GRID MÓD (Nincs nyitott pozíció)

```
                    SELL orderek (ár FELETT)
                    ────────────────────────
                         SELL @ 175.2
                         SELL @ 173.8
                         SELL @ 172.4
                         SELL @ 171.0
    Aktuális ár ───────► 170.0 ◄─────────
                         BUY @ 169.0
                         BUY @ 167.6
                         BUY @ 166.2
                         BUY @ 164.8
                    ────────────────────────
                    BUY orderek (ár ALATT)
```

### 2.2 POZÍCIÓ NYITÁS (Grid order FILL)

Amikor egy grid order teljesül:

```
ELŐTTE:                          UTÁNA:
10 grid order a piacon    →      0 grid order (MIND TÖRÖLVE)
0 pozíció                 →      1 pozíció (LONG vagy SHORT)
0 TP/SL                   →      2 order (1 TP + 1 SL)
```

**LONG pozíció (BUY teljesült):**
```
Entry:  169.0 (BUY teljesült)
TP:     entry × (1 + tp_pct) = 169.51 (SELL LIMIT)   ← Eladunk drágábban = PROFIT
SL:     entry × (1 - sl_pct) = 166.47 (SELL STOP)    ← Eladunk olcsóbban = LOSS
```

**SHORT pozíció (SELL teljesült):**
```
Entry:  171.0 (SELL teljesült)
TP:     entry × (1 - tp_pct) = 170.49 (BUY LIMIT)    ← Visszavásárlás olcsóbban = PROFIT
SL:     entry × (1 + sl_pct) = 173.57 (BUY STOP)     ← Visszavásárlás drágábban = LOSS
```

### 2.3 POZÍCIÓ ZÁRÁS

**Take Profit teljesül:**
- Profit realizálódik
- SL order törlődik
- Grid újraközpontosítás az aktuális áron

**Stop Loss teljesül:**
- Loss realizálódik
- TP order törlődik
- Grid újraközpontosítás az aktuális áron

### 2.4 Állapot Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   ┌──────────┐                              ┌──────────┐        │
│   │          │  Grid order FILL             │          │        │
│   │   GRID   │ ──────────────────────────►  │  TP/SL   │        │
│   │   MÓD    │                              │   MÓD    │        │
│   │          │  TP vagy SL FILL             │          │        │
│   │ 10 order │ ◄──────────────────────────  │ 2 order  │        │
│   │ 0 pozíció│                              │ 1 pozíció│        │
│   └──────────┘                              └──────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Konfiguráció - Részletes Magyarázat

### 3.1 Grid Paraméterek

#### `grid_levels` (Alapérték: 15)

**Mit jelent:** Hány darab order kerül elhelyezésre az ár ALATT (BUY) és az ár FELETT (SELL).

**Példa:**
```
grid_levels = 5

→ 5 BUY order az ár alatt
→ 5 SELL order az ár felett
→ Összesen: 10 order a piacon
```

**Hatás:**
- **Több level** = Sűrűbb háló, több esély a fill-re, de több tőke kell
- **Kevesebb level** = Ritkább háló, kevesebb fill, de kisebb tőkeigény

---

#### `order_size_usdc` (Alapérték: 50)

**Mit jelent:** Minden egyes order értéke USDC-ben.

**Példa:**
```
order_size_usdc = 10
SOL ára = 170 USDC

→ Egy order mennyisége: 10 / 170 = 0.059 SOL
→ Ha 10 order van: 10 × 10 = 100 USDC potenciális kitettség
```

**Hatás:**
- **Nagyobb érték** = Nagyobb pozíciók, több profit/loss
- **Kisebb érték** = Kisebb pozíciók, kisebb kockázat
- **Minimum:** Binance Futures min notional = 5 USDC

---

#### `grid_offset_pct` (Alapérték: 8.0)

**Mit jelent:** A grid TELJES szélessége százalékban. A grid az ár körül ±(offset/2) távolságra terjed.

**Példa:**
```
grid_offset_pct = 2.0
Aktuális ár = 170.00

→ Half offset = 2.0 / 2 = 1.0%
→ Grid alsó széle: 170.00 × 0.99 = 168.30
→ Grid felső széle: 170.00 × 1.01 = 171.70
→ Grid tartomány: 168.30 - 171.70
```

**Hatás:**
- **Szélesebb grid** = Távolabbi orderek, ritkább fill-ek, de nagyobb ármozgást lefed
- **Szűkebb grid** = Közelebbi orderek, gyakoribb fill-ek, de kis ármozgásnál is kilép

```
grid_offset_pct = 2%   →  ±1% az ártól  →  Szűk grid
grid_offset_pct = 8%   →  ±4% az ártól  →  Széles grid
grid_offset_pct = 16%  →  ±8% az ártól  →  Nagyon széles grid
```

---

#### `take_profit_pct` (Alapérték: 1.2)

**Mit jelent:** Hány százalék profitot célzunk meg egy pozíción.

**Példa LONG esetén:**
```
take_profit_pct = 0.3
Entry ár = 169.00

→ TP ár = 169.00 × (1 + 0.003) = 169.51
→ Ha elérjük: 0.3% profit
→ 10 USDC pozíción: 0.03 USDC profit
```

**Példa SHORT esetén:**
```
take_profit_pct = 0.3
Entry ár = 171.00

→ TP ár = 171.00 × (1 - 0.003) = 170.49
→ Ha elérjük: 0.3% profit
```

**Hatás:**
- **Nagyobb TP%** = Ritkábban teljesül, de nagyobb profit trade-enként
- **Kisebb TP%** = Gyakrabban teljesül, de kisebb profit trade-enként

---

#### `stop_loss_pct` (Alapérték: 2.0)

**Mit jelent:** Mekkora veszteségnél záródik automatikusan a pozíció.

**Példa LONG esetén:**
```
stop_loss_pct = 1.5
Entry ár = 169.00

→ SL ár = 169.00 × (1 - 0.015) = 166.47
→ Ha elérjük: -1.5% loss
→ 10 USDC pozíción: -0.15 USDC veszteség
```

**Risk/Reward arány:**
```
TP = 0.3%, SL = 1.5%
R/R = 0.3 / 1.5 = 0.2

→ Ahhoz, hogy profitábilis legyél: win rate > 83% kell!
```

---

### 3.2 Újraközpontosítás

#### `recenter_drift_threshold_pct` (Alapérték: 3.0)

**Mit jelent:** Ha az ár ennyivel eltávolodik a grid közepétől, újraközpontosítás történik.

**Példa:**
```
recenter_drift_threshold_pct = 1.5
Grid közép = 170.00

→ Drift küszöb = 170.00 × 0.015 = 2.55 USDC
→ Ha ár > 172.55 VAGY ár < 167.45 → Recenter
```

**Mi történik recenter-nél:**
1. Összes grid order TÖRLÉS
2. Új grid elhelyezés az aktuális ár körül

---

#### `recenter_interval_seconds` (Alapérték: 300)

**Mit jelent:** Minimum ennyi időnek kell eltelnie két újraközpontosítás között.

**Példa:**
```
recenter_interval_seconds = 300

→ Ha 10:00:00-kor volt recenter
→ Legközelebb 10:05:00 után lehet újra
→ Még ha a drift elérte is a küszöböt korábban
```

**Miért fontos:** Megakadályozza a túl gyakori order törlést/újraküldést, ami fee-ket generál.

---

### 3.3 Kockázatkezelés

#### `breakout_threshold_pct` (Alapérték: 6.0)

**Mit jelent:** Ha az ár ennyivel kilép a grid tartományból, MINDEN leáll.

**Példa:**
```
breakout_threshold_pct = 8.0
Grid alsó = 168.30
Grid felső = 171.70

→ Breakout alsó: 168.30 × (1 - 0.08) = 154.84
→ Breakout felső: 171.70 × (1 + 0.08) = 185.44

→ Ha ár < 154.84 VAGY ár > 185.44:
  - Összes order TÖRLÉS
  - Pozíció ZÁRÁS
  - Grid SZÜNET
```

---

#### `trailing_stop_threshold_pct` (Alapérték: 8.0)

**Mit jelent:** Ha az ár visszaesik a session csúcsától ennyivel, MINDEN leáll.

**Példa:**
```
trailing_stop_threshold_pct = 10.0
Session legmagasabb ár = 180.00

→ Trailing stop: 180.00 × (1 - 0.10) = 162.00

→ Ha ár < 162.00:
  - Összes order TÖRLÉS
  - Pozíció ZÁRÁS
  - Grid SZÜNET
```

**Megjegyzés:** `enable_trailing_stop = false` esetén nem aktív!

---

#### `max_drawdown_pct` (Alapérték: 15.0)

**Mit jelent:** Ha a számla egyenlege ennyivel csökken a kezdeti értéktől, MINDEN leáll.

**Példa:**
```
max_drawdown_pct = 20.0
Kezdeti equity = 500 USDC

→ Drawdown limit: 500 × (1 - 0.20) = 400 USDC

→ Ha equity < 400 USDC:
  - Összes order TÖRLÉS
  - Pozíció ZÁRÁS
  - Grid SZÜNET
```

---

#### `max_long_notional` / `max_short_notional` / `max_total_notional`

**Mit jelent:** Maximum mekkora pozíció értéket engedélyezünk.

**Példa:**
```
max_long_notional = 60
max_short_notional = 60
max_total_notional = 100

→ Max LONG pozíció: 60 USDC
→ Max SHORT pozíció: 60 USDC
→ Max összes: 100 USDC (ha mindkét irányban van pozíció)
```

**Megjegyzés:** Single position mode-ban egyszerre csak egy irányban van pozíció, szóval a `max_total_notional` ritkán releváns.

---

### 3.4 Funkció Kapcsolók

| Paraméter | Alapérték | Mit csinál |
|-----------|-----------|------------|
| `volatility_adapt_offset` | true | ATR alapján szélesíti/szűkíti a gridet |
| `enable_breakout_stop` | true | Breakout védelem aktív |
| `enable_exposure_limits` | true | Notional limitek aktívak |
| `enable_trailing_stop` | true | Trailing stop aktív |
| `enable_max_drawdown` | true | Drawdown védelem aktív |
| `enable_auto_resume` | true | Szünet után auto újraindítás |
| `enable_dynamic_grid_levels` | true | Volatilitás alapú level számítás |

---

### 3.5 Dinamikus Grid

#### `min_grid_levels` / `max_grid_levels`

**Mit jelent:** Ha `enable_dynamic_grid_levels = true`, a grid szintek száma automatikusan változik.

**Példa:**
```
grid_levels = 5 (alap)
min_grid_levels = 3
max_grid_levels = 8

→ Magas volatilitás esetén: 3 level (kevesebb order)
→ Alacsony volatilitás esetén: 8 level (több order)
→ Normál esetben: 5 level
```

---

### 3.6 Indikátorok

| Paraméter | Alapérték | Mit csinál |
|-----------|-----------|------------|
| `atr_period` | 14 | ATR számítás periódusa (volatilitás mérés) |
| `sma_fast_period` | 9 | Gyors mozgóátlag (trend irány) |
| `sma_slow_period` | 21 | Lassú mozgóátlag (trend irány) |

**Trend érzékelés:**
```
Ha SMA(9) > SMA(21) → UPTREND
Ha SMA(9) < SMA(21) → DOWNTREND
```

---

## 4. Kockázatkezelés

### 4.1 Összefoglaló Táblázat

| Védelem | Trigger | Mi történik |
|---------|---------|-------------|
| Breakout Stop | Ár kilép grid ± X% | Flatten + Pause |
| Trailing Stop | Ár csúcstól -X% | Flatten + Pause |
| Max Drawdown | Equity kezdettől -X% | Flatten + Pause |
| Exposure Limit | Notional > limit | Pause (nincs flatten) |

### 4.2 Auto Resume

Ha `enable_auto_resume = true`:
- 30 perc szünet után
- Ha az ár visszatér az eredeti grid tartomány ±5%-ába
- Automatikusan újraindul a grid

---

## 5. Futtatás

### 5.1 Docker

```bash
# docker.env
MONGODB_URI=mongodb://user:pass@host:27017/nautilus?authSource=admin
STRATEGY_ID=grid_sol_50usdc
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_ENV=TESTNET
TRADING_MODE=futures
STRATEGY_TYPE=grid
SYMBOL=SOLUSDC

# Indítás
docker-compose up -d

# Logok
docker-compose logs -f

# Leállítás (GRACEFUL - törli az ordereket!)
docker-compose down
```

### 5.2 Python

```bash
source .env
python run/run_live_grid.py
```

---

## 6. Példa Konfiguráció

### `grid_sol_50usdc` (MongoDB-ben)

```json
{
  "strategy_id": "grid_sol_50usdc",
  "strategy_type": "grid",
  "symbol": "SOLUSDC",
  "parameters": {
    "order_size_usdc": 10,
    "grid_levels": 5,
    "grid_offset_pct": 2,
    "take_profit_pct": 0.3,
    "stop_loss_pct": 1.5,
    "recenter_drift_threshold_pct": 1.5,
    "recenter_interval_seconds": 300,
    "breakout_threshold_pct": 8,
    "trailing_stop_threshold_pct": 10,
    "max_drawdown_pct": 20,
    "max_long_notional": 60,
    "max_short_notional": 60,
    "max_total_notional": 100,
    "volatility_adapt_offset": false,
    "enable_breakout_stop": true,
    "enable_exposure_limits": true,
    "enable_trailing_stop": false,
    "enable_max_drawdown": true,
    "enable_auto_resume": true,
    "enable_dynamic_grid_levels": false
  }
}
```

### Mit jelent ez konkrétan?

| Paraméter | Érték | Gyakorlati jelentés |
|-----------|-------|---------------------|
| `grid_levels: 5` | 10 order | 5 BUY + 5 SELL |
| `order_size_usdc: 10` | 10 USDC/order | ~0.059 SOL @ 170 USDC |
| `grid_offset_pct: 2` | ±1% grid | 168.30 - 171.70 tartomány |
| `take_profit_pct: 0.3` | +0.3% | ~0.03 USDC profit/trade |
| `stop_loss_pct: 1.5` | -1.5% | ~0.15 USDC loss/trade |
| `max exposure` | 50 USDC | 5 × 10 USDC |

---

## 7. Mit Fogsz Látni

### 7.1 Indításkor

```
========================================
KEBO TRADE - GRID STRATEGY (FUTURES USDC MARGIN)
========================================
Strategy: grid_sol_50usdc
Symbol: SOLUSDC
Environment: TESTNET
Grid levels: 5
Order size: 10 USDC

🚀 STARTING - Grid Strategy Futures USDC Margin
✅ RUNNING - Grid Strategy
```

### 7.2 Grid Elhelyezés

```
Grid centered at 170.00 | Range: 168.30 - 171.70 (±1.00%)
Placed 10 grid orders (effective levels: 5)
```

**Binance-on 10 order jelenik meg.**

### 7.3 Státusz Log (~30 másodpercenként)

```
[STATE] Price=170.0000 | Position=NONE | Mode=GRID | GridOrders=10 (actual=10) | TP=False SL=False | P&L=0.00
```

### 7.4 Grid Order Fill

```
GRID ORDER FILLED: BUY at 169.49 (level 2) → Switching to TP/SL mode
Cancelled 9 grid orders → switched to TP/SL mode
Placing TP/SL for BUY position: Entry=169.49, TP=170.00, SL=166.95
TP/SL mode active: TP at 170.00, SL at 166.95
```

**Binance-on most 2 order van (TP + SL).**

### 7.5 Take Profit Fill

```
TAKE PROFIT FILLED at 170.00 → Re-centering grid
Trade closed with PROFIT: +0.05 USDC
Placed 10 grid orders (effective levels: 5)
```

### 7.6 Stop Loss Fill

```
STOP LOSS TRIGGERED at 166.95 → Re-centering grid
Trade closed with LOSS: -0.15 USDC
Placed 10 grid orders (effective levels: 5)
```

### 7.7 Leállítás

```
⚠️ Received SIGTERM, initiating graceful shutdown...
SHUTDOWN - Cancelling ALL orders via Binance API...
  Successfully cancelled 10 orders via Binance API
✅ Shutdown complete
```

---

## 8. Összefoglaló Táblázat

| Fázis | Binance Orderek | Pozíció | Log Kulcsszavak |
|-------|-----------------|---------|-----------------|
| Indulás | 0 → 10 | NINCS | "Placed 10 grid orders" |
| GRID mód | 10 | NINCS | "Mode=GRID" |
| Fill után | 10 → 2 | VAN | "GRID ORDER FILLED" |
| TP/SL mód | 2 | VAN | "Mode=TP/SL" |
| TP fill | 2 → 10 | NINCS | "PROFIT" |
| SL fill | 2 → 10 | NINCS | "LOSS" |
| Leállítás | X → 0 | marad | "Successfully cancelled" |
