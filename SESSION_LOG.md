# IMC Prosperity 4 — Tutorial Phase Strategy Development Log

## Overview

This document records the full end-to-end process of developing, testing, and optimizing trading strategies for the IMC Prosperity 4 tutorial round (Round 0), covering products **TOMATOES** and **EMERALDS**.

---

## 1. Research Phase

### 1.1 Competition Rules (from wiki)

| Rule | Detail |
|------|--------|
| Position limits | EMERALDS = 80, TOMATOES = 80 |
| Order matching | OB depth first, then market trades |
| Market trade fill price | Your order's price (not the trade's price) |
| Limit enforcement | Before matching — all orders cancelled if any would exceed limit |
| Conversions | NOT supported in Round 0 |

### 1.2 Past Winner Analysis — Frankfurt Hedgehogs (2nd place globally, Prosperity 3)

Studied `https://github.com/TimoDiehm/imc-prosperity-3` — 925-line trading algorithm.

**Key strategies from past winner:**

| Product | Strategy | Profit/Round |
|---------|----------|-------------|
| Rainforest Resin | Static MM at fixed fair value 10,000 | ~39,000 |
| Kelp | Dynamic MM around wall_mid | ~5,000 |
| Squid Ink | Informed trader (Olivia) detection | ~8,000 |

**Critical insight borrowed:** The "wall mid" concept — use the price level with the LARGEST resting volume (not best bid/ask) as the fair value anchor.

---

## 2. Data Analysis

### 2.1 EMERALDS

**Data source:** `prices_round_0_day_-2.csv`, `prices_round_0_day_-1.csv`

| Metric | Value |
|--------|-------|
| Mid price range | 9,996 – 10,004 (essentially fixed) |
| Unique mid prices | 3 (9996, 10000, 10004) |
| Bid price_1 levels | {9992, 10000} |
| Ask price_1 levels | {10000, 10008} |
| Market trade prices | ONLY at 9,992 and 10,008 |
| Market trades/day | ~200 |
| Avg trade qty | 5.4 |

**Conclusion:** EMERALDS = Rainforest Resin analog. Fixed fair value of 10,000. Walls at 9992/10008.

### 2.2 TOMATOES

| Metric | Value |
|--------|-------|
| Mid price range | 4,946.5 – 5,036.0 |
| Mean mid price | ~4,993 |
| Std dev of mid price | ~19.75 |
| Lag-1 autocorr of returns | **-0.42** (strong mean reversion) |
| Bid/ask spread (level 1) | ~13 ticks |
| Wall bid (bid_price with most vol) | bid_price_2 or bid_price_3 |
| Wall ask (ask_price with most vol) | ask_price_2 or ask_price_3 |
| Market trades/day | ~410 |
| Avg trade qty | 3.5 |

**Day -2:** Price UP trend (4,993 → 5,006, median trade price 5,008)
**Day -1:** Price DOWN trend (5,006 → 4,957, median trade price 4,979)

**Conclusion:** TOMATOES = Kelp analog with stronger mean reversion. No fixed fair value; wall_mid tracks current price.

---

## 3. Infrastructure Setup

### 3.1 Backtester Setup

1. Installed backtester from source: `cd imc-prosperity-3-backtester && pip install -e .`
2. Added product limits to `prosperity3bt/data.py`:
   ```python
   LIMITS = {
       "EMERALDS": 80,
       "TOMATOES": 80,
       ...  # existing products
   }
   ```
3. Created custom data directory:
   ```
   custom_data/round0/
     prices_round_0_day_-1.csv
     prices_round_0_day_-2.csv
     trades_round_0_day_-1.csv
     trades_round_0_day_-2.csv
   ```
4. Copied `datamodel.py` to project root for imports
5. Run command: `python3 -m prosperity3bt trader.py 0 --data custom_data --merge-pnl`

---

## 4. Strategy Development & Optimization

### 4.1 Baseline (wavy.py / empty trader)

