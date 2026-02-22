# MongoDB API Specifikáció

NestJS backend fejlesztőknek szóló dokumentáció a trading rendszer MongoDB collection-jeiről.

## Kapcsolat

```
URI: Környezeti változóban (MONGODB_URI)
Database: nautilus
```

## Collection-ök Áttekintése

| Collection | Leírás | Frissítési gyakoriság |
|------------|--------|----------------------|
| `orders` | Order események | Minden order küldésnél |
| `fills` | Fill (teljesülés) események | Minden fill-nél |
| `positions` | Pozíciók (nyitott/zárt) | Nyitás/zárás |
| `sessions` | Trading session-ök | Indítás/leállítás |
| `balances` | Balance snapshot-ok | ~60 másodpercenként (live) |
| `heartbeat` | Stratégia heartbeat | ~30 másodpercenként (live) |
| `errors` | Hibák és figyelmeztetések | Hiba esetén |

---

## Közös Mezők

Minden dokumentum tartalmazza ezeket a mezőket:

```typescript
interface BaseDocument {
  _id: ObjectId;

  // Stratégia azonosítás
  strategy_type: string;    // pl. "bounce_scalper"
  strategy_id: string;      // pl. "bounce_scalper_live_001"

  // Környezet
  is_backtest: boolean;     // true = backtest, false = live
  session_id: string;       // UUID - egyedi session azonosító
}
```

---

## 1. `orders` Collection

Order események - minden küldött order.

### Séma

```typescript
interface Order extends BaseDocument {
  // Azonosítók
  client_order_id: string;      // Kliens oldali order ID (egyedi)
  venue_order_id?: string;      // Tőzsde oldali order ID (ACCEPTED után)

  // Order adatok
  instrument_id: string;        // pl. "BTCUSDC.BINANCE"
  order_side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT" | "STOP_MARKET" | "STOP_LIMIT";
  quantity: number;             // Mennyiség (base currency-ben)
  price?: number;               // Ár (LIMIT order esetén)

  // Státusz
  status: "SUBMITTED" | "ACCEPTED" | "FILLED" | "CANCELED" | "REJECTED" | "SYNC_CLOSED";
  reduce_only: boolean;         // true = csak pozíció zárás

  // Kézi beavatkozás
  external_action?: boolean;    // true = kézzel törölték/módosították
  reason?: string;              // Reject/cancel ok

  // Időbélyegek
  submitted_at: Date;           // Order küldés ideje
  updated_at: Date;             // Utolsó frissítés
  ts_event: number;             // NautilusTrader nanosec timestamp
}
```

### Státusz Életciklus

```
SUBMITTED → ACCEPTED → FILLED
                    → CANCELED (stratégia vagy kézi)
         → REJECTED (tőzsde elutasította)
         → SYNC_CLOSED (crash recovery után)
```

### Indexek (ajánlott)

```javascript
db.orders.createIndex({ "strategy_id": 1, "client_order_id": 1 }, { unique: true })
db.orders.createIndex({ "strategy_id": 1, "status": 1 })
db.orders.createIndex({ "session_id": 1 })
db.orders.createIndex({ "submitted_at": -1 })
db.orders.createIndex({ "instrument_id": 1, "status": 1 })
```

### Példa Dokumentum

```json
{
  "_id": "65d8a1b2c3d4e5f6a7b8c9d0",
  "strategy_type": "bounce_scalper",
  "strategy_id": "bounce_scalper_live_001",
  "is_backtest": false,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",

  "client_order_id": "O-20260221-123456-001",
  "venue_order_id": "12345678",
  "instrument_id": "BTCUSDC.BINANCE",
  "order_side": "BUY",
  "order_type": "MARKET",
  "quantity": 0.00005,
  "price": null,
  "status": "FILLED",
  "reduce_only": false,

  "submitted_at": "2026-02-21T12:00:00.000Z",
  "updated_at": "2026-02-21T12:00:01.500Z",
  "ts_event": 1740142800000000000
}
```

---

## 2. `fills` Collection

Fill események - order teljesülések.

### Séma

```typescript
interface Fill extends BaseDocument {
  // Azonosítók
  fill_id?: string;             // Trade ID a tőzsdétől
  client_order_id: string;      // Kapcsolódó order
  venue_order_id?: string;      // Tőzsde order ID

  // Fill adatok
  instrument_id: string;
  order_side: "BUY" | "SELL";
  quantity: number;             // Teljesült mennyiség
  price: number;                // Teljesülési ár
  commission: number;           // Jutalék (quote currency-ben)
  liquidity_side?: "MAKER" | "TAKER";

  // Időbélyegek
  filled_at: Date;
  ts_event: number;
}
```

