# Kebo Trade

NautilusTrader alapú cryptocurrency trading keretrendszer MongoDB persistence-el.

## Jellemzők

- **NautilusTrader** - Professzionális algorithmic trading framework
- **MongoDB Persistence** - Valós idejű adatmentés frontend-hez
- **Crash Recovery** - Automatikus szinkronizáció újraindításkor
- **Pluggable Stratégiák** - BaseStrategy-ből származtatott stratégiák
- **Kézi Beavatkozás Kezelés** - Külső cancel/fill érzékelése

## Gyors Indítás

### 1. Telepítés

```bash
cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade
pip install -r requirements.txt
```

### 2. Backtest

```bash
# Alapértelmezett (MongoDB nélkül)
python run/run_backtest.py

# MongoDB-vel
MONGODB_ENABLED=true python run/run_backtest.py
```

### 3. Live Trading

```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# TESTNET (ajánlott először!)
export BINANCE_TESTNET="true"
python run/run_live.py

# LIVE (VALÓS PÉNZ!)
export BINANCE_TESTNET="false"
python run/run_live.py
```

## Architektúra

```
┌──────────────────┐     ┌──────────────────┐
│  BounceScalper   │     │  Más Stratégia   │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         └────────────┬───────────┘
                      │ extends
         ┌────────────▼───────────┐
         │     BaseStrategy       │
         │  - MongoDB integration │
         │  - Event handlers      │
         └────────────┬───────────┘
                      │ uses
         ┌────────────▼───────────┐
         │   MongoDBPublisher     │
         │  - Async fire-and-forget│
         │  - Session tracking    │
         └────────────────────────┘
```

## Projekt Struktúra

```
kebo-trade/
├── persistence/                # MongoDB persistence layer
│   ├── config.py               # Konfiguráció
│   ├── publisher.py            # Async publisher
│   └── sync.py                 # Crash recovery sync
├── strategies/
│   ├── base_strategy.py        # Közös base class
│   ├── bounce_scalper.py       # Bounce Scalper stratégia
│   └── bounce_scalper_config.py
├── run/
│   ├── run_backtest.py         # Backtest
│   └── run_live.py             # Live trading
├── data/
│   └── download_bounce_data.py # Adat letöltő
├── docs/
│   └── BOUNCE_SCALPER.md       # Stratégia dokumentáció
└── backtest_results/           # Riportok
```

## Stratégiák

| Stratégia | Leírás | Dokumentáció |
|-----------|--------|--------------|
| Bounce Scalper | Mean Reversion scalping | [docs/BOUNCE_SCALPER.md](docs/BOUNCE_SCALPER.md) |

## MongoDB Collections

| Collection | Tartalom |
|------------|----------|
| `orders` | Összes order esemény |
| `fills` | Fill (teljesülés) események |
| `positions` | Pozíciók (OPEN/CLOSED) |
| `sessions` | Session tracking (crash recovery) |
| `balances` | Balance snapshots (live) |
| `heartbeat` | Stratégia heartbeat (live) |

## Környezeti Változók

| Változó | Leírás | Default |
|---------|--------|---------|
| `BINANCE_API_KEY` | Binance API kulcs | - |
| `BINANCE_API_SECRET` | Binance API secret | - |
| `BINANCE_TESTNET` | Testnet mód | "true" |
| `MONGODB_ENABLED` | MongoDB engedélyezése | "true" (live), "false" (backtest) |
| `MONGODB_URI` | Custom MongoDB URI | beépített |

## Új Stratégia Készítése

1. Hozz létre egy új fájlt `strategies/my_strategy.py`
2. Származtasd a `BaseStrategy`-ből
3. Implementáld a logikát (`on_bar`, `on_trade_tick`, stb.)
4. A MongoDB persistence automatikusan működik

```python
from strategies.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def on_bar(self, bar):
        # Stratégia logika
        if self.should_buy():
            order = self.order_factory.market(...)
            self.submit_order(order)
```

## Docker Futtatás

```bash
# Build (linux/amd64 platformra)
docker-compose build

# Indítás
docker-compose up -d

# Logok
docker-compose logs -f

# Leállítás
docker-compose down
```

Részletes dokumentáció: [docs/DOCKER.md](docs/DOCKER.md)

## Kockázatok

- **Downtrend:** Hosszú esés esetén a mean reversion stratégiák veszteségesek
- **Slippage:** Gyors mozgásoknál az ár elcsúszhat
- **API hibák:** Hálózati problémák esetén orderek elveszhetnek

## License

MIT