**PnL: 0** (no orders placed)

---

### 4.2 Version 1 — Basic Market Making

**EMERALDS:** Static MM around fair value 10,000
- Take sells < 10,000, take buys > 10,000
- Post passive bid at 9,999 / ask at 10,001
- Flatten at 10,000 when inventory non-zero
- Passive size = 10

**TOMATOES:** Dynamic MM using wall_mid (**with bug** — used `min` instead of `max` for ask wall)
- Take OB orders crossing wall_mid
- Quote at wall_mid ± 2 with inventory + momentum skew
- EMA alpha = 0.2, inv_skew = 4, momentum damp = 0.3

**Results:**
| Day | EMERALDS | TOMATOES | Total |
|-----|----------|----------|-------|
| Day -2 | 768 | 3,261 | 4,029 |
| Day -1 | 835 | 4,733 | 5,568 |
| **Total** | **1,603** | **7,994** | **9,597** |

**Problem found:** EMERALDS posting at 9999/10001 only earns 2 ticks per round trip.

---

### 4.3 Key Discovery — EMERALDS Wall Strategy

**Parameter sweep (local simulation):**

| Bid Price | Ask Price | Total PnL |
|-----------|-----------|-----------|
| 9,999 | 10,001 | 2,092 |
| 9,997 | 10,003 | 6,276 |
| 9,995 | 10,005 | 10,460 |
| 9,993 | 10,007 | 14,644 |
| **9,992** | **10,008** | **16,736** |

**Insight:** ALL market trades happen at exactly 9,992 or 10,008. Posting AT the wall levels matches the same trades but earns 16 ticks per round trip instead of 2. This is 8× more profitable.

---

### 4.4 Bug Fix — wall_mid for TOMATOES

**Bug:** `ask_wall = min(sell_orders, key=lambda p: abs(sell_orders[p]))` → finds SMALLEST volume ask (ask_price_1, the thin level)

**Fix:** `ask_wall = max(sell_orders, key=lambda p: abs(sell_orders[p]))` → finds LARGEST volume ask (ask_price_2 / ask_price_3, the wall level)

The wall_mid now correctly uses the thick-volume levels as the fair value anchor.

---

### 4.5 Version 2 — Wall Strategy + Bug Fix

**Results:**
| Day | EMERALDS | TOMATOES | Total |
|-----|----------|----------|-------|
| Day -2 | 8,000 | 6,237 | 14,237 |
| Day -1 | 8,736 | 1,744 | 10,480 |
| **Total** | **16,736** | **7,981** | **24,717** |

EMERALDS improved 10×. But TOMATOES day -1 dropped to 1,744 — the downtrend hurts badly.

---

### 4.6 TOMATOES Parameter Sweep

**Swept:** spread (4–7), inv_skew (0–10), ema_alpha (0.2–0.5), momentum_damp (0.0–0.5)

**Key finding:** Momentum signal adds **zero value** — results identical for mom_damp = 0.0 vs 0.3 vs 0.5. Removed.

**Best configuration found:**

| Parameter | Value | Why |
|-----------|-------|-----|
| SPREAD | 6 | Wider = more profit per fill, same volume |
| INV_SKEW | 2 | Small skew helps balance position |
| EMA/MOMENTUM | N/A | Removed — adds no value |
| PASSIVE_SIZE | 20 | Irrelevant — market trades are tiny (3–5 units) |

**Spread selection logic:**
- Market bid1/ask1 half-spread ≈ 6.5 (bid at 5000, ask at 5013, wm at 5006)
- Our spread = 6 puts quotes just inside the outer market spread
- Trades beyond ±6 from wm fill our passive quotes
- Higher spread → earn more per fill → optimal at 6

**TOMATOES spread sweep results:**
| Spread | Day -2 | Day -1 | Total |
|--------|--------|--------|-------|
| 4 | 5,609 | 4,891 | 10,500 |
| 5 | 6,910 | 6,343 | 13,254 |
| **6** | **8,365** | **7,833** | **16,198** |
| 7 | 6,134 | 5,994 | 12,128 |

