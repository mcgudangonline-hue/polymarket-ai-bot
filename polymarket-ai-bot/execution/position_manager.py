class PositionManager:

    def __init__(self):
        self.current_position = None


    def has_open_position(self):
        return self.current_position is not None


    def open_position(self, side, price, size):
        if self.has_open_position():
            return None

        self.current_position = {
            "side": side,
            "entry_price": price,
            "size": size
        }

        return self.current_position


    def close_position(self, exit_price):
        if not self.has_open_position():
            return None

        side = self.current_position["side"]
        entry_price = self.current_position["entry_price"]
        size = self.current_position["size"]

        realized_pnl = (exit_price - entry_price) * size

        closed_position = {
            "side": side,
            "entry_price": entry_price,
            "size": size,
            "exit_price": exit_price,
            "realized_pnl": realized_pnl
        }

        self.current_position = None

        return closed_position


    def get_position(self):
        return self.current_position