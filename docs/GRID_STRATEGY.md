# Grid Trading Stratégia

Geometrikus grid trading stratégia Binance Futures-re, NautilusTrader alapon MongoDB persistence-el.

---

## Tartalomjegyzék

1. [Áttekintés](#1-áttekintés)
2. [Működési elv](#2-működési-elv)
3. [Konfiguráció](#3-konfiguráció)
4. [Backtest futtatása](#4-backtest-futtatása)
5. [Live trading](#5-live-trading)
6. [Kockázatkezelés](#6-kockázatkezelés)
7. [Technikai indikátorok](#7-technikai-indikátorok)
8. [MongoDB integráció](#8-mongodb-integráció)
9. [Példa config](#9-példa-config)

---

## 1. Áttekintés

A Grid Strategy egy geometrikus eloszlású ordereket használó kereskedési stratégia, amely az aktuális ár körül helyez el buy és sell ordereket. Különösen hatékony oldalazó (ranging) piacokon.

### Fő jellemzők

- **Geometrikus grid szintek** - Az orderek geometrikus eloszlásban helyezkednek el
- **Automatikus TP/SL** - Minden teljesült orderhez TP és SL kerül elhelyezésre
- **Volatilitás adaptáció** - ATR alapú grid szélesség igazítás
- **Trend érzékelés** - SMA cross alapú trend detektálás
- **Dinamikus grid szintek** - Volatilitás és trend alapú szint számítás
- **Kockázatkezelési védelmek** - Breakout stop, trailing stop, max drawdown
- **Single position mode** - Egyszerre csak egy pozíció

---

## 2. Működési elv

### 2.1 Grid felépítése

```
                    SELL orders
           ┌─────────────────────────┐
           │  S5  S4  S3  S2  S1     │  ← Ár felett
           └─────────────────────────┘
                        ↑
                   Current Price
                        ↓
           ┌─────────────────────────┐
           │  B1  B2  B3  B4  B5     │  ← Ár alatt
           └─────────────────────────┘
                    BUY orders
```

### 2.2 Geometrikus eloszlás

Az orderek nem egyenletes távolságra vannak, hanem geometrikus arányban:

```
ratio = (upper_price / lower_price) ^ (1 / (grid_levels * 2))

BUY_i  = current_price * ratio^(-i)
SELL_i = current_price * ratio^(+i)
```

### 2.3 Trade flow

1. **Inicializálás**: Grid középre állítása az aktuális ár körül
2. **Order elhelyezés**: Buy orderek ár alatt, sell orderek ár felett
3. **Fill kezelés**: Ha egy grid order teljesül, TP/SL pár kerül elhelyezésre
4. **Pozíció zárás**: TP vagy SL teljesül
5. **Grid újraindítás**: Pozíció zárása után a grid újraközpontosodik

### 2.4 Single Position Mode

A stratégia egyszerre csak egy pozíciót tart:
- Egy grid order teljesülésekor az összes többi grid order törlődik
- TP/SL elhelyezése a pozícióhoz
- Pozíció zárása után a grid újra felépül

---

## 3. Konfiguráció

### 3.1 Grid paraméterek

| Paraméter | Alapérték | Leírás |
|-----------|-----------|--------|
| `grid_levels` | 15 | Grid szintek száma (mindkét irányba) |
| `order_quantity` | 1.0 | Order mennyiség |
| `grid_offset_pct` | 8.0% | Grid szélesség (±4% az ártól) |
| `take_profit_pct` | 1.2% | Take profit százalék |
| `stop_loss_pct` | 2.0% | Stop loss százalék |

### 3.2 Újraközpontosítás

| Paraméter | Alapérték | Leírás |
|-----------|-----------|--------|
| `recenter_drift_threshold_pct` | 3.0% | Ár eltolódás küszöb |
| `recenter_interval_seconds` | 300 | Minimum idő újraközpontosítások között |

### 3.3 Kockázatkezelés

| Paraméter | Alapérték | Leírás |
|-----------|-----------|--------|
| `breakout_threshold_pct` | 6.0% | Breakout stop küszöb |
| `trailing_stop_threshold_pct` | 8.0% | Trailing stop a csúcstól |
| `max_drawdown_pct` | 15.0% | Maximum drawdown limit |
| `max_long_notional` | 800 | Max long oldali kitettség |
| `max_short_notional` | 800 | Max short oldali kitettség |
| `max_total_notional` | 1200 | Max összes kitettség |

### 3.4 Dinamikus grid

| Paraméter | Alapérték | Leírás |
|-----------|-----------|--------|
| `min_grid_levels` | 5 | Minimum grid szintek |
| `max_grid_levels` | 30 | Maximum grid szintek |
| `volatility_adapt_offset` | true | ATR alapú offset adaptáció |
| `enable_dynamic_grid_levels` | true | Dinamikus szint számítás |

### 3.5 Technikai indikátorok

| Paraméter | Alapérték | Leírás |
|-----------|-----------|--------|
| `atr_period` | 14 | ATR periódus |
| `sma_fast_period` | 9 | Gyors SMA periódus |
| `sma_slow_period` | 21 | Lassú SMA periódus |

---

## 4. Backtest futtatása

### 4.1 Adat előkészítés

Hozd létre az adat fájlt a `data/grid_data/` mappában:

```bash
mkdir -p data/grid_data
```

Fájlnév formátum: `{SYMBOL}_{START}_{END}_{TIMEFRAME}.csv`

Példa: `BTCUSDC_20251101_20260221_15m.csv`

CSV formátum:
```csv
timestamp,open,high,low,close,volume
2025-11-01 00:00:00,50000.0,50100.0,49900.0,50050.0,100.5
2025-11-01 00:15:00,50050.0,50150.0,49950.0,50100.0,95.2
...
```

### 4.2 Backtest futtatás

```bash
cd kebo-trade

# MongoDB nélkül
MONGODB_ENABLED=false python run/run_backtest_grid.py

# MongoDB-vel
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
MONGODB_ENABLED=true python run/run_backtest_grid.py
```

### 4.3 Eredmények

A `backtest_results/` mappában:
- `grid_{timestamp}_orders.csv` - Összes order
- `grid_{timestamp}_fills.csv` - Fill-ek
- `grid_{timestamp}_positions.csv` - Pozíciók
- `grid_{timestamp}_summary.txt` - Összefoglaló

---

## 5. Live trading

### 5.1 Környezeti változók

```bash
# .env fájl
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
export STRATEGY_ID="grid_strategy_futures_001"
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
export BINANCE_TESTNET="true"  # vagy "false" ÉLESHEZ
export SYMBOL="BTCUSDC"
export LOG_LEVEL="INFO"
```

### 5.2 Futtatás

```bash
# Testnet (ajánlott először!)
source .env
python run/run_live_grid.py

# Éles (VALÓS PÉNZ!)
export BINANCE_TESTNET="false"
python run/run_live_grid.py
```

### 5.3 Leállítás

`Ctrl+C` - Graceful shutdown:
- Összes nyitott order törlése
- Pozíció zárása
- Állapot mentése MongoDB-be

### 5.4 Docker

```bash
# docker.env
MONGODB_URI=mongodb://user:pass@host:27017/nautilus?authSource=admin
STRATEGY_ID=grid_strategy_futures_001
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true
TRADING_MODE=grid
SYMBOL=BTCUSDC

# Futtatás
docker run --env-file docker.env kebo-trade:grid
```

---

## 6. Kockázatkezelés

### 6.1 Breakout Stop

Ha az ár a grid tartományból ennyivel kilép:

```
Lower bound = grid_lower * (1 - breakout_threshold)
Upper bound = grid_upper * (1 + breakout_threshold)

Ha ár < lower_bound VAGY ár > upper_bound → FLATTEN + PAUSE
```

### 6.2 Trailing Stop

A legmagasabb ártól visszaesés:

```
Trail low = highest_price * (1 - trailing_stop_threshold)

Ha ár < trail_low → FLATTEN + PAUSE
```

### 6.3 Maximum Drawdown

A kezdő equity-től számított maximális veszteség:

```
Threshold = starting_equity * (1 - max_drawdown_pct)

Ha current_equity < threshold → FLATTEN + PAUSE
```

### 6.4 Exposure Limits

Maximális kitettség korlátozás:

```
Long notional < max_long_notional
Short notional < max_short_notional
Total notional < max_total_notional
```

### 6.5 Auto Resume

Pause után automatikus újraindítás ha:
1. Eltelt a `resume_cooldown_minutes`
2. Az ár az eredeti grid tartomány ±`resume_price_tolerance_pct` között van

---

## 7. Technikai indikátorok

### 7.1 ATR (Average True Range)

A volatilitás mérésére használt indikátor.

```
True Range = max(
    high - low,
    abs(high - prev_close),
    abs(low - prev_close)
)

ATR = SMA(True Range, period)
```

Használat: Grid offset adaptáció

### 7.2 SMA (Simple Moving Average)

Trend irány meghatározása:

```
SMA_fast (9 periódus)
SMA_slow (21 periódus)

Ha SMA_fast > SMA_slow → UPTREND
Ha SMA_fast < SMA_slow → DOWNTREND
```

### 7.3 Dinamikus Grid Szintek

A grid szintek száma dinamikusan változik:

**Magas volatilitás (>3%)**: Grid szintek csökkennek
**Alacsony volatilitás (<1%)**: Grid szintek növekednek
**Erős trend (>4%)**: Grid szintek felezése
**Közepes trend (>2%)**: Grid szintek 2/3-ra csökkentése

---

## 8. MongoDB integráció

### 8.1 Session tracking

Minden indítás új session-t hoz létre. Crash recovery támogatás.

### 8.2 Collections

| Collection | Tartalom |
|------------|----------|
| `sessions` | Session tracking |
| `orders` | Order események |
| `fills` | Fill események |
| `positions` | Pozíciók |
| `balances` | Balance snapshots |
| `heartbeat` | Heartbeat (állapot) |
| `errors` | Hibák |

### 8.3 Heartbeat adatok

```json
{
  "grid_active": true,
  "paused_due_to_risk": false,
  "effective_grid_levels": 15,
  "current_mid_price": 50000.0,
  "trend_direction": "UP",
  "trend_strength": 2.5,
  "position": {
    "side": "LONG",
    "quantity": 0.001
  },
  "performance": {
    "total_trades": 10,
    "win_rate": 0.7,
    "total_pnl": 0.005
  }
}
```

---

## 9. Példa config

### 9.1 MongoDB config (strategy_configs collection)

```json
{
  "strategy_id": "grid_strategy_futures_001",
  "strategy_type": "grid_strategy",
  "symbol": "BTCUSDC",
  "parameters": {
    "grid_levels": 15,
    "order_quantity": 0.001,
    "grid_offset_pct": 8.0,
    "take_profit_pct": 1.2,
    "stop_loss_pct": 2.0,
    "recenter_drift_threshold_pct": 3.0,
    "recenter_interval_seconds": 300,
    "breakout_threshold_pct": 6.0,
    "trailing_stop_threshold_pct": 8.0,
    "max_drawdown_pct": 15.0,
    "max_long_notional": 800.0,
    "max_short_notional": 800.0,
    "max_total_notional": 1200.0,
    "volatility_adapt_offset": true,
    "enable_breakout_stop": true,
    "enable_exposure_limits": true,
    "enable_trailing_stop": true,
    "enable_max_drawdown": true,
    "enable_auto_resume": true,
    "enable_dynamic_grid_levels": true,
    "min_grid_levels": 5,
    "max_grid_levels": 30,
    "atr_period": 14,
    "sma_fast_period": 9,
    "sma_slow_period": 21
  }
}
```

### 9.2 Config feltöltés

Hozz létre `grid_config.json` fájlt a fenti tartalommal, majd:

```bash
python run/upload_config.py grid_config.json
```

---

## 10. Összehasonlítás: Grid vs Bounce Scalper

| Jellemző | Grid Strategy | Bounce Scalper |
|----------|---------------|----------------|
| **Irány** | LONG + SHORT | LONG only |
| **Pozíciók** | Single | Multiple per instrument |
| **Instrumentumok** | Egyetlen | Több |
| **Piaci feltétel** | Ranging | Mean reversion |
| **Entry** | Grid szint | EMA-ATR sáv |
| **TP/SL** | Limit + Stop-Market | Fix százalék |
| **Kockázatkezelés** | Breakout, trailing, drawdown | Min balance |

---

## 11. Tippek

### 11.1 Paraméter hangolás

- **Oldalazó piac**: Több grid szint, szűkebb offset
- **Trending piac**: Kevesebb szint, szélesebb offset
- **Magas volatilitás**: Automatikus adaptáció (`volatility_adapt_offset: true`)

### 11.2 Tesztelés

1. Mindig **TESTNET** módban kezdj
2. Futtass backtest-et különböző időszakokra
3. Figyeld a drawdown értékeket
4. Állítsd be a megfelelő position size-t

### 11.3 Élesen

- Használj alacsony order quantity-t kezdetben
- Állíts be szigorú max_drawdown limitet
- Figyeld a funding rate-eket (Futures)
- Ne hagyd felügyelet nélkül hosszú ideig
