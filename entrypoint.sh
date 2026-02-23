#!/bin/bash
# Kebo Trade - Docker Entrypoint
#
# Ez a script biztosítja, hogy a Python process megkapja a SIGTERM/SIGINT
# jeleket és graceful shutdown-t hajtson végre (orderek törlése).
#
# FONTOS: Használj `docker stop` parancsot (nem `docker kill`)!

set -e

echo "========================================"
echo "KEBO TRADE - Live Trading"
echo "========================================"
echo "Trading Mode: ${TRADING_MODE:-spot}"
echo "Strategy Type: ${STRATEGY_TYPE:-bounce_scalper}"
echo "========================================"

# Determine which runner to use
if [ "$TRADING_MODE" = "futures" ]; then
    if [ "$STRATEGY_TYPE" = "grid" ] || [ "$STRATEGY_TYPE" = "grid_strategy" ]; then
        echo "Starting: Grid Strategy (Futures USDC Margin)"
        exec python run/run_live_grid.py
    else
        echo "Starting: Bounce Scalper (Futures USDC Margin)"
        exec python run/run_live_futures.py
    fi
else
    echo "Starting: Bounce Scalper (Spot)"
    exec python run/run_live.py
fi
