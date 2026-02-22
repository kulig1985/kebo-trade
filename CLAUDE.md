# CLAUDE.md

Ez a fájl útmutatást nyújt a Claude Code-nak a projektben való munkához.

## Projekt Áttekintés

**Kebo Trade** - NautilusTrader alapú cryptocurrency trading keretrendszer MongoDB persistence-el.

- **Keretrendszer:** NautilusTrader
- **Piac:** Binance SPOT
- **Adatbázis:** MongoDB (PyMongo Async API)
- **Stratégiák:** Pluggable (BaseStrategy-ből származnak)

## Architektúra

```
┌─────────────────────────────────────────────────────────────────┐
│                      Trading Stratégia                          │
│                    (pl. BounceScalper)                          │
└────────────────────────────┬────────────────────────────────────┘
                             │ extends
┌────────────────────────────▼────────────────────────────────────┐
│                       BaseStrategy                               │
│  - MongoDB persistence (orders, fills, positions)               │
│  - Kézi beavatkozás kezelés                                     │
│  - State save/restore                                            │
└────────────────────────────┬────────────────────────────────────┘
                             │ uses
┌────────────────────────────▼────────────────────────────────────┐
│                    MongoDBPublisher                              │
│  - Fire-and-forget async queue                                  │
│  - Háttér workerek (nem blokkolja a stratégiát)                │
│  - Session tracking                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Projekt Struktúra

```
kebo-trade/
├── persistence/                    # MongoDB persistence layer
│   ├── __init__.py
│   ├── config.py                   # MongoDBConfig
│   ├── publisher.py                # MongoDBPublisher (async)
│   └── sync.py                     # MongoDBSyncService (crash recovery)
├── strategies/
│   ├── base_strategy.py            # Közös base class
│   ├── bounce_scalper.py           # Bounce Scalper stratégia
│   └── bounce_scalper_config.py    # Bounce Scalper konfig
├── run/
│   ├── run_backtest.py             # Backtest futtatás
│   └── run_live.py                 # Live trading
├── data/
│   ├── download_bounce_data.py     # Adat letöltő
│   └── bounce_data/                # CSV-k (gitignore!)
├── backtest_results/               # Riportok
├── docs/
│   └── BOUNCE_SCALPER.md           # Bounce Scalper dokumentáció
├── README.md                       # Projekt dokumentáció
├── CLAUDE.md                       # Ez a fájl
├── requirements.txt                # Függőségek
└── pyproject.toml                  # Projekt konfig
```

## Futtatás

```bash
cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade

# Backtest (MongoDB kikapcsolva alapból)
python run/run_backtest.py

# Backtest MongoDB-vel
MONGODB_ENABLED=true python run/run_backtest.py

# Live (TESTNET)
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"
export BINANCE_TESTNET="true"
python run/run_live.py

# Live (VALÓS PÉNZ!)
export BINANCE_TESTNET="false"
python run/run_live.py
```

## MongoDB Konfiguráció

**Connection string:** Környezeti változóban (`MONGODB_URI`)

**Collections:**
| Collection | Tartalom |
|------------|----------|
| `orders` | Order események |
| `fills` | Fill események |
| `positions` | Pozíciók (OPEN/CLOSED) |
| `sessions` | Session tracking |
| `balances` | Balance snapshots (live) |
| `heartbeat` | Heartbeat (live) |
| `errors` | Hibák/figyelmeztetések |

**Környezeti változók:**
- `MONGODB_URI` - Custom connection string
- `MONGODB_ENABLED` - "true"/"false" (backtest-nél alapból false)

## Új Stratégia Létrehozása

```python
from strategies.base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)

    def on_bar(self, bar):
        # Stratégia logika
        pass

    def _get_balance_snapshot(self) -> dict:
        # Balance adatok (live heartbeat-hez)
        return {"total_usdc": 1000.0}

    def _get_heartbeat_data(self) -> dict:
        # Stratégia állapot (live heartbeat-hez)
        return {"active_positions": 2}
```

## Fontos

- CSV fájlok .gitignore-ban vannak
- API kulcsok környezeti változókban
- Először TESTNET-en tesztelj
- MongoDB: PyMongo Async API (Motor deprecated 2026 májusában)
- A stratégia SOHA nem blokkolódik DB írásra (fire-and-forget queue)