### Indexek (ajánlott)

```javascript
db.fills.createIndex({ "strategy_id": 1, "fill_id": 1 })
db.fills.createIndex({ "strategy_id": 1, "client_order_id": 1 })
db.fills.createIndex({ "session_id": 1 })
db.fills.createIndex({ "filled_at": -1 })
db.fills.createIndex({ "instrument_id": 1 })
```

### Példa Dokumentum

```json
{
  "_id": "65d8a1b2c3d4e5f6a7b8c9d1",
  "strategy_type": "bounce_scalper",
  "strategy_id": "bounce_scalper_live_001",
  "is_backtest": false,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",

  "fill_id": "987654321",
  "client_order_id": "O-20260221-123456-001",
  "venue_order_id": "12345678",
  "instrument_id": "BTCUSDC.BINANCE",
  "order_side": "BUY",
  "quantity": 0.00005,
  "price": 95000.50,
  "commission": 0.00475,
  "liquidity_side": "TAKER",

  "filled_at": "2026-02-21T12:00:01.500Z",
  "ts_event": 1740142801500000000
}
```

---

## 3. `positions` Collection

Pozíciók - nyitott és zárt.

### Séma

```typescript
interface Position extends BaseDocument {
  // Azonosítók
  position_id: string;          // NautilusTrader position ID
  instrument_id: string;

  // Pozíció adatok
  side: "LONG" | "SHORT";
  quantity: number;             // Mennyiség
  avg_open_price: number;       // Átlagos nyitási ár
  avg_close_price?: number;     // Átlagos zárási ár (CLOSED esetén)

  // P&L
  realized_pnl?: number;        // Realizált profit/loss (quote currency)

  // Státusz
  status: "OPEN" | "CLOSED" | "SYNC_RECOVERY";

  // Időbélyegek
  opened_at: Date;
  closed_at?: Date;             // Zárás időpontja
  updated_at?: Date;
  duration_seconds?: number;    // Pozíció tartama másodpercben

  ts_event: number;
}
```

### Státusz

| Státusz | Leírás |
|---------|--------|
| `OPEN` | Aktív, nyitott pozíció |
| `CLOSED` | Lezárt pozíció (TP/SL/manual) |
| `SYNC_RECOVERY` | Crash recovery után lezárt |

### Indexek (ajánlott)

```javascript
db.positions.createIndex({ "strategy_id": 1, "position_id": 1 }, { unique: true })
db.positions.createIndex({ "strategy_id": 1, "status": 1 })
db.positions.createIndex({ "session_id": 1 })
db.positions.createIndex({ "opened_at": -1 })
db.positions.createIndex({ "instrument_id": 1, "status": 1 })
```

### Példa Dokumentum

```json
{
  "_id": "65d8a1b2c3d4e5f6a7b8c9d2",
  "strategy_type": "bounce_scalper",
  "strategy_id": "bounce_scalper_live_001",
  "is_backtest": false,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",

  "position_id": "P-BTCUSDC-001",
  "instrument_id": "BTCUSDC.BINANCE",
  "side": "LONG",
  "quantity": 0.00005,
  "avg_open_price": 95000.50,
  "avg_close_price": 95950.25,
  "realized_pnl": 0.0475,
  "status": "CLOSED",

  "opened_at": "2026-02-21T12:00:01.500Z",
  "closed_at": "2026-02-21T12:15:30.000Z",
  "duration_seconds": 928.5,
  "ts_event": 1740143730000000000
}
```

---

## 4. `sessions` Collection

Trading session-ök - indítás/leállítás nyomon követése.

### Séma

```typescript
interface Session extends BaseDocument {
  // Session azonosítás (session_id a BaseDocument-ben)

  // Időbélyegek
  started_at: Date;
  ended_at?: Date;              // null = még fut

  // Leállítás oka
  end_reason?: "NORMAL" | "ERROR" | "CRASH_RECOVERY";

  // Recovery info
  recovered_from?: string;      // Előző session_id, ha recovery
  state_snapshot?: object;      // Stratégia állapot mentés

  // Nyitott pozíciók a session végén
  open_positions?: string[];    // position_id lista
  open_orders?: string[];       // client_order_id lista
}
```

### Indexek (ajánlott)

```javascript
db.sessions.createIndex({ "session_id": 1 }, { unique: true })
db.sessions.createIndex({ "strategy_id": 1, "started_at": -1 })
db.sessions.createIndex({ "strategy_id": 1, "ended_at": 1 })
```

### Példa Dokumentum

