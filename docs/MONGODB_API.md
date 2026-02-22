# MongoDB API Specifikáció

NestJS backend fejlesztőknek szóló dokumentáció a trading rendszer MongoDB collection-jeiről és webhook integrációról.

## Kapcsolat

```
URI: Környezeti változóban (MONGODB_URI)
Database: nautilus
```

---

## Collection-ök Áttekintése

| Collection | Leírás | Frissítési gyakoriság |
|------------|--------|----------------------|
| `strategy_configs` | Stratégia konfigurációk | Manuális (admin) |
| `orders` | Order események | Minden order küldésnél |
| `fills` | Fill (teljesülés) események | Minden fill-nél |
| `positions` | Pozíciók (nyitott/zárt) | Nyitás/zárás |
| `sessions` | Trading session-ök | Indítás/leállítás |
| `balances` | Balance snapshot-ok | ~60 másodpercenként (live) |
| `heartbeat` | Stratégia heartbeat | ~30 másodpercenként (live) |
| `errors` | Hibák és figyelmeztetések | Hiba esetén |

---

## Webhook Notification

A Python trading rendszer minden DB írás után HTTP POST-ot küld a backend-nek.

### Konfiguráció (Python oldalon)

```bash
export WEBHOOK_URL="http://your-nestjs-backend:3000/api/trading/webhook"
```

### Webhook Payload

```typescript
interface WebhookPayload {
  event: string;          // Event típus: "orders", "order_update", "fills", stb.
  collection: string;     // MongoDB collection neve
  strategy_id: string;    // Stratégia azonosító
  session_id: string;     // Session UUID
  is_backtest: boolean;   // true = backtest, false = live
  timestamp: string;      // ISO 8601 formátum
  data: object;           // Az esemény adatai
}
```

### Event típusok

| Event | Collection | Mikor |
|-------|------------|-------|
| `orders` | orders | Új order küldésekor |
| `order_update` | orders | Order státusz változáskor |
| `fills` | fills | Order teljesülésekor |
| `positions` | positions | Pozíció nyitáskor |
| `position_update` | positions | Pozíció záráskor/változáskor |
| `balances` | balances | Balance snapshot (~60 sec) |
| `heartbeat` | heartbeat | Heartbeat (~30 sec) |
| `errors` | errors | Hiba/figyelmeztetés esetén |

### NestJS Controller Példa

```typescript
import { Controller, Post, Body, HttpCode } from '@nestjs/common';

interface WebhookPayload {
  event: string;
  collection: string;
  strategy_id: string;
  session_id: string;
  is_backtest: boolean;
  timestamp: string;
  data: any;
}

@Controller('api/trading')
export class TradingWebhookController {
  constructor(private readonly wsGateway: TradingGateway) {}

  @Post('webhook')
  @HttpCode(200)
  async handleWebhook(@Body() payload: WebhookPayload) {
    // Webhook fogadása és továbbítás WebSocket-en a frontendeknek
    this.wsGateway.broadcast(payload.strategy_id, {
      type: payload.event,
      data: payload.data,
      timestamp: payload.timestamp,
    });

    return { received: true };
  }
}
```

### WebSocket Gateway Példa

```typescript
import { WebSocketGateway, WebSocketServer } from '@nestjs/websockets';
import { Server } from 'socket.io';

@WebSocketGateway({ cors: true })
export class TradingGateway {
  @WebSocketServer()
  server: Server;

  broadcast(strategyId: string, data: any) {
    // Összes kliens értesítése aki erre a stratégiára subscribed
    this.server.to(`strategy:${strategyId}`).emit('trading_event', data);
  }
}
```

---

## Közös Mezők

Minden dokumentum tartalmazza:

```typescript
interface BaseDocument {
  _id: ObjectId;
  strategy_type: string;    // pl. "bounce_scalper"
  strategy_id: string;      // pl. "bounce_scalper_live_001"
  is_backtest: boolean;
  session_id: string;       // UUID
}
```

---

## 1. `strategy_configs` Collection

Stratégia konfigurációk tárolása.

