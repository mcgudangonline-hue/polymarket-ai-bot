from datetime import datetime


class PaperTrader:

    def __init__(self):
        self.trades = []
        self.trade_counter = 0

    def place_order(self, side, price, size):
        self.trade_counter += 1

        trade = {
            "trade_id": self.trade_counter,
            "timestamp": datetime.utcnow().isoformat(),
            "side": side,
            "price": price,
            "size": size
        }

        self.trades.append(trade)
        return trade

    def get_trade_history(self):
        return self.trades