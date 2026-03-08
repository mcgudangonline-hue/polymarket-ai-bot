"""
Read-only reasoning layer for market analysis.
Rule-based logic only; no external LLM API.
Interface prepared for future AI integration.
"""


class ReasoningEngine:
    """Simple rule-based market analysis. Output is for observation/logging only."""

    def analyze_market(
        self,
        price: float,
        has_open_position: bool,
        market_title: str | None = None,
        volume: float | None = None,
    ) -> dict:
        """
        Analyze current market state and return bias, confidence, reasoning, and recommendation.
        Returns a dict with: market_bias, confidence, reasoning, recommendation.
        """
        # Simple rule-based logic (explainable, no external API)
        if not has_open_position:
            if price < 0.45:
                return {
                    "market_bias": "bullish",
                    "confidence": 0.6,
                    "reasoning": f"No position; price {price:.3f} is relatively low; bias leans bullish.",
                    "recommendation": "BUY",
                }
            if price > 0.55:
                return {
                    "market_bias": "bearish",
                    "confidence": 0.5,
                    "reasoning": f"No position; price {price:.3f} is relatively high; bias leans bearish.",
                    "recommendation": "HOLD",
                }
            return {
                "market_bias": "neutral",
                "confidence": 0.4,
                "reasoning": f"No position; price {price:.3f} in mid-range; no strong bias.",
                "recommendation": "NO_TRADE",
            }

        # Has open position
        if price > 0.55:
            return {
                "market_bias": "bearish",
                "confidence": 0.6,
                "reasoning": f"Open position; price {price:.3f} relatively high; bias leans toward taking profit.",
                "recommendation": "SELL",
            }
        if price < 0.45:
            return {
                "market_bias": "bullish",
                "confidence": 0.4,
                "reasoning": f"Open position; price {price:.3f} low; holding for recovery.",
                "recommendation": "HOLD",
            }
        return {
            "market_bias": "neutral",
            "confidence": 0.4,
            "reasoning": f"Open position; price {price:.3f} in mid-range; hold.",
            "recommendation": "HOLD",
        }
