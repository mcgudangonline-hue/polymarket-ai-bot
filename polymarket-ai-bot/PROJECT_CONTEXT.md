PROJECT: Polymarket AI Bot



Current Architecture

--------------------



Language: Python



Core Modules

\- main.py

\- config/settings.yaml

\- utils/logger.py

\- utils/config\_loader.py

\- utils/session\_audit.py



Trading Engine

\- risk/risk\_manager.py

\- execution/paper\_trader.py

\- execution/position\_manager.py



Market Layer

\- data/market\_data.py



Strategy

\- strategies/base\_strategy.py

\- strategies/threshold\_strategy.py



Features Implemented

--------------------



✓ Config system (YAML)

✓ Logger system

✓ Paper trading engine

✓ Position manager

✓ Risk manager

✓ Strategy system

✓ Entry logic (BUY)

✓ Exit logic (SELL)

✓ Market simulator

✓ Session audit JSON

✓ Iteration history logging

✓ Max trades per session guardrail

✓ Polling interval config



Current Strategy

----------------



Threshold Strategy



BUY  if price <= buy\_threshold

SELL if price >= sell\_threshold



Config Example

--------------



buy\_threshold: 0.54

sell\_threshold: 0.56



Current Execution Mode

----------------------



paper trading only



Next Planned Systems

--------------------



1\. PnL calculation

2\. Position tracking improvements

3\. Trade performance metrics

4\. Market data integration (Polymarket API)

5\. AI reasoning layer

6\. Backtesting system

