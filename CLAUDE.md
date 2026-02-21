# CLAUDE.md

Ez a fájl útmutatást nyújt a Claude Code-nak a projektben való munkához.

## Projekt Áttekintés

**Bounce Scalper** - NautilusTrader alapú cryptocurrency trading robot.

- **Stratégia:** Mean Reversion (visszapattanás)
- **Piac:** Binance SPOT
- **Irány:** LONG only
- **Működés:** Sok kis trade, gyors profit

## Futtatás

```bash
cd /Users/kuligabor/git/kebo-trade-wrapper/kebo-trade

# Backtest
python run/run_backtest.py

# Live (TESTNET)
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"
export BINANCE_TESTNET="true"
python run/run_live.py

# Adat letöltés
cd data && python download_bounce_data.py
```

## Projekt Struktúra

```
kebo-trade/
├── strategies/
│   ├── bounce_scalper.py         # Stratégia
│   └── bounce_scalper_config.py  # Konfig
├── run/
│   ├── run_backtest.py           # Backtest
│   └── run_live.py               # Live
├── data/
│   ├── download_bounce_data.py   # Letöltő
│   └── bounce_data/              # CSV-k (gitignore!)
├── backtest_results/             # Riportok
├── README.md                     # Dokumentáció
├── CLAUDE.md                     # Ez a fájl
├── requirements.txt              # Függőségek
└── pyproject.toml                # Projekt konfig
```

## Stratégia Logika

```
Entry Band = EMA(20) - 0.8 × ATR(14)

VÁSÁRLÁS ha:
  - Előző close < Entry Band
  - Mostani close >= Entry Band

ELADÁS:
  - Take Profit: +1%
  - Stop Loss: -1.5%
```

## Paraméterek

| Paraméter | Érték |
|-----------|-------|
| trade_size_usdc | 5.0 |
| ema_period | 20 |
| atr_period | 14 |
| entry_atr_multiplier | 0.8 |
| take_profit_pct | 1.0 |
| stop_loss_pct | 1.5 |
| cooldown_ticks | 10 |

## Backtest Eredmények

- **Időszak:** 2025-01-01 - 2026-02-21
- **Profit:** +8.5%
- **Trade-ek:** ~32/nap

## Fontos

- CSV fájlok .gitignore-ban vannak
- API kulcsok környezeti változókban
- Először TESTNET-en tesztelj
