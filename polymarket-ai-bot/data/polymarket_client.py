"""
Optional Polymarket market data feed.
Read-only HTTP price fetch with safe fallback.
Bulk /prices support for scanner.
"""

import json
import logging
import time
import urllib.error
import urllib.request

logger = logging.getLogger("polymarket_bot")


def get_prices_bulk(
    token_ids: list[str],
    api_base: str = "https://clob.polymarket.com",
    side: str = "BUY",
    timeout_seconds: int = 10,
) -> dict[str, float]:
    """
    Fetch prices for multiple token_ids in one request (CLOB POST /prices).
    Returns dict token_id -> price. Failed or missing tokens are omitted.
    """
    api_base = api_base.rstrip("/")
    if not token_ids:
        return {}
    payload = [{"token_id": tid, "side": side} for tid in token_ids]
    url = f"{api_base}/prices"
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=max(1, timeout_seconds)) as resp:
            body = resp.read().decode("utf-8")
            if resp.status != 200:
                snippet = (body or "")[:300]
                logger.warning(
                    "Polymarket bulk /prices HTTP error: status=%s body_snippet=%s",
                    resp.status,
                    snippet,
                )
                return {}
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.warning(
            "Polymarket bulk /prices request failed: exception=%s type=%s",
            e,
            type(e).__name__,
        )
        return {}
    try:
        raw = json.loads(body)
    except json.JSONDecodeError as e:
        logger.warning("Polymarket bulk /prices invalid JSON: %s", e)
        return {}
    if not isinstance(raw, dict):
        logger.warning("Polymarket bulk /prices response not a dict: %s", type(raw))
        return {}
    result = {}
    for tid in token_ids:
        side_data = raw.get(tid)
        if not isinstance(side_data, dict):
            continue
        p = side_data.get(side)
        if p is None:
            continue
        try:
            p = float(p)
        except (TypeError, ValueError):
            continue
        if 0 <= p <= 1:
            result[tid] = round(p, 4)
    return result


def get_orderbook(
    token_id: str,
    api_base: str = "https://clob.polymarket.com",
    timeout_seconds: int = 10,
) -> dict:
    """
    Fetch orderbook for a token (GET /book?token_id=...).
    Returns normalized dict: best_bid, best_ask, mid_price, spread.
    All values are float or None. Prices are validated to [0, 1].
    """
    api_base = api_base.rstrip("/")
    url = f"{api_base}/book?token_id={token_id}"
    logger.info("Polymarket orderbook request: url=%s", url)

    result = {
        "best_bid": None,
        "best_ask": None,
        "mid_price": None,
        "spread": None,
    }

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=max(1, timeout_seconds)) as resp:
            body = resp.read().decode("utf-8")
            if resp.status != 200:
                snippet = (body or "")[:300]
                logger.warning(
                    "Polymarket orderbook HTTP error: status=%s body_snippet=%s",
                    resp.status,
                    snippet,
                )
                return result
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.warning(
            "Polymarket orderbook request failed: exception=%s type=%s",
            e,
            type(e).__name__,
        )
        return result

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        logger.warning("Polymarket orderbook invalid JSON: %s", e)
        return result

    if not isinstance(data, dict):
        logger.warning("Polymarket orderbook response not a dict: %s", type(data))
        return result

    def parse_price(val):
        if val is None:
            return None
        try:
            p = float(val)
            return p if 0 <= p <= 1 else None
        except (TypeError, ValueError):
            return None

    best_bid = None
    best_ask = None
    bids = data.get("bids")
    if isinstance(bids, list) and len(bids) > 0:
        first = bids[0]
        if isinstance(first, dict) and "price" in first:
            best_bid = parse_price(first["price"])
        elif isinstance(first, (list, tuple)) and len(first) >= 1:
            best_bid = parse_price(first[0])

    asks = data.get("asks")
    if isinstance(asks, list) and len(asks) > 0:
        first = asks[0]
        if isinstance(first, dict) and "price" in first:
            best_ask = parse_price(first["price"])
        elif isinstance(first, (list, tuple)) and len(first) >= 1:
            best_ask = parse_price(first[0])

    result["best_bid"] = best_bid
    result["best_ask"] = best_ask
    if best_bid is not None and best_ask is not None:
        result["mid_price"] = round((best_bid + best_ask) / 2, 4)
        result["spread"] = round(best_ask - best_bid, 4)

    logger.info(
        "Polymarket orderbook parsed: best_bid=%s best_ask=%s mid_price=%s spread=%s",
        result["best_bid"],
        result["best_ask"],
        result["mid_price"],
        result["spread"],
    )
    return result


