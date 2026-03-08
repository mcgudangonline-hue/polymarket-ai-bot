class BaseStrategy:

    def generate_signal(self, market_data):
        raise NotImplementedError("Strategy must implement generate_signal method.")

    def get_exit_reason(self):
        """Return exit reason when last signal was SELL; otherwise None. Override in subclasses."""
        return None