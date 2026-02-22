# Bounce Scalper Stratégia

Mean Reversion alapú LONG-only scalping stratégia NautilusTrader-hez.

## Működési Elv

A stratégia a **"visszapattanás"** (bounce) jelenségét használja ki:
- Amikor az ár átmenetileg leesik egy dinamikus támasz szint alá
- Majd visszapattan felfelé
- Az egy jó vételi lehetőség

```
     ▲ ár
     │      ╭─────╮
     │     ╱       ╲  ← ár visszapattan
 ────┼────╳─────────╳─── EMA (mozgóátlag)
     │   ╱           ╲
 ────┼──╳─────────────── Entry Band (EMA - ATR×0.8)
     │ ╱
     │╱  ← előző bar itt volt (ALATTA)
     └──────────────────────────────► idő

Ha az előző bar ALATT volt, a mostani FELETTE → BOUNCE → BUY!
```

## Stratégia Logika

### Entry (Vásárlás)

```
Entry Band = EMA(20) - ATR(14) × 0.8

VÁSÁRLÁS ha:
  - Előző bar close < Entry Band
  - Mostani bar close >= Entry Band
  - Nincs aktív pozíció
  - Nincs cooldown
  - Van elég szabad egyenleg
```

### Exit (Eladás)

```
Take Profit: entry_price × 1.01  (+1%)
Stop Loss:   entry_price × 0.985 (-1.5%)
```

## Paraméterek

| Paraméter | Default | Leírás |
|-----------|---------|--------|
| `trade_size_usdc` | 5.0 | Trade méret USDC-ben |
| `max_positions_per_instrument` | 1 | Max pozíció instrumentenként |
| `ema_period` | 20 | EMA periódus (bar) |
| `atr_period` | 14 | ATR periódus (bar) |
| `entry_atr_multiplier` | 0.8 | Entry band = EMA - X×ATR |
| `take_profit_pct` | 1.0 | Take Profit százalék |
| `stop_loss_pct` | 1.5 | Stop Loss százalék |
| `exit_atr_multiplier` | None | Exit band (opcionális) |
| `min_free_balance_usdc` | 10.0 | Min szabad egyenleg |
| `cooldown_ticks` | 10 | Várakozás exit után (bar) |

## Kereskedett Párok

- BTCUSDC
- ETHUSDC
- SOLUSDC
- ARBUSDC
- TIAUSDC
- ADAUSDC
- AVAXUSDC
- DOGEUSDC

## Timeframe

**5 perces barok** - Optimalizálva scalping-hez.

## Backtest Eredmények

| Metrika | Érték |
|---------|-------|
| Időszak | 2025-01-01 - 2026-02-21 |
| Kezdő egyenleg | 1000 USDC |
| Végső egyenleg | ~1085 USDC |
| Profit | +8.5% |
| Összes trade | ~13,476 |
| Trade/nap | ~32 |

## Futtatás

### Backtest

```bash
cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade

# Alap backtest
python run/run_backtest.py

# MongoDB-vel (események mentése)
MONGODB_ENABLED=true python run/run_backtest.py
```

### Live Trading

```bash
cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade

export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# TESTNET (ajánlott először!)
export BINANCE_TESTNET="true"
python run/run_live.py

# LIVE (VALÓS PÉNZ!)
export BINANCE_TESTNET="false"
python run/run_live.py
```

### Adat Letöltés

```bash
cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade/data
python download_bounce_data.py
```

## Fájlok

| Fájl | Leírás |
|------|--------|
| `strategies/bounce_scalper.py` | Stratégia implementáció |
| `strategies/bounce_scalper_config.py` | Konfiguráció (StrategyConfig) |
| `run/run_backtest.py` | Backtest runner |
| `run/run_live.py` | Live trading runner |
| `data/download_bounce_data.py` | Historikus adat letöltő |

## MongoDB Mezők

### Orders Collection

```json
{
  "strategy_type": "bounce_scalper",
  "strategy_id": "bounce_scalper_live_001",
  "client_order_id": "O-20260221-...",
  "instrument_id": "BTCUSDC.BINANCE",
  "order_side": "BUY",
  "order_type": "MARKET",
  "quantity": 0.00005,
  "status": "FILLED",
  "submitted_at": "2026-02-21T12:00:00Z"
}
```

### Positions Collection

```json
{
  "strategy_type": "bounce_scalper",
  "position_id": "P-001-BTCUSDC",
  "instrument_id": "BTCUSDC.BINANCE",
  "side": "LONG",
  "quantity": 0.00005,
  "avg_open_price": 95000.0,
  "avg_close_price": 95950.0,
  "realized_pnl": 0.0475,
  "status": "CLOSED",
  "opened_at": "2026-02-21T12:00:00Z",
  "closed_at": "2026-02-21T12:15:00Z",
  "duration_seconds": 900
}
```

## Indikátorok

### EMA (Exponential Moving Average)

Exponenciális mozgóátlag - az elmúlt N bar súlyozott átlaga, ahol az újabb barok nagyobb súlyt kapnak.

```
EMA(t) = α × Price(t) + (1 - α) × EMA(t-1)
α = 2 / (period + 1)
```

### ATR (Average True Range)

Átlagos valós tartomány - volatilitás mérése.

```
True Range = max(High - Low, |High - PrevClose|, |Low - PrevClose|)
ATR = EMA(True Range, period)
```

## Kockázatok

1. **Downtrend:** Hosszú esés esetén a visszapattanások nem működnek - sok SL
2. **Gyors mozgások:** SL nem mindig teljesül pontosan (slippage)
3. **Likviditás:** Kis forgalmú párokon rossz fill árak
4. **Sideways:** Alacsony volatilitás esetén kevés jelzés

## Optimalizálási Lehetőségek

- **ATR multiplier:** Alacsonyabb = több trade, magasabb = kevesebb de "biztosabb"
- **TP/SL arány:** Jelenlegi 1:1.5 - növelhető a TP nagyobb profit-hoz
- **Cooldown:** Csökkenthető agresszívebb trading-hez
- **Párok:** Volatilisebb párok több lehetőséget adnak

## Rövidítések

| Rövidítés | Angol | Magyar |
|-----------|-------|--------|
| EMA | Exponential Moving Average | Exponenciális Mozgóátlag |
| ATR | Average True Range | Átlagos Valós Tartomány |
| TP | Take Profit | Profit realizálás |
| SL | Stop Loss | Veszteség korlátozás |
| USDC | USD Coin | Stablecoin (1 USDC ≈ 1 USD) |
| SPOT | Spot market | Azonnali piac |
| LONG | Long position | Vételi pozíció |