*(Simulation values — actual backtester ~20% lower due to limit enforcement)*

---

### 4.7 Version 3 — Final Optimized Strategy

**EMERALDS:**
- Post buy at 9,992 (wall bid), sell at 10,008 (wall ask)
- Size = 40 per order (capped by capacity)
- Also take OB asks/bids at exactly 10,000 for inventory management

**TOMATOES:**
- wall_mid = (highest-volume-bid + highest-volume-ask) / 2
- Quote at wall_mid ± 6, with ±2 tick inventory skew
- No momentum or EMA component

**Final Backtester Results:**
| Day | EMERALDS | TOMATOES | Total |
|-----|----------|----------|-------|
| Day -2 | 8,000 | 8,532 | 16,532 |
| Day -1 | 8,736 | 4,164 | 12,900 |
| **Total** | **16,736** | **12,696** | **29,432** |

**Improvement from baseline:** 9,597 → 29,432 (+207%)

---

## 5. Architecture of Final trader.py

```
trader.py
├── Logger class (visualizer-compatible format)
├── get_wall_mid(order_depth) → float
│   └── max by volume for both bid and ask walls
├── emeralds_orders(order_depth, position) → list[Order]
│   ├── Take OB asks at ≤ 10,000 (inventory flatten)
│   ├── Take OB bids at ≥ 10,000 (inventory flatten)
│   └── Post passive buy@9992 / sell@10008 (wall quotes)
├── tomatoes_orders(order_depth, position) → list[Order]
│   ├── Take OB orders that have crossed wall_mid (rare)
│   ├── Compute inventory skew (max ±2 ticks)
│   └── Post passive buy@(wm-6+skew) / sell@(wm+6+skew)
└── Trader.run() → dispatch to above per product
```

---

## 6. Remaining Issues / Future Improvements

### 6.1 TOMATOES Trending Market Problem
- Day -1 (downtrend) earns only 4,164 vs 8,532 on day -2 (uptrend)
- Root cause: passive buy fills in falling market, position goes long, sell quotes don't fill
- **What was tried:** aggressive flatten when position > threshold → no improvement in simulation
- **What could help:** trend detection (dual EMA crossover to flip from buy-heavy to sell-heavy)

### 6.2 Position Limit Enforcement Gap
- Local simulation overestimates TOMATOES PnL by ~28% vs actual backtester
- Backtester enforces ALL-or-nothing cancellation if any order set exceeds limit
- Simulation doesn't replicate this exactly

### 6.3 EMERALDS Near-Optimal
- Earning 16,736/2days = 8,368/day
- Theoretical max ≈ (200 trades × 5.4 qty / 2) × 16 = 8,640/day
- Capturing ~97% of available profit

---

## 7. Files Created / Modified

| File | Action | Description |
|------|--------|-------------|
| `trader.py` | Created | Final trading strategy |
| `datamodel.py` | Copied | From backtester, required for imports |
| `custom_data/round0/*.csv` | Copied | Prosperity 4 tutorial data for backtester |
| `imc-prosperity-3-backtester/prosperity3bt/data.py` | Modified | Added EMERALDS:80, TOMATOES:80 to LIMITS |
| `backtests/final.log` | Created | Final backtest output log |

---

## 8. Run Commands

```bash
# Install backtester
cd imc-prosperity-3-backtester && pip install -e .

# Run backtest (both days, merged PnL)
python3 -m prosperity3bt trader.py 0 --data custom_data --merge-pnl --no-out

# Run backtest and save log (for visualizer)
python3 -m prosperity3bt trader.py 0 --data custom_data --merge-pnl --out backtests/result.log

# Open in visualizer (requires --vis flag and visualizer running)
python3 -m prosperity3bt trader.py 0 --data custom_data --vis
```
