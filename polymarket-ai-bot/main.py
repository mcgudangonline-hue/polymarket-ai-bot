import time

from utils.logger import setup_logger
from utils.config_loader import load_config
from utils.session_audit import save_session_audit
from risk.risk_manager import RiskManager
from execution.paper_trader import PaperTrader
from execution.position_manager import PositionManager
from data.market_data import MarketDataFeed
from data.polymarket_client import PolymarketDataFeed, get_orderbook
from data.polymarket_discovery import fetch_gamma_price_for_token
from strategies.threshold_strategy import ThresholdStrategy
from ai.market_scanner import MarketScanner
from strategies.hybrid_strategy import HybridStrategy
from ai.reasoning_engine import ReasoningEngine


def main():
    logger = setup_logger()
    config = load_config()

    bot_mode = config["bot"]["mode"]
    bankroll = config["trading"]["bankroll"]
    max_risk_per_trade = config["trading"]["max_risk_per_trade"]
    max_trades_per_session = config["trading"]["max_trades_per_session"]
    fee_rate = config["trading"]["fee_rate"]
    slippage_rate = config["trading"]["slippage_rate"]
    data_source = config["market"]["data_source"]
    polling_interval_seconds = config["market"]["polling_interval_seconds"]
    buy_threshold = config["strategy"]["buy_threshold"]
    sell_threshold = config["strategy"]["sell_threshold"]
    take_profit_pct = config["strategy"].get("take_profit_pct", 0.10)
    stop_loss_pct = config["strategy"].get("stop_loss_pct", 0.05)
    max_hold_iterations = config["strategy"].get("max_hold_iterations", 5)
    reentry_cooldown_iterations = config["strategy"].get("reentry_cooldown_iterations", 2)
    min_price_change_for_entry = config["strategy"].get("min_price_change_for_entry", 0.003)
    min_price_change_lookback = config["strategy"].get("min_price_change_lookback", 1)
    strategy_mode = config["strategy"].get("mode", "threshold")

    risk_manager = RiskManager(
        bankroll=bankroll,
        max_risk_per_trade=max_risk_per_trade
    )

    trader = PaperTrader()
    position_manager = PositionManager()
    if data_source == "simulator":
        market = MarketDataFeed()
    elif data_source == "polymarket":
        pm = config.get("polymarket", {})
        token_id = (pm.get("token_id") or "").strip()
        gamma_fallback_price = None
        if not token_id:
            scanner = MarketScanner(
                api_base=pm.get("api_base", "https://clob.polymarket.com"),
                scan_limit=pm.get("scan_limit", 20),
                timeout_seconds=pm.get("timeout_seconds", 10),
                price_source=pm.get("price_source", "clob"),
                min_gamma_price=pm.get("min_gamma_price", 0.03),
                max_gamma_price=pm.get("max_gamma_price", 0.97),
                min_liquidity=pm.get("min_liquidity", 5000),
                min_volume=pm.get("min_volume", 10000),
            )
            candidate = scanner.scan()
            if candidate:
                token_id = candidate["token_id"]
                gamma_fallback_price = candidate.get("gamma_price")
                if gamma_fallback_price is not None:
                    try:
                        gamma_fallback_price = float(gamma_fallback_price)
                    except (TypeError, ValueError):
                        gamma_fallback_price = None
                if gamma_fallback_price is not None and not (0 <= gamma_fallback_price <= 1):
                    gamma_fallback_price = None
                logger.info(
                    "Selected market: title=%s, token_id=%s, score=%.4f, confidence=%.4f, volume=%.2f, liquidity=%.2f",
                    candidate.get("title", ""),
                    token_id,
                    candidate.get("score", 0),
                    candidate.get("confidence", 0),
                    candidate.get("volume", 0),
                    candidate.get("liquidity", 0),
                )
            else:
                logger.warning("Market scanner returned no candidate; using fallback price.")
        timeout_sec = pm.get("timeout_seconds", 10)
        gamma_price_provider = (
            (lambda: fetch_gamma_price_for_token(token_id, timeout_seconds=timeout_sec))
            if token_id
            else None
        )
        market = PolymarketDataFeed(
            api_base=pm.get("api_base", "https://clob.polymarket.com"),
            token_id=token_id,
            fallback_price=pm.get("fallback_price", 0.5),
            timeout_seconds=timeout_sec,
            gamma_fallback_price=gamma_fallback_price,
            gamma_price_provider=gamma_price_provider,
            price_source=pm.get("price_source", "clob"),
        )
        if token_id and pm.get("enable_orderbook_diagnostic", False):
            ob = get_orderbook(
                token_id,
                api_base=pm.get("api_base", "https://clob.polymarket.com"),
                timeout_seconds=timeout_sec,
            )
            logger.info("Orderbook (startup): %s", ob)
    else:
        market = MarketDataFeed()
    threshold_strategy = ThresholdStrategy(
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        max_hold_iterations=max_hold_iterations,
        min_price_change_for_entry=min_price_change_for_entry,
        min_price_change_lookback=min_price_change_lookback,
    )
    reasoning_engine = ReasoningEngine()
    if strategy_mode == "hybrid":
        strategy = HybridStrategy(threshold_strategy, reasoning_engine)
    else:
        strategy = threshold_strategy

    executed_trades = 0
    total_realized_pnl = 0.0
    total_fees_paid = 0.0
    total_realized_pnl_after_fees = 0.0
    closed_positions = []
    iteration_history = []
    last_price = None
    price_history = []
    hold_iterations = 0
    cooldown_iterations_remaining = 0
    try:
        lookback_n = max(1, int(min_price_change_lookback))
    except (TypeError, ValueError):
        lookback_n = 1

    logger.info(f"Bot mode: {bot_mode}")
    logger.info(f"Data source: {data_source}")
    logger.info(f"Strategy buy threshold: {buy_threshold}")
    logger.info(f"Strategy mode: {strategy_mode}")
    logger.info(f"Strategy sell threshold: {sell_threshold}")
    logger.info(f"Take profit pct: {take_profit_pct}, stop loss pct: {stop_loss_pct}, max hold iterations: {max_hold_iterations}, reentry cooldown iterations: {reentry_cooldown_iterations}")
    logger.info(f"Max trades per session: {max_trades_per_session}")
    logger.info(f"Polling interval seconds: {polling_interval_seconds}")
    logger.info("Starting market loop...")

    for iteration in range(1, 6):
        price = market.get_price()
        last_price = price
        N = lookback_n
        previous_price = price_history[-1] if price_history else None
        lookback_price = price_history[-N] if len(price_history) >= N else None
        price_change = (price - lookback_price) if lookback_price is not None else None
        price_history_size = len(price_history)
        if lookback_price is not None:
            logger.info(
                "Price movement: previous_price=%.6f, lookback_price=%.6f, price_change=%.6f, lookback=%d",
                previous_price or 0.0, lookback_price, price_change or 0.0, N,
            )
        has_open_position = position_manager.has_open_position()
        if has_open_position:
            hold_iterations += 1

        market_data = {
            "price": price,
            "has_open_position": has_open_position,
            "previous_price": previous_price,
            "lookback_price": lookback_price,
            "price_change": price_change,
            "price_history_size": price_history_size,
        }
        if has_open_position:
            pos = position_manager.get_position()
            if pos:
                market_data["entry_price"] = pos["entry_price"]
                market_data["hold_iterations"] = hold_iterations

        if strategy_mode == "hybrid":
            signal = strategy.decide_trade(market_data)
        else:
            signal = strategy.generate_signal(market_data)
            reasoning = reasoning_engine.analyze_market(
                price=price,
                has_open_position=has_open_position,
                market_title=None,
                volume=None,
            )
            logger.info(f"Reasoning: {reasoning}")

        # Re-entry cooldown: suppress BUY for N iterations after closing a position
        if signal == "BUY" and cooldown_iterations_remaining > 0:
            logger.info(f"BUY suppressed by re-entry cooldown ({cooldown_iterations_remaining} iterations remaining).")
            signal = "HOLD"

        iteration_record = {
            "iteration": iteration,
            "price": price,
            "signal": signal,
            "has_open_position": has_open_position
        }
        if has_open_position:
            pos = position_manager.get_position()
            entry_price = pos["entry_price"]
            size = pos["size"]
            iteration_record["unrealized_pnl"] = (price - entry_price) * size
        iteration_history.append(iteration_record)

        logger.info(f"Iteration: {iteration}")
        logger.info(f"Market price: {price}")
        logger.info(f"Has open position: {has_open_position}")
        logger.info(f"Strategy signal: {signal}")

        if signal == "BUY":
            if position_manager.has_open_position():
                logger.warning("Trade skipped. Open position already exists.")
            elif executed_trades >= max_trades_per_session:
                logger.warning("Trade skipped. Max trades per session reached.")
            elif risk_manager.can_trade(price):
                position_size = risk_manager.calculate_position_size(price)
                buy_execution_price = price * (1 + slippage_rate)
                opened_position = position_manager.open_position("BUY", buy_execution_price, position_size)

                if opened_position is not None:
                    hold_iterations = 0
                    trade = trader.place_order("BUY", buy_execution_price, position_size)
                    executed_trades += 1
                    logger.info(f"Paper trade executed: {trade}")
                    logger.info(f"Opened position: {opened_position}")
                    logger.info(f"Executed trades count: {executed_trades}")
                else:
                    logger.warning("Trade skipped. Failed to open position.")
            else:
                logger.warning("Trade rejected by risk manager.")

        elif signal == "SELL":
            current_position = position_manager.get_position()

            if current_position is None:
                logger.warning("SELL skipped. No open position found.")
            else:
                sell_execution_price = price * (1 - slippage_rate)
                closed_position = position_manager.close_position(sell_execution_price)

                if closed_position is not None:
                    entry_price = closed_position["entry_price"]
                    exit_price = closed_position["exit_price"]
                    size = closed_position["size"]
                    realized_pnl = closed_position["realized_pnl"]
                    exit_reason = getattr(strategy, "get_exit_reason", lambda: None)() or "unknown"
                    closed_position["exit_reason"] = exit_reason
                    entry_fee = entry_price * size * fee_rate
                    exit_fee = exit_price * size * fee_rate
                    total_fee = entry_fee + exit_fee
                    realized_pnl_after_fees = realized_pnl - total_fee
                    closed_position["entry_fee"] = entry_fee
                    closed_position["exit_fee"] = exit_fee
                    closed_position["total_fee"] = total_fee
                    closed_position["realized_pnl_after_fees"] = realized_pnl_after_fees
                    closed_positions.append(closed_position)
                    total_realized_pnl += realized_pnl
                    total_fees_paid += total_fee
                    total_realized_pnl_after_fees += realized_pnl_after_fees
                    trade = trader.place_order("SELL", sell_execution_price, closed_position["size"])
                    executed_trades += 1
                    logger.info(f"Paper trade executed: {trade}")
                    logger.info(f"Closed position: {closed_position}")
                    logger.info(f"Executed trades count: {executed_trades}")
                    cooldown_iterations_remaining = reentry_cooldown_iterations
                else:
                    logger.warning("SELL skipped. Failed to close position.")

        else:
            logger.info("No trade executed. Strategy returned HOLD.")

        if cooldown_iterations_remaining > 0:
            cooldown_iterations_remaining -= 1

        price_history.append(price)
        if N + 1 > 0:
            price_history = price_history[-(N + 1) :]
        time.sleep(polling_interval_seconds)

    trade_history = trader.get_trade_history()
    current_position = position_manager.get_position()
    if current_position is not None and last_price is not None:
        final_unrealized_pnl = (last_price - current_position["entry_price"]) * current_position["size"]
    else:
        final_unrealized_pnl = 0.0

    logger.info("Market loop finished safely.")
    logger.info(f"Session executed trades total: {executed_trades}")
    logger.info(f"Session trade history: {trade_history}")
    logger.info(f"Session iteration history: {iteration_history}")
    logger.info(f"Final open position: {current_position}")

    # Trade performance metrics from closed_positions
    total_closed_trades = len(closed_positions)
    if total_closed_trades > 0:
        pnls = [cp["realized_pnl"] for cp in closed_positions]
        winning_trades = sum(1 for p in pnls if p > 0)
        losing_trades = sum(1 for p in pnls if p < 0)
        win_rate = winning_trades / total_closed_trades
        average_realized_pnl = sum(pnls) / total_closed_trades
        best_trade_pnl = max(pnls)
        worst_trade_pnl = min(pnls)
    else:
        winning_trades = 0
        losing_trades = 0
        win_rate = 0.0
        average_realized_pnl = 0.0
        best_trade_pnl = 0.0
        worst_trade_pnl = 0.0

    session_data = {
        "bot_mode": bot_mode,
        "bankroll": bankroll,
        "max_risk_per_trade": max_risk_per_trade,
        "max_trades_per_session": max_trades_per_session,
        "polling_interval_seconds": polling_interval_seconds,
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
        "executed_trades": executed_trades,
        "trade_history": trade_history,
        "closed_positions": closed_positions,
        "iteration_history": iteration_history,
        "final_open_position": current_position,
        "total_realized_pnl": total_realized_pnl,
        "total_fees_paid": total_fees_paid,
        "total_realized_pnl_after_fees": total_realized_pnl_after_fees,
        "final_unrealized_pnl": final_unrealized_pnl,
        "total_closed_trades": total_closed_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "average_realized_pnl": average_realized_pnl,
        "best_trade_pnl": best_trade_pnl,
        "worst_trade_pnl": worst_trade_pnl,
    }

    audit_file_path = save_session_audit(session_data)
    logger.info(f"Session audit saved to: {audit_file_path}")


if __name__ == "__main__":
    main()