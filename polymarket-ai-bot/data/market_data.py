import random


class MarketDataFeed:

    def __init__(self, start_price=0.55):
        self.price = start_price

    def get_price(self):
        change = random.uniform(-0.01, 0.01)
        self.price = max(0.01, min(0.99, self.price + change))
        return round(self.price, 4)