### Séma

```typescript
interface StrategyConfig {
  _id: ObjectId;
  strategy_id: string;        // Egyedi azonosító (pl. "bounce_scalper_live_001")
  strategy_type: string;      // Stratégia típus (pl. "bounce_scalper")
  symbols: string[];          // Tradelt szimbólumok (pl. ["BTCUSDC", "ETHUSDC"])
  parameters: {
    trade_size_usdc: number;
    max_positions_per_instrument: number;
    take_profit_pct: number;
    stop_loss_pct: number;
    ema_period: number;
    atr_period: number;
    entry_atr_multiplier: number;
    exit_atr_multiplier?: number;
    min_free_balance_usdc: number;
    cooldown_ticks: number;
    // ... stratégia-specifikus paraméterek
  };
  created_at?: Date;
  updated_at?: Date;
}
```

### Indexek

```javascript
db.strategy_configs.createIndex({ "strategy_id": 1 }, { unique: true })
```

### Példa Dokumentum

```json
{
  "_id": "65d8a1b2c3d4e5f6a7b8c9d0",
  "strategy_id": "bounce_scalper_live_001",
  "strategy_type": "bounce_scalper",
  "symbols": ["BTCUSDC", "ETHUSDC", "SOLUSDC"],
  "parameters": {
    "trade_size_usdc": 5.0,
    "max_positions_per_instrument": 1,
    "take_profit_pct": 1.0,
    "stop_loss_pct": 1.5,
    "ema_period": 20,
    "atr_period": 14,
    "entry_atr_multiplier": 0.8,
    "exit_atr_multiplier": null,
    "min_free_balance_usdc": 10.0,
    "cooldown_ticks": 10
  }
}
```

### NestJS Schema

```typescript
import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { Document } from 'mongoose';

@Schema({ collection: 'strategy_configs', timestamps: true })
export class StrategyConfig extends Document {
  @Prop({ required: true, unique: true, index: true })
  strategy_id: string;

  @Prop({ required: true })
  strategy_type: string;

  @Prop({ type: [String], required: true })
  symbols: string[];

  @Prop({ type: Object, required: true })
  parameters: Record<string, any>;
}

export const StrategyConfigSchema = SchemaFactory.createForClass(StrategyConfig);
```

---

## 2. `orders` Collection

Order események.

### Séma

```typescript
interface Order extends BaseDocument {
  client_order_id: string;
  venue_order_id?: string;
  instrument_id: string;
  order_side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT" | "STOP_MARKET" | "STOP_LIMIT";
  quantity: number;
  price?: number;
  status: "SUBMITTED" | "ACCEPTED" | "FILLED" | "CANCELED" | "REJECTED" | "SYNC_CLOSED";
  reduce_only: boolean;
  external_action?: boolean;
  reason?: string;
  submitted_at: Date;
  updated_at: Date;
  ts_event: number;
}
```

### Státusz Életciklus

```
SUBMITTED → ACCEPTED → FILLED
                    → CANCELED
         → REJECTED
         → SYNC_CLOSED (crash recovery)
```

### Indexek

```javascript
db.orders.createIndex({ "strategy_id": 1, "client_order_id": 1 }, { unique: true })
db.orders.createIndex({ "strategy_id": 1, "status": 1 })
db.orders.createIndex({ "session_id": 1 })
db.orders.createIndex({ "submitted_at": -1 })
```

---

## 3. `fills` Collection

Order teljesülések.

### Séma

```typescript
interface Fill extends BaseDocument {
  fill_id?: string;
  client_order_id: string;
  venue_order_id?: string;
  instrument_id: string;
  order_side: "BUY" | "SELL";
  quantity: number;
  price: number;
  commission: number;
  liquidity_side?: "MAKER" | "TAKER";
  filled_at: Date;
  ts_event: number;
}
```

### Indexek

```javascript
db.fills.createIndex({ "strategy_id": 1, "client_order_id": 1 })
db.fills.createIndex({ "session_id": 1 })
db.fills.createIndex({ "filled_at": -1 })
```

---