```json
{
  "_id": "65d8a1b2c3d4e5f6a7b8c9d3",
  "strategy_type": "bounce_scalper",
  "strategy_id": "bounce_scalper_live_001",
  "is_backtest": false,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",

  "started_at": "2026-02-21T10:00:00.000Z",
  "ended_at": "2026-02-21T18:00:00.000Z",
  "end_reason": "NORMAL",

  "recovered_from": null,
  "state_snapshot": {
    "instrument_states": {
      "BTCUSDC.BINANCE": {
        "entry_price": null,
        "position_count": 0,
        "cooldown_remaining": 3
      }
    }
  }
}
```

---

## 5. `balances` Collection

Balance snapshot-ok (csak live trading).

### Séma

```typescript
interface Balance extends BaseDocument {
  // Balance adatok
  balances: Array<{
    currency: string;           // pl. "USDC", "BTC"
    total: number;              // Összes
    free: number;               // Szabad
    locked: number;             // Zárolt (nyitott orderekben)
  }>;

  total_equity_usdc: number;    // Összes érték USDC-ben
  open_positions_count: number; // Nyitott pozíciók száma

  // Időbélyeg
  timestamp: Date;
}
```

### Frissítési Gyakoriság

~60 másodpercenként (live trading). Backtest-nél NEM generálódik.

### Indexek (ajánlott)

```javascript
db.balances.createIndex({ "strategy_id": 1, "timestamp": -1 })
db.balances.createIndex({ "session_id": 1 })
```

### Példa Dokumentum

```json
{
  "_id": "65d8a1b2c3d4e5f6a7b8c9d4",
  "strategy_type": "bounce_scalper",
  "strategy_id": "bounce_scalper_live_001",
  "is_backtest": false,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",

  "balances": [
    {
      "currency": "USDC",
      "total": 1085.50,
      "free": 1080.00,
      "locked": 5.50
    }
  ],
  "total_equity_usdc": 1085.50,
  "open_positions_count": 1,

  "timestamp": "2026-02-21T12:01:00.000Z"
}
```

---

## 6. `heartbeat` Collection

Stratégia heartbeat (csak live trading).

### Séma

```typescript
interface Heartbeat extends BaseDocument {
  // Státusz
  status: "RUNNING" | "STOPPED" | "ERROR";
  uptime_seconds: number;       // Futási idő másodpercben

  // Stratégia-specifikus állapot
  state?: {
    active_positions: number;
    instruments_tracked: number;
    instruments_in_cooldown: number;
    // ... stratégia-függő mezők
  };

  // Időbélyeg
  timestamp: Date;
}
```

### Viselkedés

- **Upsert**: Mindig csak 1 dokumentum/session (frissül, nem új rekord)
- **Frissítés**: ~30 másodpercenként
- **Backtest**: NEM generálódik

### Indexek (ajánlott)

```javascript
db.heartbeat.createIndex({ "session_id": 1 }, { unique: true })
db.heartbeat.createIndex({ "strategy_id": 1, "timestamp": -1 })
```

### Példa Dokumentum

```json
{
  "_id": "65d8a1b2c3d4e5f6a7b8c9d5",
  "strategy_type": "bounce_scalper",
  "strategy_id": "bounce_scalper_live_001",
  "is_backtest": false,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",

  "status": "RUNNING",
  "uptime_seconds": 7200.5,

  "state": {
    "active_positions": 2,
    "instruments_tracked": 8,
    "instruments_in_cooldown": 1
  },

  "timestamp": "2026-02-21T12:00:30.000Z"
}
```

---

## 7. `errors` Collection

Hibák és figyelmeztetések.

### Séma

```typescript
interface Error extends BaseDocument {
  level: "INFO" | "WARNING" | "ERROR";
  source: "STRATEGY" | "EXCHANGE" | "SYSTEM";
  message: string;

  // Időbélyeg
  timestamp: Date;
}
```

### Indexek (ajánlott)

```javascript
db.errors.createIndex({ "strategy_id": 1, "timestamp": -1 })
db.errors.createIndex({ "session_id": 1 })
db.errors.createIndex({ "level": 1 })
```

### Példa Dokumentum

```json
{
  "_id": "65d8a1b2c3d4e5f6a7b8c9d6",
  "strategy_type": "bounce_scalper",
  "strategy_id": "bounce_scalper_live_001",
  "is_backtest": false,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",

  "level": "WARNING",
  "source": "EXCHANGE",
  "message": "Order rejected: Insufficient balance",

  "timestamp": "2026-02-21T12:05:00.000Z"
}
```

---

## Gyakori Query-k

### Aktív session lekérése

