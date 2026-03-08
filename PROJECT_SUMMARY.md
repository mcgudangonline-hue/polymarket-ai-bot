# Polymarket AI Trading Bot – Project Summary

## Overview
This repository contains an AI-assisted trading bot for Polymarket prediction markets.

The bot operates primarily using the Gamma API as a price source when CLOB access is unavailable.

Main goals:
- Automated market discovery
- Hybrid strategy (threshold + AI reasoning)
- Risk-managed trade execution
- Paper trading environment for testing

---

# Architecture

Main modules:

main.py  
Entry point that runs the trading loop.

ai/
Reasoning engine and market scanner.

strategies/
Trading strategies including threshold and hybrid logic.

data/
Polymarket client, discovery logic, and market data.

execution/
Trade execution and position manager.

utils/
Logger, config loader, and session audit.

config/
Strategy and runtime configuration.

logs/
Session audit and runtime logs.

---

# Pricing System

Primary source: **Gamma API**

Gamma price chain:

1. cached gamma price
2. refreshed gamma provider
3. static gamma fallback
4. config fallback

CLOB endpoints are disabled in gamma mode.

---

# Market Scanner

Markets are filtered by:

- gamma_price range
- liquidity
- volume

Default filters:


---

# Strategy Logic

Hybrid strategy combines:

Threshold strategy  
+
AI reasoning engine

BUY conditions:

- price <= buy_threshold
- AI recommendation = BUY
- AI confidence ≥ 0.6
- price movement ≥ min_price_change_for_entry

SELL conditions:

- take_profit
- stop_loss
- max_hold_iterations

Exit signals are **not blocked by AI reasoning**.

---

# Risk Management

Features:

Take profit: 10%  
Stop loss: 5%  
Max hold iterations: configurable  
Re-entry cooldown: prevents immediate re-buy.

---

# Gamma Price Movement Filter

To avoid flat-price entries:

BUY only allowed if:



---

# Strategy Logic

Hybrid strategy combines:

Threshold strategy  
+
AI reasoning engine

BUY conditions:

- price <= buy_threshold
- AI recommendation = BUY
- AI confidence ≥ 0.6
- price movement ≥ min_price_change_for_entry

SELL conditions:

- take_profit
- stop_loss
- max_hold_iterations

Exit signals are **not blocked by AI reasoning**.

---

# Risk Management

Features:

Take profit: 10%  
Stop loss: 5%  
Max hold iterations: configurable  
Re-entry cooldown: prevents immediate re-buy.

---

# Gamma Price Movement Filter

To avoid flat-price entries:

BUY only allowed if:


Price movement uses configurable lookback window.

---

# Current Mode


CLOB access currently returns 403.

---

# Future Improvements

Planned upgrades:

- WebSocket price feed
- Spread-based execution
- Position sizing model
- Strategy backtesting
- Multi-market scanning
- Real trading support

---

# Repository

https://github.com/mcgudangonline-hue/polymarket-ai-bot
