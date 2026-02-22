# Kebo Trade

NautilusTrader alapú cryptocurrency trading rendszer.

---

## Tartalomjegyzék

1. [Telepítés](#1-telepítés)
2. [Környezeti változók beállítása](#2-környezeti-változók-beállítása)
3. [Backtest futtatása](#3-backtest-futtatása)
4. [Live trading futtatása](#4-live-trading-futtatása)
5. [Config kezelés](#5-config-kezelés)
6. [Docker használat](#6-docker-használat)
7. [Több stratégia futtatása](#7-több-stratégia-futtatása)
8. [Webhook notification](#8-webhook-notification)
9. [Hibaelhárítás](#9-hibaelhárítás)

---

## 1. Telepítés

```bash
cd kebo-trade
pip install -r requirements.txt
```

---

## 2. Környezeti változók beállítása

Hozd létre a `.env` fájlt:

```bash
cp .env.example .env
```

Szerkeszd a `.env` fájlt:

```bash
# KÖTELEZŐ - MongoDB kapcsolat
MONGODB_URI=mongodb://user:password@host:27017/nautilus?authSource=admin

# KÖTELEZŐ live tradinghez - Binance API
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=true

# OPCIONÁLIS
STRATEGY_ID=bounce_scalper_live_001
WEBHOOK_URL=http://localhost:3000/api/trading/webhook
LOG_LEVEL=INFO
```

Betöltés terminálban:

```bash
export $(grep -v '^#' .env | xargs)
```

---

## 3. Backtest futtatása

### 3.1 Egyszerű backtest (MongoDB nélkül)

```bash
python run/run_backtest.py
```

Az eredmények a `backtest_results/` mappában lesznek.

### 3.2 Backtest MongoDB-vel

Ha szeretnéd, hogy a backtest is mentse az adatokat MongoDB-be:

```bash
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
export MONGODB_ENABLED="true"

python run/run_backtest.py
```

### 3.3 Backtest paraméterek módosítása

Szerkeszd a `run/run_backtest.py` fájlt:

```python
# 73-82. sor körül
SYMBOLS = [
    "BTC/USDC",
    "ETH/USDC",
    "SOL/USDC",
]

# 85-89. sor körül
START_DATE = "20251101"
END_DATE = "20260221"
STARTING_USDC = 1000.0
```

---

## 4. Live trading futtatása

### 4.1 Testnet (ajánlott először!)

```bash
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
export BINANCE_API_KEY="your_testnet_api_key"
export BINANCE_API_SECRET="your_testnet_api_secret"
export BINANCE_TESTNET="true"

python run/run_live.py
```

### 4.2 Éles kereskedés (VALÓS PÉNZ!)

```bash
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
export BINANCE_API_KEY="your_live_api_key"
export BINANCE_API_SECRET="your_live_api_secret"
export BINANCE_TESTNET="false"

python run/run_live.py
```

### 4.3 Leállítás

`Ctrl+C` - graceful shutdown, menti az állapotot.

---

## 5. Config kezelés

A stratégia konfigurációkat MongoDB-ben tárolhatod (`strategy_configs` collection).

**FONTOS:** Először állítsd be a MONGODB_URI-t!

```bash
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
```

### 5.1 Default config feltöltése

```bash
python run/manage_config.py upload bounce_scalper_live_001
```

Ez a beépített default értékeket tölti fel.

### 5.2 Custom config feltöltése (JSON fájlból)

Hozz létre egy JSON fájlt (pl. `my_config.json`):

```json
{
    "strategy_id": "my_btc_scalper",
    "strategy_type": "bounce_scalper",
    "symbols": ["BTCUSDC", "ETHUSDC"],
    "parameters": {
        "trade_size_usdc": 10.0,
        "max_positions_per_instrument": 1,
        "take_profit_pct": 1.5,
        "stop_loss_pct": 2.0,
        "ema_period": 20,
        "atr_period": 14,
        "entry_atr_multiplier": 0.8,
        "exit_atr_multiplier": null,
        "min_free_balance_usdc": 20.0,
        "cooldown_ticks": 10
    }
}
```

Töltsd fel:

```bash
python run/upload_config.py my_config.json
```

Példa fájl: `example_config.json`

### 5.3 Custom config feltöltése (interaktív)

```bash
python run/upload_config.py --interactive
```

Ez végigkérdezi a paramétereket.

### 5.4 Configok listázása

```bash
python run/manage_config.py list
```

Kimenet:
```
Found 2 config(s):

  • bounce_scalper_live_001
    Type: bounce_scalper
    Symbols: ['BTCUSDC', 'ETHUSDC', 'SOLUSDC']

  • my_btc_scalper
    Type: bounce_scalper
    Symbols: ['BTCUSDC', 'ETHUSDC']
```

### 5.5 Config lekérése

```bash
python run/manage_config.py get my_btc_scalper
```

### 5.6 Config módosítása

Módosítsd a JSON fájlt és töltsd fel újra - felülírja a régit:

```bash
python run/upload_config.py my_config.json
```

### 5.7 Ha nincs config a DB-ben

A rendszer automatikusan a beépített default értékeket használja, így a DB-ben tárolt config **opcionális**.

---

## 6. Docker használat

### 6.1 Image buildelése

```bash
# macOS-en (linux/amd64 platformra, mert a szerver Linux)
docker build --platform linux/amd64 -t kebo-trade:latest .
```

### 6.2 Futtatás .env fájllal

```bash
docker run --env-file .env kebo-trade:latest
```

### 6.3 Futtatás explicit változókkal

```bash
docker run \
  -e MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin" \
  -e BINANCE_API_KEY="your_api_key" \
  -e BINANCE_API_SECRET="your_api_secret" \
  -e BINANCE_TESTNET="true" \
  -e STRATEGY_ID="bounce_scalper_live_001" \
  kebo-trade:latest
```

### 6.4 docker-compose használata

```bash
# Indítás
docker-compose up -d

# Logok követése
docker-compose logs -f

# Leállítás
docker-compose down
```

### 6.5 Háttérben futtatás

```bash
docker run -d --name bounce-scalper \
  --env-file .env \
  --restart unless-stopped \
  kebo-trade:latest

# Logok
docker logs -f bounce-scalper

# Leállítás
docker stop bounce-scalper
docker rm bounce-scalper
```

---

## 7. Több stratégia futtatása

Minden stratégiához **külön konténer** kell, különböző `STRATEGY_ID`-val.

### 7.1 Python-nal (két terminál)

**Terminal 1:**
```bash
export MONGODB_URI="mongodb://..."
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
export STRATEGY_ID="bounce_scalper_001"
python run/run_live.py
```

**Terminal 2:**
```bash
export MONGODB_URI="mongodb://..."
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
export STRATEGY_ID="bounce_scalper_002"
python run/run_live.py
```

### 7.2 Docker-rel (két konténer)

```bash
# Stratégia 1
docker run -d --name bounce-001 \
  -e MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin" \
  -e BINANCE_API_KEY="your_api_key" \
  -e BINANCE_API_SECRET="your_api_secret" \
  -e BINANCE_TESTNET="true" \
  -e STRATEGY_ID="bounce_scalper_001" \
  --restart unless-stopped \
  kebo-trade:latest

# Stratégia 2
docker run -d --name bounce-002 \
  -e MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin" \
  -e BINANCE_API_KEY="your_api_key" \
  -e BINANCE_API_SECRET="your_api_secret" \
  -e BINANCE_TESTNET="true" \
  -e STRATEGY_ID="bounce_scalper_002" \
  --restart unless-stopped \
  kebo-trade:latest
```

### 7.3 docker-compose.multi.yml használata

```bash
# .env fájl kell a közös változókhoz (MONGODB_URI, BINANCE_*, stb.)

# Indítás
docker-compose -f docker-compose.multi.yml up -d

# Logok
docker-compose -f docker-compose.multi.yml logs -f

# Csak egy stratégia logjait
docker-compose -f docker-compose.multi.yml logs -f bounce-001

# Leállítás
docker-compose -f docker-compose.multi.yml down
```

### 7.4 Saját docker-compose készítése több stratégiához

Hozz létre `docker-compose.custom.yml` fájlt:

```yaml
services:
  btc-strategy:
    image: kebo-trade:latest
    container_name: btc-scalper
    environment:
      - MONGODB_URI=${MONGODB_URI}
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
      - BINANCE_TESTNET=true
      - STRATEGY_ID=btc_scalper_001
    restart: unless-stopped

  eth-strategy:
    image: kebo-trade:latest
    container_name: eth-scalper
    environment:
      - MONGODB_URI=${MONGODB_URI}
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
      - BINANCE_TESTNET=true
      - STRATEGY_ID=eth_scalper_001
    restart: unless-stopped

  sol-strategy:
    image: kebo-trade:latest
    container_name: sol-scalper
    environment:
      - MONGODB_URI=${MONGODB_URI}
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
      - BINANCE_TESTNET=true
      - STRATEGY_ID=sol_scalper_001
    restart: unless-stopped
```

```bash
docker-compose -f docker-compose.custom.yml up -d
```

---

## 8. Webhook notification

Ha be van állítva `WEBHOOK_URL`, minden DB írás után HTTP POST megy a backend-nek.

### 8.1 Beállítás

```bash
export WEBHOOK_URL="http://your-backend:3000/api/trading/webhook"
```

Vagy `.env` fájlban:
```
WEBHOOK_URL=http://your-backend:3000/api/trading/webhook
```

### 8.2 Webhook payload

```json
{
  "event": "orders",
  "collection": "orders",
  "strategy_id": "bounce_scalper_001",
  "session_id": "uuid...",
  "is_backtest": false,
  "timestamp": "2026-02-22T12:00:00.000Z",
  "data": {
    "client_order_id": "...",
    "instrument_id": "BTCUSDC.BINANCE",
    "order_side": "BUY",
    "quantity": 0.001,
    "status": "SUBMITTED"
  }
}
```

### 8.3 Event típusok

| Event | Mikor |
|-------|-------|
| `orders` | Új order |
| `order_update` | Order státusz változás |
| `fills` | Order teljesülés |
| `positions` | Pozíció nyitás |
| `position_update` | Pozíció zárás/változás |
| `balances` | Balance snapshot (~60 sec) |
| `heartbeat` | Heartbeat (~30 sec) |
| `errors` | Hiba |

---

## 9. Hibaelhárítás

### "MONGODB_URI not set!"

Állítsd be a környezeti változót:
```bash
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
```

### "MongoDB connection failed"

- Ellenőrizd a connection string-et
- Ellenőrizd, hogy a MongoDB szerver elérhető-e
- Ellenőrizd a felhasználónevet és jelszót
- Speciális karakterek URL encode-olva legyenek (pl. `+` → `%2B`)

### "BINANCE_API_KEY required"

Állítsd be a Binance API kulcsokat:
```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
```

### Docker build lassú

Első build lassú (Rust compiler, dependencies). Utána gyorsabb.

### Konténer nem indul

```bash
# Logok megnézése
docker logs bounce-scalper

# Vagy
docker-compose logs
```

---

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
| `errors` | Hibák |

Részletes API dokumentáció: [docs/MONGODB_API.md](docs/MONGODB_API.md)

---

## További dokumentáció

- [docs/BOUNCE_SCALPER.md](docs/BOUNCE_SCALPER.md) - Bounce Scalper stratégia részletei
- [docs/MONGODB_API.md](docs/MONGODB_API.md) - MongoDB API (NestJS fejlesztőknek)
