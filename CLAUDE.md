# CLAUDE.md

NautilusTrader alapú trading keretrendszer MongoDB persistence-el.

## Struktúra

```
kebo-trade/
├── persistence/              # MongoDB layer
│   ├── config.py             # MongoDBConfig
│   ├── config_loader.py      # Config DB-ből
│   ├── publisher.py          # Async publisher
│   └── sync.py               # Crash recovery
├── strategies/
│   ├── __init__.py
│   ├── base.py               # BaseStrategy class
│   ├── bounce_scalper/       # Mean Reversion stratégia
│   │   ├── __init__.py
│   │   ├── strategy.py       # BounceScalper
│   │   ├── config.py         # BounceScalperConfig
│   │   ├── run_live_spot.py  # Live SPOT
│   │   ├── run_live_futures.py # Live FUTURES
│   │   └── run_backtest.py   # Backtest
│   └── grid/                 # Grid stratégia (fejlesztés alatt)
│       ├── __init__.py
│       ├── strategy.py       # GridStrategy
│       ├── config.py         # GridStrategyConfig
│       ├── run_live.py       # Live FUTURES
│       └── run_backtest.py   # Backtest
├── run/
│   ├── utils/
│   │   ├── cancel_all_orders.py  # Vészhelyzeti order törlés
│   │   ├── manage_config.py      # Config kezelés
│   │   └── upload_config.py      # Config feltöltés
│   └── mock_webhook.py
├── docs/
│   └── GRID_STRATEGY.md      # Grid stratégia dokumentáció
├── Dockerfile
├── docker-compose.yml
└── entrypoint.sh
```

## Stratégiák

### Bounce Scalper
Mean Reversion alapú LONG-only scalping stratégia.

```bash
# Backtest
python -m strategies.bounce_scalper.run_backtest

# Live (spot)
python -m strategies.bounce_scalper.run_live_spot

# Live (futures)
python -m strategies.bounce_scalper.run_live_futures
```

### Grid Strategy
Grid trading stratégia (MEGJEGYZÉS: jelenleg nem valódi grid, lásd docs/GRID_STRATEGY.md).

```bash
# Backtest
python -m strategies.grid.run_backtest

# Live (futures)
python -m strategies.grid.run_live
```

## Docker

```bash
# Build
docker build --platform linux/amd64 -t kebo-trade .

# Run (bounce_scalper spot)
docker run -e MONGODB_URI="..." -e BINANCE_API_KEY="..." -e BINANCE_API_SECRET="..." kebo-trade

# Run (grid futures)
docker run -e TRADING_MODE=futures -e STRATEGY_TYPE=grid -e ... kebo-trade

# docker-compose
docker-compose up -d
```

## Config kezelés

```bash
# Config feltöltése DB-be
python -m run.utils.manage_config upload bounce_scalper_live_001

# Configok listázása
python -m run.utils.manage_config list

# Config lekérése
python -m run.utils.manage_config get bounce_scalper_live_001
```

## Környezeti változók

| Változó | Leírás | Kötelező |
|---------|--------|----------|
| MONGODB_URI | Connection string | ✓ |
| STRATEGY_ID | Stratégia azonosító | - |
| STRATEGY_TYPE | "bounce_scalper" / "grid" | - |
| TRADING_MODE | "spot" / "futures" | - |
| BINANCE_API_KEY | API key | ✓ (live) |
| BINANCE_API_SECRET | API secret | ✓ (live) |
| BINANCE_ENV | "TESTNET" / "LIVE" | - |
| LOG_LEVEL | INFO/DEBUG | - |

## MongoDB Collections

| Collection | Tartalom |
|------------|----------|
| strategy_configs | Stratégia konfigurációk |
| orders | Order események |
| fills | Fill események |
| positions | Pozíciók |
| sessions | Session tracking |
| balances | Balance snapshots |
| heartbeat | Heartbeat |
| errors | Hibák |

## Több stratégia futtatása

```bash
# Strategy 1 (bounce_scalper)
STRATEGY_ID=bounce_scalper_001 python -m strategies.bounce_scalper.run_live_futures &

# Strategy 2 (grid)
STRATEGY_ID=grid_sol_50usdc python -m strategies.grid.run_live &

# Docker-ben
STRATEGY_ID=grid_sol_50usdc TRADING_MODE=futures STRATEGY_TYPE=grid docker-compose up -d
```
