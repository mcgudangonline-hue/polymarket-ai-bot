"""
Multi-market scanner for Polymarket.
Fetches markets, evaluates each with the reasoning engine, scores by confidence/liquidity/volume.
Read-only; returns best market candidate. Does not modify the trading loop.
"""

import logging
import math

from data.polymarket_discovery import fetch_markets
from data.polymarket_client import PolymarketDataFeed, get_prices_bulk
from ai.reasoning_engine import ReasoningEngine

logger = logging.getLogger("polymarket_bot")


class MarketScanner:
    """
    Scans multiple markets, scores them using ReasoningEngine plus liquidity/volume,
    returns the best candidate. Read-only.
    """

    def __init__(
        self,
        reasoning_engine: ReasoningEngine | None = None,
        scan_limit: int = 20,
        default_scan_price: float = 0.5,
        timeout_seconds: int = 15,
        api_base: str = "https://clob.polymarket.com",
        price_source: str = "clob",
        min_gamma_price: float = 0.03,
        max_gamma_price: float = 0.97,
        min_liquidity: float = 5000.0,
        min_volume: float = 10000.0,
    ):
        self.reasoning_engine = reasoning_engine or ReasoningEngine()
        self.scan_limit = max(1, min(scan_limit, 100))
        self.default_scan_price = default_scan_price
        self.timeout_seconds = timeout_seconds
        self.api_base = api_base.rstrip("/") if api_base else "https://clob.polymarket.com"
        _ps = (price_source or "clob").strip().lower()
        self._price_source = "gamma" if _ps == "gamma" else "clob"
        self.min_gamma_price = min_gamma_price
        self.max_gamma_price = max_gamma_price
        self.min_liquidity = min_liquidity
        self.min_volume = min_volume

    def scan(self) -> dict | None:
        """
        Fetch markets, evaluate each with the reasoning engine, compute score,
        return the best market candidate or None if none valid.
        Skips markets where reasoning confidence < 0.3.

        Returns:
            {"title": str, "token_id": str, "score": float, "confidence": float,
             "volume": float, "liquidity": float} or None
        """
        markets = fetch_markets(
            limit=self.scan_limit,
            active=True,
            closed=False,
            order="volume_24hr",
            ascending=False,
            timeout_seconds=self.timeout_seconds,
        )
        if not markets:
            logger.warning("Market scanner: no markets returned from discovery")
            return None

        if self._price_source == "gamma":
            logger.info("Market scanner: price_source=gamma active (no CLOB scan requests)")

        token_ids = []
        for m in markets:
            tid = (m.get("token_id") or "").strip()
            if tid and tid not in token_ids:
                token_ids.append(tid)

        bulk_prices = {}
        if self._price_source == "clob" and token_ids:
            bulk_prices = get_prices_bulk(
                token_ids,
                api_base=self.api_base,
                side="BUY",
                timeout_seconds=self.timeout_seconds,
            )
            if bulk_prices:
                logger.info(
                    "Market scanner: bulk /prices succeeded, received %d of %d tokens",
                    len(bulk_prices),
                    len(token_ids),
                )
            else:
                logger.info("Market scanner: bulk /prices failed or empty, using per-token fallback")

        scored = []
        for m in markets:
            token_id = (m.get("token_id") or "").strip()
            if not token_id:
                continue
            enable_order_book = m.get("enableOrderBook")
            if enable_order_book is False:
                logger.debug("Market scanner: skipping market (enableOrderBook=false): %s", m.get("title") or token_id)
                continue
            accepting_orders = m.get("acceptingOrders")
            if accepting_orders is not None and accepting_orders is False:
                logger.debug("Market scanner: skipping market (acceptingOrders=false): %s", m.get("title") or token_id)
                continue
            title = m.get("title") or ""
            liquidity = m.get("liquidity")
            volume = m.get("volume")
            if liquidity is not None and not isinstance(liquidity, (int, float)):
                liquidity = None
            if volume is not None and not isinstance(volume, (int, float)):
                volume = None
            liquidity = float(liquidity) if liquidity is not None else 0.0
            volume = float(volume) if volume is not None else 0.0

            price = None
            used_source = None
            if self._price_source == "gamma":
                gamma_price = m.get("gamma_price")
                if gamma_price is not None:
                    try:
                        price = float(gamma_price)
                        if 0 <= price <= 1:
                            used_source = "gamma_price"
                    except (TypeError, ValueError):
                        pass
                if price is None or used_source is None:
                    logger.debug(
                        "Market scanner: skipping market %s (no valid gamma_price in gamma mode)",
                        title or token_id,
                    )
                    continue
                if price < self.min_gamma_price:
                    logger.debug(
                        "Market scanner: skipping market %s (gamma_price %.4f < min_gamma_price %.2f)",
                        title or token_id, price, self.min_gamma_price,
                    )
                    continue
                if price > self.max_gamma_price:
                    logger.debug(
                        "Market scanner: skipping market %s (gamma_price %.4f > max_gamma_price %.2f)",
                        title or token_id, price, self.max_gamma_price,
                    )
                    continue
                if liquidity < self.min_liquidity:
                    logger.debug(
                        "Market scanner: skipping market %s (liquidity %.0f < min_liquidity %.0f)",
                        title or token_id, liquidity, self.min_liquidity,
                    )
                    continue
                if volume < self.min_volume:
                    logger.debug(
                        "Market scanner: skipping market %s (volume %.0f < min_volume %.0f)",
                        title or token_id, volume, self.min_volume,
                    )
                    continue
            else:
                if token_id in bulk_prices:
                    price = bulk_prices[token_id]
                    used_source = "bulk_clob_prices"
                else:
                    feed = PolymarketDataFeed(
                        api_base=self.api_base,
                        token_id=token_id,
                        fallback_price=self.default_scan_price,
                        timeout_seconds=self.timeout_seconds,
                    )
                    clob_price = feed.get_price()
                    if clob_price != self.default_scan_price:
                        price = clob_price
                        used_source = "single_clob_price"
                    elif m.get("gamma_price") is not None:
                        price = float(m["gamma_price"])
                        used_source = "gamma_price"
                        logger.info(
                            "Market scanner: using gamma_price=%.4f for %s (CLOB unavailable)",
                            price, title or token_id,
                        )

                if price is None or used_source is None:
                    logger.info(
                        "Market scanner: skipping market %s (no orderbook price, no gamma_price)",
                        title or token_id,
                    )
                    continue
                if price < self.min_gamma_price:
                    logger.debug(
                        "Market scanner: skipping market %s (price %.4f < min_gamma_price %.2f)",
                        title or token_id, price, self.min_gamma_price,
                    )
                    continue
                if price > self.max_gamma_price:
                    logger.debug(
                        "Market scanner: skipping market %s (price %.4f > max_gamma_price %.2f)",
                        title or token_id, price, self.max_gamma_price,
                    )
                    continue
                if liquidity < self.min_liquidity:
                    logger.debug(
                        "Market scanner: skipping market %s (liquidity %.0f < min_liquidity %.0f)",
                        title or token_id, liquidity, self.min_liquidity,
                    )
                    continue
                if volume < self.min_volume:
                    logger.debug(
                        "Market scanner: skipping market %s (volume %.0f < min_volume %.0f)",
                        title or token_id, volume, self.min_volume,
                    )
                    continue

            logger.debug(
                "Market scanner: scoring market %s price=%.4f source=%s",
                title or token_id, price, used_source,
            )
            reasoning = self.reasoning_engine.analyze_market(
                price,
                has_open_position=False,
                market_title=title or None,
                volume=volume if volume else None,
            )
            confidence = float(reasoning.get("confidence", 0.0))

            if confidence < 0.3:
                continue

            gamma_price = m.get("gamma_price")
            if gamma_price is not None:
                try:
                    gamma_float = float(gamma_price)
                except (TypeError, ValueError):
                    gamma_float = None
            else:
                gamma_float = None
            score = self._score(confidence, liquidity, volume, gamma_float)
            if gamma_price is not None:
                try:
                    gamma_price = float(gamma_price)
                except (TypeError, ValueError):
                    gamma_price = None
            scored.append({
                "title": title,
                "token_id": token_id,
                "score": score,
                "confidence": confidence,
                "liquidity": liquidity,
                "volume": volume,
                "gamma_price": gamma_price,
                "enableOrderBook": m.get("enableOrderBook"),
                "acceptingOrders": m.get("acceptingOrders"),
            })

        if not scored:
            logger.warning("Market scanner: no markets with valid token_id")
            return None

        best = max(scored, key=lambda x: x["score"])
        logger.info(
            "Market scanner: best candidate title=%r token_id=%r score=%.4f confidence=%.4f volume=%.2f liquidity=%.2f",
            best["title"], best["token_id"], best["score"],
            best["confidence"], best["volume"], best["liquidity"],
        )
        return {
            "title": best["title"],
            "token_id": best["token_id"],
            "score": best["score"],
            "confidence": best["confidence"],
            "volume": best["volume"],
            "liquidity": best["liquidity"],
            "gamma_price": best.get("gamma_price"),
            "enableOrderBook": best.get("enableOrderBook"),
            "acceptingOrders": best.get("acceptingOrders"),
        }

    def _score(
        self,
        confidence: float,
        liquidity: float,
        volume: float,
        gamma_price: float | None = None,
    ) -> float:
        """
        Combine confidence (from reasoning engine), liquidity, and volume into one score.
        Uses log scale for liquidity/volume to avoid one huge market dominating.
        Boosts score when gamma_price is a valid float in [0, 1] for runtime fallback quality.
        """
        conf = max(0.0, min(1.0, confidence))
        liq = max(0.0, liquidity)
        vol = max(0.0, volume)
        log_liq = math.log1p(liq)
        log_vol = math.log1p(vol)
        base = conf * (1.0 + 0.2 * log_liq + 0.3 * log_vol)
        if gamma_price is not None and 0 <= gamma_price <= 1:
            return base * 1.1
        return base
