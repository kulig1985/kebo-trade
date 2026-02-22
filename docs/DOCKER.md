# Docker Futtatás

A Kebo Trade live trading Docker konténerben futtatható.

## Gyors Indítás

### 1. Konfiguráció

```bash
cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade

# .env fájl létrehozása
cp .env.example .env

# Szerkeszd a .env fájlt a saját API kulcsaiddal
nano .env
```

### 2. Build és Indítás

```bash
# Build (linux/amd64 platformra)
docker-compose build

# Indítás háttérben
docker-compose up -d

# Logok követése
docker-compose logs -f
```

### 3. Leállítás

```bash
# Graceful leállítás
docker-compose down

# Vagy: Stop (konténer megmarad)
docker-compose stop
```

## Részletes Parancsok

### Build

```bash
# Alap build
docker-compose build

# Tiszta build (cache nélkül)
docker-compose build --no-cache

# Csak image build (compose nélkül)
docker build --platform linux/amd64 -t kebo-trade:latest .
```

### Futtatás

```bash
# Háttérben (detached)
docker-compose up -d

# Előtérben (logok látszanak)
docker-compose up

# Újraindítás
docker-compose restart

# Állapot ellenőrzése
docker-compose ps
```

### Logok

```bash
# Összes log
docker-compose logs

# Valós idejű követés
docker-compose logs -f

# Utolsó 100 sor
docker-compose logs --tail=100

# Csak a bounce-scalper konténer
docker-compose logs -f bounce-scalper
```

### Leállítás

```bash
# Graceful shutdown (SIGTERM)
docker-compose down

# Stop (konténer megmarad)
docker-compose stop

# Erőltetett leállítás
docker-compose kill
```

### Debug

```bash
# Shell a konténerben
docker-compose exec bounce-scalper bash

# Python REPL a konténerben
docker-compose exec bounce-scalper python

# Konténer állapot
docker inspect bounce-scalper-live
```

## Konfiguráció

### Környezeti Változók (.env)

```env
# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true

# MongoDB
MONGODB_ENABLED=true

# Stratégia
STRATEGY_ID=bounce_scalper_live_001
USE_EXTERNAL_CONFIG=false

# Logging
LOG_LEVEL=INFO
```

### Külső Config Fájl

Ha `USE_EXTERNAL_CONFIG=true`, a stratégia paraméterek külső JSON fájlból olvashatók.

```bash
# Config könyvtár létrehozása
mkdir -p config

# Config fájl másolása
cp config/strategy.json.example config/strategy.json

# Szerkesztés
nano config/strategy.json
```

**config/strategy.json:**
```json
{
  "strategy_type": "bounce_scalper",
  "strategy_id": "bounce_scalper_live_001",
  "symbols": ["BTCUSDC", "ETHUSDC"],
  "parameters": {
    "trade_size_usdc": 10.0,
    "take_profit_pct": 1.5,
    "stop_loss_pct": 2.0
  }
}
```

**FONTOS:** Config módosítás után újra kell indítani a konténert!

```bash
docker-compose restart
```

## Platform Megjegyzések

### macOS → Linux

A Dockerfile `--platform linux/amd64`-ra épül, így macOS-en a buildelt image Linux szerveren fut.

```bash
# Build macOS-en
docker build --platform linux/amd64 -t kebo-trade:latest .

# Push registry-be
docker tag kebo-trade:latest your-registry/kebo-trade:latest
docker push your-registry/kebo-trade:latest

# Pull és futtatás Linux szerveren
docker pull your-registry/kebo-trade:latest
docker run --env-file .env your-registry/kebo-trade:latest
```

### Multi-arch Build

Ha ARM és AMD64 is kell:

```bash
# Buildx setup
docker buildx create --name multiarch --use

# Multi-platform build
docker buildx build --platform linux/amd64,linux/arm64 \
  -t kebo-trade:latest --push .
```

## Resource Limits

A `docker-compose.yml`-ben beállított limitek:

| Resource | Limit | Reservation |
|----------|-------|-------------|
| CPU | 2.0 cores | 0.5 cores |
| Memory | 2 GB | 512 MB |

Módosítás:

```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 4G
```

## Hibakeresés

### Konténer nem indul

```bash
# Logok ellenőrzése
docker-compose logs bounce-scalper

# Konténer státusz
docker-compose ps

# Exit code
docker inspect bounce-scalper-live --format='{{.State.ExitCode}}'
```

### MongoDB kapcsolat hiba

```bash
# Konténerből tesztelés
docker-compose exec bounce-scalper python -c "
from pymongo import AsyncMongoClient
import asyncio
async def test():
    client = AsyncMongoClient('mongodb://...')
    await client.admin.command('ping')
    print('OK')
asyncio.run(test())
"
```

### API kulcs hiba

```bash
# Env vars ellenőrzése
docker-compose exec bounce-scalper env | grep BINANCE
```

## Biztonsági Megjegyzések

1. **API kulcsok**: Soha ne commitold a `.env` fájlt git-be!
2. **Non-root**: A konténer `trader` userként fut (uid 1001)
3. **Read-only config**: A config volume `:ro` (read-only) mount
4. **Network isolation**: A konténer saját hálózaton fut

## Példa Workflow

```bash
# 1. Először TESTNET-en tesztelj!
echo "BINANCE_TESTNET=true" >> .env

# 2. Build
docker-compose build

# 3. Indítás
docker-compose up -d

# 4. Logok figyelése
docker-compose logs -f

# 5. Ha minden OK, leállítás
docker-compose down

# 6. LIVE módra váltás
sed -i 's/BINANCE_TESTNET=true/BINANCE_TESTNET=false/' .env

# 7. Újraindítás LIVE módban
docker-compose up -d
```
