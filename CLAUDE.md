# CLAUDE.md

NautilusTrader alapú trading keretrendszer MongoDB persistence-el.

## Struktúra

```
kebo-trade/
├── persistence/          # MongoDB layer
│   ├── config.py         # MongoDBConfig
│   ├── config_loader.py  # Config DB-ből
│   ├── publisher.py      # Async publisher
│   └── sync.py           # Crash recovery
├── strategies/
│   ├── base_strategy.py  # Base class
│   └── bounce_scalper.py # Stratégia
├── run/
│   ├── run_live.py       # Live trading
│   ├── run_backtest.py   # Backtest
│   └── manage_config.py  # Config kezelés
├── Dockerfile
└── docker-compose.yml
```

## Futtatás

### Python

```bash
# Backtest
python run/run_backtest.py

# Live
export MONGODB_URI="mongodb://user:pass@host:27017/db?authSource=admin"
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
python run/run_live.py
```

### Docker

```bash
# Build
docker build --platform linux/amd64 -t kebo-trade .

# Run
docker run -e MONGODB_URI="..." -e BINANCE_API_KEY="..." -e BINANCE_API_SECRET="..." kebo-trade

# docker-compose
docker-compose up -d
```

## Config kezelés

```bash
# Config feltöltése DB-be
python run/manage_config.py upload bounce_scalper_live_001

# Configok listázása
python run/manage_config.py list

# Config lekérése
python run/manage_config.py get bounce_scalper_live_001
```

## Környezeti változók

| Változó | Leírás | Kötelező |
|---------|--------|----------|
| MONGODB_URI | Connection string | ✓ |
| STRATEGY_ID | Stratégia azonosító | - |
| BINANCE_API_KEY | API key | ✓ (live) |
| BINANCE_API_SECRET | API secret | ✓ (live) |
| BINANCE_TESTNET | "true"/"false" | - |
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
# Strategy 1
STRATEGY_ID=bounce_scalper_001 python run/run_live.py &

# Strategy 2
STRATEGY_ID=bounce_scalper_002 python run/run_live.py &

# Docker-ben
STRATEGY_ID=bounce_scalper_001 docker-compose up -d
STRATEGY_ID=bounce_scalper_002 docker-compose up -d
```
