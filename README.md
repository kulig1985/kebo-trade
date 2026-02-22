# Kebo Trade

NautilusTrader alapú cryptocurrency trading rendszer MongoDB persistence-el.

---

## Tartalomjegyzék

1. [Telepítés](#1-telepítés)
2. [Környezeti változók](#2-környezeti-változók)
3. [Backtest futtatása](#3-backtest-futtatása)
4. [Live trading futtatása](#4-live-trading-futtatása)
5. [Stratégia config kezelés](#5-stratégia-config-kezelés)
6. [Docker futtatás](#6-docker-futtatás)
7. [Több stratégia futtatása](#7-több-stratégia-futtatása)
8. [Webhook notification](#8-webhook-notification)
9. [MongoDB collections](#9-mongodb-collections)
10. [VPS Deployment](#10-vps-deployment)
11. [Hibaelhárítás](#11-hibaelhárítás)

---

## 1. Telepítés

```bash
cd kebo-trade
pip install -r requirements.txt
```

---

## 2. Környezeti változók

### 2.1 Összes változó

| Változó | Kötelező | Default | Leírás |
|---------|----------|---------|--------|
| `MONGODB_URI` | **IGEN** | - | MongoDB connection string |
| `MONGODB_ENABLED` | nem | `true` | MongoDB be/ki |
| `STRATEGY_ID` | **IGEN** | - | Egyedi stratégia azonosító |
| `BINANCE_API_KEY` | **IGEN** (live) | - | Binance API key |
| `BINANCE_API_SECRET` | **IGEN** (live) | - | Binance API secret |
| `BINANCE_TESTNET` | nem | `true` | Testnet mód |
| `WEBHOOK_URL` | nem | - | Backend notification URL |
| `WEBHOOK_SECRET` | nem | - | Webhook hitelesítő kulcs |
| `LOG_LEVEL` | nem | `INFO` | Log szint |

### 2.2 .env fájl létrehozása

```bash
# Példa fájl másolása
cp .env.example .env

# Szerkesztés
nano .env
```

### 2.3 .env fájl betöltése

**FONTOS:** A `.env` fájlt be kell tölteni a terminálban futtatás előtt!

```bash
# Betöltés
source .env

# Ellenőrzés
echo $STRATEGY_ID
```

### 2.4 Példa .env fájl tartalma

```bash
export MONGODB_URI="mongodb://user:password@host:27017/nautilus?authSource=admin"
export MONGODB_ENABLED="true"
export STRATEGY_ID="bounce_scalper_live_001"
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
export BINANCE_TESTNET="true"
export WEBHOOK_URL=""
export WEBHOOK_SECRET=""
export LOG_LEVEL="INFO"
```

---

## 3. Backtest futtatása

### 3.1 Egyszerű backtest (MongoDB nélkül)

```bash
# .env betöltése (STRATEGY_ID kell!)
source .env

# Vagy MONGODB_ENABLED kikapcsolása
export MONGODB_ENABLED="false"

# Futtatás
python run/run_backtest.py
```

### 3.2 Backtest MongoDB-vel

Ha szeretnéd, hogy a backtest eredmények MongoDB-be kerüljenek:

```bash
source .env
export MONGODB_ENABLED="true"
python run/run_backtest.py
```

### 3.3 Backtest-hez külön .env

Használd a `env-examples/backtest.env.example` fájlt:

```bash
# Másold és szerkeszd
cp env-examples/backtest.env.example backtest.env
nano backtest.env

# Betöltés és futtatás
source backtest.env
python run/run_backtest.py
```

### 3.4 Backtest paraméterek módosítása

Szerkeszd a `run/run_backtest.py` fájlt (70-90. sorok körül):

```python
SYMBOLS = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
START_DATE = "20251101"
END_DATE = "20260221"
STARTING_USDC = 1000.0
```

---

## 4. Live trading futtatása

### 4.1 Előkészületek

1. Hozd létre a `.env` fájlt
2. Állítsd be a Binance API kulcsokat
3. Állítsd be a MongoDB URI-t
4. Válassz egyedi STRATEGY_ID-t

### 4.2 Testnet futtatás (ajánlott először!)

```bash
# .env fájl tartalma:
# export BINANCE_TESTNET="true"

source .env
python run/run_live.py
```

### 4.3 Éles futtatás (VALÓS PÉNZ!)

```bash
# .env fájlban:
# export BINANCE_TESTNET="false"

source .env
python run/run_live.py
```

### 4.4 Leállítás

`Ctrl+C` - graceful shutdown, menti az állapotot MongoDB-be.

---

## 5. Stratégia config kezelés

A stratégia paramétereket MongoDB-ben tárolhatod (`strategy_configs` collection).

### 5.1 MONGODB_URI beállítása

Minden config parancs előtt kell!

```bash
source .env
# vagy
export MONGODB_URI="mongodb://user:pass@host:27017/nautilus?authSource=admin"
```

### 5.2 Default config feltöltése

```bash
python run/manage_config.py upload bounce_scalper_live_001
```

### 5.3 Custom config feltöltése JSON-ból

Hozz létre JSON fájlt (pl. `my_config.json`):

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

Feltöltés:

```bash
python run/upload_config.py my_config.json
```

### 5.4 Interaktív config létrehozás

```bash
python run/upload_config.py --interactive
```

### 5.5 Configok listázása

```bash
python run/manage_config.py list
```

### 5.6 Config lekérése

```bash
python run/manage_config.py get my_btc_scalper
```

### 5.7 Ha nincs config a DB-ben

A rendszer a beépített default értékeket használja automatikusan.

---

## 6. Docker futtatás

### 6.1 Mikor kell `--build`?

| Változás | Parancs |
|----------|---------|
| `docker.env` módosítás | `docker-compose up -d` |
| Python kód (`*.py`) | `docker-compose up -d --build` |
| `requirements.txt` | `docker-compose up -d --build` |
| `Dockerfile` | `docker-compose up -d --build` |
| `git pull` | `docker-compose up -d --build` |

**Egyszerűen:** Ha csak a `docker.env` változott → NEM kell `--build`. Minden más → KELL `--build`.

### 6.2 Első indítás

```bash
cp env-examples/docker.env.example docker.env
nano docker.env
docker-compose up -d --build
```

### 6.3 Logok

```bash
docker-compose logs -f
```

### 6.4 Leállítás

```bash
docker-compose down
```

### 6.5 Újraindítás

```bash
docker-compose up -d
```

### 6.6 Config módosítás után

```bash
nano docker.env
docker-compose up -d
```

### 6.7 Kód módosítás után (git pull)

```bash
docker-compose up -d --build
```

### 6.7 docker.env formátum

```bash
MONGODB_URI=mongodb://user:pass@host:27017/nautilus?authSource=admin
STRATEGY_ID=bounce_scalper_001
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true
WEBHOOK_URL=
WEBHOOK_SECRET=
LOG_LEVEL=INFO
```

**NEM kell `export`!**

---

## 7. Több stratégia futtatása

Minden stratégiának **külön STRATEGY_ID** és **külön process/konténer** kell!

### 7.1 Python - külön terminálokban

**Terminal 1:**
```bash
source bounce-001.env
python run/run_live.py
```

**Terminal 2:**
```bash
source bounce-002.env
python run/run_live.py
```

### 7.2 Python - háttérben

```bash
# Stratégia 1 háttérben
source bounce-001.env && python run/run_live.py &

# Stratégia 2 háttérben
source bounce-002.env && python run/run_live.py &

# Folyamatok listázása
jobs

# Leállítás
kill %1  # első
kill %2  # második
```

### 7.3 Docker - külön konténerek

Minden stratégiához külön env fájl:

**docker-001.env:**
```
MONGODB_URI=mongodb://user:pass@host:27017/nautilus?authSource=admin
STRATEGY_ID=bounce_scalper_001
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true
```

**docker-002.env:**
```
MONGODB_URI=mongodb://user:pass@host:27017/nautilus?authSource=admin
STRATEGY_ID=bounce_scalper_002
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true
```

Indítás:

```bash
docker run -d --name bounce-001 --env-file docker-001.env kebo-trade:latest
docker run -d --name bounce-002 --env-file docker-002.env kebo-trade:latest
```

### 7.4 docker-compose.multi.yml használata

**Előkészület:** Hozz létre két env fájlt!

1. `docker-001.env` (STRATEGY_ID=bounce_scalper_001)
2. `docker-002.env` (STRATEGY_ID=bounce_scalper_002)

Lásd: `env-examples/docker-001.env.example` és `docker-002.env.example`

```bash
# Indítás
docker-compose -f docker-compose.multi.yml up -d

# Logok
docker-compose -f docker-compose.multi.yml logs -f

# Csak egy stratégia logjait
docker logs -f bounce-001
docker logs -f bounce-002

# Leállítás
docker-compose -f docker-compose.multi.yml down
```

---

## 8. Webhook notification

### 8.1 Mi ez?

Ha be van állítva `WEBHOOK_URL`, minden MongoDB írás után HTTP POST megy a megadott URL-re.

**FONTOS:** Webhook **csak LIVE módban** működik! Backtest-ben automatikusan ki van kapcsolva (túl sok esemény lenne).

Használat: A NestJS backend fogadja és WebSocket-en továbbítja a frontendnek.

### 8.2 Beállítás

.env fájlban:
```bash
export WEBHOOK_URL="http://your-backend:3000/api/trading/webhook"
export WEBHOOK_SECRET="your_secret_key_here"
```

**FONTOS:** A `WEBHOOK_SECRET` értékének PONTOSAN meg kell egyeznie a backend `.env` fájljában beállított értékkel!

Docker-ben:
```bash
docker run \
  -e WEBHOOK_URL="http://backend:3000/api/trading/webhook" \
  -e WEBHOOK_SECRET="your_secret_key_here" \
  ...
```

### 8.3 Hitelesítés

A robot minden webhook kéréshez hozzáadja az `X-Webhook-Secret` header-t:

```
POST /api/trading/webhook
Content-Type: application/json
X-Webhook-Secret: your_secret_key_here
```

A backend ellenőrzi ezt a header-t, és elutasítja a kérést ha nem egyezik.

### 8.4 Webhook payload

```json
{
  "event": "orders",
  "collection": "orders",
  "strategy_id": "bounce_scalper_001",
  "session_id": "uuid...",
  "is_backtest": false,
  "timestamp": "2026-02-22T12:00:00.000Z",
  "data": { ... }
}
```

### 8.5 Event típusok

| Event | Mikor |
|-------|-------|
| `orders` | Új order |
| `order_update` | Order státusz változás |
| `fills` | Order teljesülés |
| `positions` | Pozíció nyitás |
| `position_update` | Pozíció zárás |
| `balances` | Balance snapshot (~60 sec) |
| `heartbeat` | Heartbeat (~30 sec) |
| `errors` | Hiba |

---

## 9. MongoDB collections

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

Részletes dokumentáció: [docs/MONGODB_API.md](docs/MONGODB_API.md)

---

## 10. VPS Deployment

### 10.1 Docker telepítése (egyszer)

```bash
sudo apt update && sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
# Logout/login kell utána!
```

### 10.2 Kód feltöltése

```bash
git clone https://github.com/YOUR_USERNAME/kebo-trade.git
cd kebo-trade
```

### 10.3 Első indítás

```bash
cp env-examples/docker.env.example docker.env
nano docker.env
docker-compose up -d --build
```

### 10.4 Logok

```bash
docker-compose logs -f
```

### 10.5 Leállítás

```bash
docker-compose down
```

### 10.6 Újraindítás

```bash
docker-compose up -d
```

### 10.7 Frissítés (git pull után)

```bash
git pull origin develop
docker-compose up -d --build
```

### 10.8 Több stratégia

```bash
nano docker-001.env
nano docker-002.env
docker-compose -f docker-compose.multi.yml up -d --build
```

---

## 11. Hibaelhárítás

### "MONGODB_URI not set!"

```bash
# Ellenőrizd hogy be van-e töltve
echo $MONGODB_URI

# Ha üres, töltsd be
source .env
```

### "MongoDB connection failed"

- Ellenőrizd a connection string-et
- Speciális karakterek URL encode-olva? (`+` → `%2B`)
- MongoDB szerver fut?

### "BINANCE_API_KEY required"

```bash
# Ellenőrizd
echo $BINANCE_API_KEY

# Ha üres
source .env
```

### Docker konténer nem indul

```bash
docker logs bounce-scalper
```

### .env nem töltődik be

**Python-hoz (source paranccsal):**
```bash
# A fájlban "export" kell minden sor elé!
export MONGODB_URI="..."
```

**Docker-hez (--env-file):**
```bash
# A fájlban NEM kell "export"!
MONGODB_URI=...
```

---

## Példa fájlok

| Fájl | Leírás |
|------|--------|
| `.env.example` | Alap .env minta |
| `env-examples/bounce-001.env.example` | Stratégia 1 |
| `env-examples/bounce-002.env.example` | Stratégia 2 |
| `env-examples/backtest.env.example` | Backtest |
| `example_config.json` | Stratégia config JSON |
| `docker-compose.yml` | Egy stratégia |
| `docker-compose.multi.yml` | Több stratégia |

---

## További dokumentáció

- [docs/BOUNCE_SCALPER.md](docs/BOUNCE_SCALPER.md) - Bounce Scalper stratégia
- [docs/MONGODB_API.md](docs/MONGODB_API.md) - MongoDB API (NestJS fejlesztőknek)