## 4. `positions` Collection

Pozíciók.

### Séma

```typescript
interface Position extends BaseDocument {
  position_id: string;
  instrument_id: string;
  side: "LONG" | "SHORT";
  quantity: number;
  avg_open_price: number;
  avg_close_price?: number;
  realized_pnl?: number;
  status: "OPEN" | "CLOSED" | "SYNC_RECOVERY";
  opened_at: Date;
  closed_at?: Date;
  updated_at?: Date;
  duration_seconds?: number;
  ts_event: number;
}
```

### Indexek

```javascript
db.positions.createIndex({ "strategy_id": 1, "position_id": 1 }, { unique: true })
db.positions.createIndex({ "strategy_id": 1, "status": 1 })
db.positions.createIndex({ "session_id": 1 })
```

---

## 5. `sessions` Collection

Trading session-ök.

### Séma

```typescript
interface Session extends BaseDocument {
  started_at: Date;
  ended_at?: Date;
  end_reason?: "NORMAL" | "ERROR" | "CRASH_RECOVERY";
  recovered_from?: string;
  state_snapshot?: object;
  open_positions?: string[];
  open_orders?: string[];
}
```

### Indexek

```javascript
db.sessions.createIndex({ "session_id": 1 }, { unique: true })
db.sessions.createIndex({ "strategy_id": 1, "started_at": -1 })
```

---

## 6. `balances` Collection

Balance snapshot-ok (csak live).

### Séma

```typescript
interface Balance extends BaseDocument {
  balances: Array<{
    currency: string;
    total: number;
    free: number;
    locked: number;
  }>;
  total_equity_usdc: number;
  open_positions_count: number;
  timestamp: Date;
}
```

### Indexek

```javascript
db.balances.createIndex({ "strategy_id": 1, "timestamp": -1 })
```

---

## 7. `heartbeat` Collection

Stratégia heartbeat (csak live).

### Séma

```typescript
interface Heartbeat extends BaseDocument {
  status: "RUNNING" | "STOPPED" | "ERROR";
  uptime_seconds: number;
  state?: {
    active_positions: number;
    instruments_tracked: number;
    instruments_in_cooldown: number;
  };
  timestamp: Date;
}
```

### Viselkedés

- **Upsert**: 1 dokumentum/session
- **Frissítés**: ~30 másodpercenként

### Indexek

```javascript
db.heartbeat.createIndex({ "session_id": 1 }, { unique: true })
```

---

## 8. `errors` Collection

Hibák és figyelmeztetések.

### Séma

```typescript
interface TradingError extends BaseDocument {
  level: "INFO" | "WARNING" | "ERROR";
  source: "STRATEGY" | "EXCHANGE" | "SYSTEM";
  message: string;
  timestamp: Date;
}
```

### Indexek

```javascript
db.errors.createIndex({ "strategy_id": 1, "timestamp": -1 })
db.errors.createIndex({ "level": 1 })
```

---

## Gyakori Query-k

### Aktív session

```javascript
db.sessions.findOne({ strategy_id: "bounce_scalper_live_001", ended_at: null })
```

### Nyitott pozíciók

```javascript
db.positions.find({ strategy_id: "bounce_scalper_live_001", status: "OPEN" })
```

### Realizált P&L összesítés

```javascript
db.positions.aggregate([
  { $match: { strategy_id: "bounce_scalper_live_001", status: "CLOSED", is_backtest: false } },
  { $group: { _id: "$instrument_id", total_pnl: { $sum: "$realized_pnl" }, trade_count: { $sum: 1 } } }
])
```

### Config lekérése

```javascript
db.strategy_configs.findOne({ strategy_id: "bounce_scalper_live_001" })
```

---

## Megjegyzések

1. **Backtest vs Live**: `is_backtest` mező alapján szűrhető
2. **Webhook**: Fire-and-forget, 2 sec timeout, nem retry-ol
3. **Heartbeat/Balance**: Csak live trading-nél generálódik
4. **SYNC_CLOSED/SYNC_RECOVERY**: Crash recovery után lezárt elemek
