"""
Hybrid strategy: combines threshold signals with AI reasoning confidence.
BUY/SELL only when both threshold and reasoning agree (with confidence gate for BUY).
"""

import logging

logger = logging.getLogger("polymarket_bot")


class HybridStrategy:
    """Combines ThresholdStrategy and ReasoningEngine for joint BUY/SELL decisions."""

    def __init__(self, threshold_strategy, reasoning_engine):
        self.threshold_strategy = threshold_strategy
        self.reasoning_engine = reasoning_engine

    def decide_trade(self, market_data: dict) -> str:
        """
        Combine threshold signal and AI reasoning. Returns "BUY", "SELL", or "HOLD".
        BUY only if threshold says BUY, reasoning says BUY, and confidence >= 0.6.
        SELL if threshold says SELL (risk/exit signals are not blocked by AI reasoning).
        market_data must contain at least: price, has_open_position; optionally entry_price, hold_iterations.
        """
        price = market_data["price"]
        has_open_position = market_data["has_open_position"]
        signal = self.threshold_strategy.generate_signal(market_data)
        reasoning = self.reasoning_engine.analyze_market(
            price=price,
            has_open_position=has_open_position,
            market_title=None,
            volume=None,
        )

        logger.info("Hybrid strategy: threshold_signal=%s, reasoning=%s", signal, reasoning)

        # BUY only if both agree and AI confidence is high enough (tolerance for float precision)
        if signal == "BUY" and reasoning["recommendation"] == "BUY" and reasoning["confidence"] >= 0.6 - 1e-9:
            return "BUY"

        # SELL exits (take_profit, stop_loss, max_hold) are risk-control exits; do not block on AI.
        if signal == "SELL":
            return "SELL"

        return "HOLD"

    def get_exit_reason(self):
        """Delegate to threshold strategy; exit reason comes from threshold logic."""
        return self.threshold_strategy.get_exit_reason()