```javascript
db.sessions.findOne({
  strategy_id: "bounce_scalper_live_001",
  ended_at: null
})
```

### Nyitott pozíciók

```javascript
db.positions.find({
  strategy_id: "bounce_scalper_live_001",
  status: "OPEN"
})
```

### Mai fill-ek

```javascript
const today = new Date();
today.setHours(0, 0, 0, 0);

db.fills.find({
  strategy_id: "bounce_scalper_live_001",
  is_backtest: false,
  filled_at: { $gte: today }
}).sort({ filled_at: -1 })
```

### Utolsó heartbeat

```javascript
db.heartbeat.findOne({
  strategy_id: "bounce_scalper_live_001"
}, { sort: { timestamp: -1 } })
```

### Realizált P&L összesítés

```javascript
db.positions.aggregate([
  {
    $match: {
      strategy_id: "bounce_scalper_live_001",
      status: "CLOSED",
      is_backtest: false
    }
  },
  {
    $group: {
      _id: "$instrument_id",
      total_pnl: { $sum: "$realized_pnl" },
      trade_count: { $sum: 1 },
      avg_duration: { $avg: "$duration_seconds" }
    }
  }
])
```

### Session history

```javascript
db.sessions.find({
  strategy_id: "bounce_scalper_live_001"
}).sort({ started_at: -1 }).limit(10)
```

---

## NestJS Mongoose Schema Példák

### Order Schema

```typescript
import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { Document } from 'mongoose';

@Schema({ collection: 'orders', timestamps: false })
export class Order extends Document {
  @Prop({ required: true })
  strategy_type: string;

  @Prop({ required: true, index: true })
  strategy_id: string;

  @Prop({ required: true })
  is_backtest: boolean;

  @Prop({ required: true, index: true })
  session_id: string;

  @Prop({ required: true, index: true })
  client_order_id: string;

  @Prop()
  venue_order_id?: string;

  @Prop({ required: true, index: true })
  instrument_id: string;

  @Prop({ required: true, enum: ['BUY', 'SELL'] })
  order_side: string;

  @Prop({ required: true })
  order_type: string;

  @Prop({ required: true })
  quantity: number;

  @Prop()
  price?: number;

  @Prop({ required: true, enum: ['SUBMITTED', 'ACCEPTED', 'FILLED', 'CANCELED', 'REJECTED', 'SYNC_CLOSED'], index: true })
  status: string;

  @Prop({ default: false })
  reduce_only: boolean;

  @Prop()
  external_action?: boolean;

  @Prop()
  reason?: string;

  @Prop({ required: true, index: true })
  submitted_at: Date;

  @Prop({ required: true })
  updated_at: Date;

  @Prop()
  ts_event?: number;
}

export const OrderSchema = SchemaFactory.createForClass(Order);

// Compound index
OrderSchema.index({ strategy_id: 1, client_order_id: 1 }, { unique: true });
```

### Position Schema

```typescript
@Schema({ collection: 'positions', timestamps: false })
export class Position extends Document {
  @Prop({ required: true })
  strategy_type: string;

  @Prop({ required: true, index: true })
  strategy_id: string;

  @Prop({ required: true })
  is_backtest: boolean;

  @Prop({ required: true, index: true })
  session_id: string;

  @Prop({ required: true, index: true })
  position_id: string;

  @Prop({ required: true, index: true })
  instrument_id: string;

  @Prop({ required: true, enum: ['LONG', 'SHORT'] })
  side: string;

  @Prop({ required: true })
  quantity: number;

  @Prop({ required: true })
  avg_open_price: number;

  @Prop()
  avg_close_price?: number;

  @Prop()
  realized_pnl?: number;

  @Prop({ required: true, enum: ['OPEN', 'CLOSED', 'SYNC_RECOVERY'], index: true })
  status: string;

  @Prop({ required: true, index: true })
  opened_at: Date;

  @Prop()
  closed_at?: Date;

  @Prop()
  updated_at?: Date;

  @Prop()
  duration_seconds?: number;

  @Prop()
  ts_event?: number;
}

export const PositionSchema = SchemaFactory.createForClass(Position);

PositionSchema.index({ strategy_id: 1, position_id: 1 }, { unique: true });
```

---

## Megjegyzések

1. **Backtest vs Live**: `is_backtest` mező alapján különíthető el
2. **Session**: Minden indítás új `session_id`-t generál
3. **Timestamps**: `ts_event` a NautilusTrader nanosec timestamp, a többi standard Date
4. **Heartbeat**: Session-önként 1 dokumentum (upsert)
5. **Crash Recovery**: `SYNC_CLOSED` státusz jelzi a recovery után lezárt elemeket
