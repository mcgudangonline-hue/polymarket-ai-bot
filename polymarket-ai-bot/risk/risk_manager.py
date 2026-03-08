class RiskManager:

    def __init__(self, bankroll, max_risk_per_trade=0.02):
        self.bankroll = bankroll
        self.max_risk_per_trade = max_risk_per_trade

    def calculate_position_size(self, price):
        risk_amount = self.bankroll * self.max_risk_per_trade
        size = risk_amount / price
        return size

    def can_trade(self, price):
        size = self.calculate_position_size(price)
        cost = size * price
        return cost <= self.bankroll