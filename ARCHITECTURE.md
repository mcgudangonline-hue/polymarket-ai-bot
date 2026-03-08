# System Architecture

Polymarket AI Bot consists of five main layers.

1. Market Discovery
2. Price Feed
3. Strategy Engine
4. Execution Engine
5. Session Logging

---

## Market Discovery

Responsible for selecting the best market.

Uses:

- volume
- liquidity
- gamma price filters

File:ai/market_scanner.py


---

## Price Feed

Responsible for fetching market prices.

Sources:

Gamma API (primary)

Fallback chain:

gamma_cache → provider → static gamma → fallback

File: data/polymarket_client.py


---

## Strategy Engine

Decision making logic.

Two layers:

Threshold strategy  
Hybrid strategy (threshold + AI reasoning)

Files: strategies/threshold_strategy.py
strategies/hybrid_strategy.py


---

## Execution Engine

Handles:

- position tracking
- trade execution
- PnL calculation

Files:
execution/trader.py
execution/position_manager.py


---

## Logging & Audit

Each session generates:

- trade history
- iteration history
- PnL report

Saved in:
logs/session_audit_*.json

