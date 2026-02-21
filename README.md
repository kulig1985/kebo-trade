# Bounce Scalper Stratégia

## Mi ez?

A **Bounce Scalper** egy automatizált cryptocurrency kereskedési stratégia, amely a **"visszapattanás"** (bounce) jelenségét használja ki. Az ötlet egyszerű: amikor az ár átmenetileg leesik egy támasz szint alá, majd visszapattan, az egy jó vételi lehetőség.

A stratégia **sok kis trade-et** csinál, mindegyik kis profittal. Ez biztonságosabb, mint kevés nagy trade-et csinálni.

---

## Hogyan működik?

### 1. A "támasz szint" meghatározása

A stratégia minden pillanatban kiszámol egy **entry band** (belépési sávot):

```
Entry Band = EMA - (ATR × szorzó)
```

| Rövidítés | Teljes név | Mit csinál? |
|-----------|------------|-------------|
| **EMA** | Exponential Moving Average | Az elmúlt X bar átlagára |
| **ATR** | Average True Range | Mennyit mozog az ár átlagosan |

**Példa:**
- EMA = 100 USDC, ATR = 2 USDC, Szorzó = 0.8
- Entry Band = 100 - (2 × 0.8) = 98.4 USDC

### 2. Mikor veszünk? (BOUNCE)

**NEM akkor veszünk, amikor az ár leesik!** Hanem amikor **visszapattan**.

```
VÁSÁRLÁS ha:
  - Előző bar záróár < Entry Band
  - Mostani bar záróár >= Entry Band
```

### 3. Mikor adunk el?

- **Take Profit:** +1% (entry price × 1.01)
- **Stop Loss:** -1.5% (entry price × 0.985)

---

## Paraméterek

| Paraméter | Default | Jelentés |
|-----------|---------|----------|
| `trade_size_usdc` | 5.0 | Trade méret USDC-ben |
| `max_positions_per_instrument` | 1 | Max pozíció instrumentenként |
| `ema_period` | 20 | EMA periódus |
| `atr_period` | 14 | ATR periódus |
| `entry_atr_multiplier` | 0.8 | ATR szorzó |
| `take_profit_pct` | 1.0 | Take Profit % |
| `stop_loss_pct` | 1.5 | Stop Loss % |
| `cooldown_ticks` | 10 | Várakozás trade után (bar) |

---

## Kereskedett párok

BTCUSDC, ETHUSDC, SOLUSDC, ARBUSDC, TIAUSDC, ADAUSDC, AVAXUSDC, DOGEUSDC

---

## Backtest Eredmények

- **Időszak:** 2025-01-01 - 2026-02-21
- **Profit:** +8.5% (1000 → 1085 USDC)
- **Trade-ek:** ~13,476 (~32/nap)

---

## Fájl Struktúra

```
kebo-trade/
├── README.md                    # Ez a fájl
├── CLAUDE.md                    # Claude Code instrukciók
├── requirements.txt             # Függőségek
├── pyproject.toml               # Projekt konfig
├── .gitignore                   # CSV kizárva!
├── strategies/
│   ├── bounce_scalper.py        # Stratégia kód
│   └── bounce_scalper_config.py # Konfiguráció
├── run/
│   ├── run_backtest.py          # Backtest futtatás
│   └── run_live.py              # Live kereskedés
├── data/
│   ├── download_bounce_data.py  # Adat letöltő
│   └── bounce_data/             # CSV adatok (gitignore!)
└── backtest_results/            # Riportok
```

---

## Futtatás

### 1. Backtest

```bash
cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade
python run/run_backtest.py
```

### 2. Live Kereskedés

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

### 3. Adat letöltés

```bash
cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade/data
python download_bounce_data.py
```

---

## Rövidítések Szótár

| Rövidítés | Angol | Magyar |
|-----------|-------|--------|
| EMA | Exponential Moving Average | Exponenciális Mozgóátlag |
| ATR | Average True Range | Átlagos Valós Tartomány |
| TP | Take Profit | Profit realizálás |
| SL | Stop Loss | Veszteség korlátozás |
| USDC | USD Coin | Stablecoin (1 USDC = 1 USD) |
| SPOT | Spot market | Azonnali piac |
| LONG | Long position | Vételi pozíció |

---

## Kockázatok

1. **Downtrend:** Ha az ár folyamatosan esik, veszteséges
2. **Gyors mozgások:** SL nem mindig teljesül pontosan
3. **Likviditás:** Kis forgalmú párokon slippage előfordulhat