class PolymarketDataFeed:
    """
    Data feed that fetches price from Polymarket CLOB API.
    On request failure or invalid response, returns last known price or fallback_price.
    """

    def __init__(
        self,
        api_base="https://clob.polymarket.com",
        token_id="",
        fallback_price=0.5,
        timeout_seconds=10,
        gamma_fallback_price=None,
        gamma_price_provider=None,
        gamma_cache_ttl_seconds=30,
        price_source="clob",
    ):
        self.api_base = api_base.rstrip("/")
        self.token_id = token_id
        self.fallback_price = float(fallback_price)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._last_price = None
        self._gamma_fallback_price = None
        self._gamma_price_provider = gamma_price_provider if callable(gamma_price_provider) else None
        self._gamma_cache_ttl = max(1, int(gamma_cache_ttl_seconds))
        self._gamma_cache_price = None
        self._gamma_cache_ts = 0.0
        self._price_source = (price_source or "clob").strip().lower()
        if self._price_source not in ("gamma", "clob"):
            self._price_source = "clob"
        if gamma_fallback_price is not None:
            try:
                p = float(gamma_fallback_price)
                if 0 <= p <= 1:
                    self._gamma_fallback_price = p
            except (TypeError, ValueError):
                pass

    def _get_price_gamma_only(self):
        """Return price using only gamma chain: cache -> fresh provider -> static gamma_fallback -> fallback_price."""
        if self._gamma_price_provider is not None:
            now = time.monotonic()
            if (
                self._gamma_cache_price is not None
                and (now - self._gamma_cache_ts) < self._gamma_cache_ttl
            ):
                logger.info(
                    "Polymarket gamma mode: using refreshed gamma_price=%s from cache",
                    self._gamma_cache_price,
                )
                self._last_price = self._gamma_cache_price
                return round(self._gamma_cache_price, 4)
            try:
                p = self._gamma_price_provider()
                if p is not None:
                    try:
                        p = float(p)
                        if 0 <= p <= 1:
                            self._gamma_cache_price = p
                            self._gamma_cache_ts = now
                            self._last_price = p
                            logger.info(
                                "Polymarket gamma mode: using refreshed gamma_price=%s from provider",
                                p,
                            )
                            return round(p, 4)
                    except (TypeError, ValueError):
                        pass
            except Exception as e:
                logger.debug(
                    "Polymarket gamma_price_provider failed: %s: %s",
                    type(e).__name__,
                    e,
                )
        if self._gamma_fallback_price is not None and 0 <= self._gamma_fallback_price <= 1:
            logger.info(
                "Polymarket gamma mode: using gamma_fallback_price=%s",
                self._gamma_fallback_price,
            )
            self._last_price = self._gamma_fallback_price
            return round(self._gamma_fallback_price, 4)
        logger.info(
            "Polymarket gamma mode: using fallback_price=%s (no gamma source)",
            self.fallback_price,
        )
        return round(self.fallback_price, 4)

    def get_price(self):
        side = "BUY"
        if not self.token_id:
            if self._last_price is not None:
                logger.info("Polymarket price: no token_id, using last_price=%s", self._last_price)
                return round(self._last_price, 4)
            logger.warning("Polymarket price: no token_id, using fallback_price=%s", self.fallback_price)
            return round(self.fallback_price, 4)

        if self._price_source == "gamma":
            logger.info("Polymarket price_source=gamma active (no CLOB request)")
            return self._get_price_gamma_only()

        url = f"{self.api_base}/price?token_id={self.token_id}&side={side}"
        logger.info("Polymarket price request: url=%s token_id=%s side=%s", url, self.token_id, side)

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                if resp.status != 200:
                    snippet = (body or "")[:300]
                    logger.warning(
                        "Polymarket price HTTP error: status=%s body_snippet=%s",
                        resp.status,
                        snippet,
                    )
                    return self._fallback("non-200 status")
        except (urllib.error.URLError, OSError, ValueError) as e:
            logger.warning(
                "Polymarket price fetch failed: exception=%s type=%s",
                e,
                type(e).__name__,
            )
            return self._fallback("request failed")

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            logger.warning("Polymarket price invalid JSON: %s", e)
            return self._fallback("invalid JSON")

        price = data.get("price")
        if price is None:
            logger.warning(
                "Polymarket price response missing 'price' field, keys=%s",
                list(data.keys()) if isinstance(data, dict) else "not a dict",
            )
            return self._fallback("missing price field")
        try:
            price = float(price)
        except (TypeError, ValueError) as e:
            logger.warning("Polymarket price not a number: value=%s error=%s", price, e)
            return self._fallback("price not a number")

        if not (0 <= price <= 1):
            logger.warning("Polymarket price out of range [0,1]: price=%s", price)
            return self._fallback("price out of range [0,1]")

        self._last_price = price
        logger.info("Polymarket price parsed: price=%s source=%s", price, f"{self.api_base}/price")
        return round(price, 4)

    def _fallback(self, reason):
        if self._last_price is not None:
            logger.info("Polymarket using last_price=%s (reason: %s)", self._last_price, reason)
            return round(self._last_price, 4)
        if self._gamma_price_provider is not None:
            now = time.monotonic()
            if (
                self._gamma_cache_price is not None
                and (now - self._gamma_cache_ts) < self._gamma_cache_ttl
            ):
                logger.info(
                    "Polymarket using refreshed gamma_price=%s from cache (reason: %s)",
                    self._gamma_cache_price,
                    reason,
                )
                return round(self._gamma_cache_price, 4)
            try:
                p = self._gamma_price_provider()
                if p is not None:
                    try:
                        p = float(p)
                        if 0 <= p <= 1:
                            self._gamma_cache_price = p
                            self._gamma_cache_ts = now
                            logger.info(
                                "Polymarket using refreshed gamma_price=%s from fresh provider (reason: %s)",
                                p,
                                reason,
                            )
                            return round(p, 4)
                    except (TypeError, ValueError):
                        pass
            except Exception as e:
                logger.debug(
                    "Polymarket gamma_price_provider failed: %s: %s",
                    type(e).__name__,
                    e,
                )
        if self._gamma_fallback_price is not None and 0 <= self._gamma_fallback_price <= 1:
            logger.info(
                "Polymarket using gamma_fallback_price=%s (reason: %s)",
                self._gamma_fallback_price,
                reason,
            )
            return round(self._gamma_fallback_price, 4)
        logger.warning("Polymarket using fallback_price=%s (reason: %s)", self.fallback_price, reason)
        return round(self.fallback_price, 4)
