# Kebo Trade

NautilusTrader alapú trading keretrendszer MongoDB persistence-el.

---

## Környezeti Változók

Először hozd létre a `.env` fájlt:

```bash
cp .env.example .env
# Szerkeszd és töltsd ki!
```

| Változó | Leírás | Kötelező |
|---------|--------|----------|
| `MONGODB_URI` | MongoDB connection string | ✓ |
| `STRATEGY_ID` | Stratégia azonosító | - |
| `BINANCE_API_KEY` | Binance API key | ✓ (live) |
| `BINANCE_API_SECRET` | Binance API secret | ✓ (live) |
| `BINANCE_TESTNET` | "true"/"false" (default: true) | - |
| `WEBHOOK_URL` | Backend notification URL | - |
| `LOG_LEVEL` | INFO/DEBUG | - |

---

## Futtatás Python-nal

### Telepítés

```bash
cd kebo-trade
pip install -r requirements.txt
```

### Backtest (MongoDB nélkül)

```bash
python run/run_backtest.py
```

### Backtest (MongoDB-vel + webhook)

```bash
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
export MONGODB_ENABLED="true"
export WEBHOOK_URL="http://localhost:3000/api/trading/webhook"  # opcionális

python run/run_backtest.py
```

### Live Trading

```bash
# Környezeti változók
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
export BINANCE_TESTNET="true"
export STRATEGY_ID="bounce_scalper_live_001"

# Futtatás
python run/run_live.py
```

### Több stratégia párhuzamosan (Python)

```bash
# Terminal 1
STRATEGY_ID=bounce_scalper_001 python run/run_live.py

# Terminal 2
STRATEGY_ID=bounce_scalper_002 python run/run_live.py
```

---

## Futtatás Docker-rel

### Build

```bash
# macOS-en (linux/amd64 platformra)
docker build --platform linux/amd64 -t kebo-trade:latest .
```

### Egy stratégia futtatása

```bash
# .env fájllal
docker run --env-file .env kebo-trade:latest

# Vagy explicit env var-okkal
docker run \
  -e MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin" \
  -e BINANCE_API_KEY="..." \
  -e BINANCE_API_SECRET="..." \
  -e BINANCE_TESTNET="true" \
  -e STRATEGY_ID="bounce_scalper_live_001" \
  kebo-trade:latest
```

### docker-compose

```bash
# Indítás
docker-compose up -d

# Logok
docker-compose logs -f

# Leállítás
docker-compose down
```

### Több stratégia futtatása (Docker)

Minden stratégiához külön konténer kell, különböző `STRATEGY_ID`-val:

```bash
# Stratégia 1
docker run -d --name bounce-001 \
  -e MONGODB_URI="mongodb://..." \
  -e BINANCE_API_KEY="..." \
  -e BINANCE_API_SECRET="..." \
  -e STRATEGY_ID="bounce_scalper_001" \
  kebo-trade:latest

# Stratégia 2
docker run -d --name bounce-002 \
  -e MONGODB_URI="mongodb://..." \
  -e BINANCE_API_KEY="..." \
  -e BINANCE_API_SECRET="..." \
  -e STRATEGY_ID="bounce_scalper_002" \
  kebo-trade:latest
```

Vagy docker-compose-szal (hozz létre `docker-compose.multi.yml`):

```yaml
services:
  bounce-001:
    image: kebo-trade:latest
    environment:
      - MONGODB_URI=${MONGODB_URI}
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
      - STRATEGY_ID=bounce_scalper_001
    restart: unless-stopped

  bounce-002:
    image: kebo-trade:latest
    environment:
      - MONGODB_URI=${MONGODB_URI}
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
      - STRATEGY_ID=bounce_scalper_002
    restart: unless-stopped
```

```bash
docker-compose -f docker-compose.multi.yml up -d
```

---

## Config Kezelés

A stratégia konfigurációk MongoDB-ben tárolhatók (`strategy_configs` collection).

```bash
# MONGODB_URI kell hozzá!
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"

# Config feltöltése (default értékekkel)
python run/manage_config.py upload bounce_scalper_live_001

# Összes config listázása
python run/manage_config.py list

# Config lekérése
python run/manage_config.py get bounce_scalper_live_001
```

**Ha nincs config a DB-ben**, a default értékeket használja (code-ban definiált).

---

## MongoDB Collections

| Collection | Tartalom |
|------------|----------|
| `strategy_configs` | Stratégia konfigurációk |
| `orders` | Order események |
| `fills` | Fill események |
| `positions` | Pozíciók |
| `sessions` | Session tracking |
| `balances` | Balance snapshots (live) |
| `heartbeat` | Heartbeat (live) |
| `errors` | Hibák |

---

## Webhook Notification

Ha be van állítva `WEBHOOK_URL`, minden DB írás után HTTP POST megy a backend-nek:

```bash
export WEBHOOK_URL="http://nestjs-backend:3000/api/trading/webhook"
```

Payload:
```json
{
  "event": "orders",
  "collection": "orders",
  "strategy_id": "bounce_scalper_001",
  "timestamp": "2026-02-22T12:00:00.000Z",
  "data": { ... }
}
```

---

## Dokumentáció

- [docs/BOUNCE_SCALPER.md](docs/BOUNCE_SCALPER.md) - Bounce Scalper stratégia
- [docs/MONGODB_API.md](docs/MONGODB_API.md) - MongoDB API + Webhook spec (NestJS fejlesztőknek)

---

## Projekt Struktúra

```
kebo-trade/
├── persistence/          # MongoDB layer
│   ├── config.py         # MongoDBConfig
│   ├── config_loader.py  # Config DB-ből
│   ├── publisher.py      # Async publisher + webhook
│   └── sync.py           # Crash recovery
├── strategies/           # Stratégiák
├── run/
│   ├── run_live.py       # Live trading
│   ├── run_backtest.py   # Backtest
│   └── manage_config.py  # Config kezelés
├── Dockerfile
└── docker-compose.yml
```

## License

MIT
