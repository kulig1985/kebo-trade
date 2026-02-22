# Kebo Trade

NautilusTrader alapú trading keretrendszer MongoDB persistence-el.

## Gyors Indítás

### Python

```bash
pip install -r requirements.txt

# Backtest
python run/run_backtest.py

# Live
export MONGODB_URI="mongodb://user:pass@host:27017/db?authSource=admin"
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
export BINANCE_TESTNET="true"
python run/run_live.py
```

### Docker

```bash
docker build --platform linux/amd64 -t kebo-trade .
docker run --env-file .env kebo-trade

# vagy docker-compose
docker-compose up -d
```

## Config Kezelés

A stratégia konfigurációk MongoDB-ben vannak tárolva (`strategy_configs` collection).

```bash
# Config feltöltése
python run/manage_config.py upload bounce_scalper_live_001

# Configok listázása
python run/manage_config.py list

# Config lekérése
python run/manage_config.py get bounce_scalper_live_001
```

Ha nincs config az adatbázisban, a default értékeket használja.

## Több Stratégia Futtatása

```bash
# Két különböző strategy ID-val
STRATEGY_ID=bounce_001 python run/run_live.py &
STRATEGY_ID=bounce_002 python run/run_live.py &

# Docker-ben
STRATEGY_ID=bounce_001 docker-compose up -d
```

## Környezeti Változók

| Változó | Leírás | Kötelező |
|---------|--------|----------|
| `MONGODB_URI` | MongoDB connection string | ✓ |
| `STRATEGY_ID` | Stratégia azonosító | - |
| `BINANCE_API_KEY` | Binance API key | ✓ (live) |
| `BINANCE_API_SECRET` | Binance API secret | ✓ (live) |
| `BINANCE_TESTNET` | "true"/"false" | - |

## MongoDB Collections

| Collection | Tartalom |
|------------|----------|
| `strategy_configs` | Stratégia konfigurációk |
| `orders` | Order események |
| `fills` | Fill események |
| `positions` | Pozíciók |
| `sessions` | Session tracking |
| `balances` | Balance snapshots |
| `heartbeat` | Heartbeat |

## Projekt Struktúra

```
kebo-trade/
├── persistence/          # MongoDB layer
├── strategies/           # Stratégiák
├── run/                  # Futtatók
├── Dockerfile
└── docker-compose.yml
```

## Dokumentáció

- [BOUNCE_SCALPER.md](docs/BOUNCE_SCALPER.md) - Bounce Scalper stratégia
- [MONGODB_API.md](docs/MONGODB_API.md) - MongoDB API (NestJS fejlesztőknek)

## License

MIT
