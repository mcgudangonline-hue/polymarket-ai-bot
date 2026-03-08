from strategies.base_strategy import BaseStrategy


class ThresholdStrategy(BaseStrategy):

    def __init__(self, buy_threshold, sell_threshold, take_profit_pct=0.10, stop_loss_pct=0.05, max_hold_iterations=5, min_price_change_for_entry=0.003, min_price_change_lookback=1):
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_hold_iterations = max_hold_iterations
        self.min_price_change_for_entry = min_price_change_for_entry
        self.min_price_change_lookback = min_price_change_lookback
        self.last_exit_reason = None

    def generate_signal(self, market_data):
        price = market_data["price"]
        has_open_position = market_data["has_open_position"]
        price_change = market_data.get("price_change")
        self.last_exit_reason = None

        # BUY only if threshold is met and price has moved enough over the lookback window (avoids flat-price entries).
        # price_change is current_price - lookback_price, where lookback_price is from min_price_change_lookback ticks ago.
        if not has_open_position and price <= self.buy_threshold:
            if price_change is not None and abs(price_change) >= self.min_price_change_for_entry:
                return "BUY"
            return "HOLD"

        if has_open_position:
            entry_price = market_data.get("entry_price")
            hold_iterations = market_data.get("hold_iterations", 0)
            if entry_price is not None:
                if price >= entry_price * (1 + self.take_profit_pct):
                    self.last_exit_reason = "take_profit"
                    return "SELL"
                if price <= entry_price * (1 - self.stop_loss_pct):
                    self.last_exit_reason = "stop_loss"
                    return "SELL"
            if hold_iterations >= self.max_hold_iterations:
                self.last_exit_reason = "max_hold"
                return "SELL"
            # Fallback for backward compatibility when entry_price not passed
            if entry_price is None and price >= self.sell_threshold:
                self.last_exit_reason = "threshold_fallback"
                return "SELL"

        return "HOLD"

    def get_exit_reason(self):
        return self.last_exit_reason