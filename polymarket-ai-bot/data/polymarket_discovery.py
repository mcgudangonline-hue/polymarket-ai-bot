"""
Minimal market discovery for Polymarket.
Fetches active markets via the Gamma API events endpoint (read-only).
Events contain their associated markets; we flatten to a list of market dicts.
Used for future market selection; does not affect the trading engine.
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger("polymarket_bot")

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
USER_AGENT = "polymarket-ai-bot/1.0"

DISCOVERY_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://docs.polymarket.com/",
    "Origin": "https://docs.polymarket.com",
}


def _extract_token_id(obj):
    """Extract first CLOB token ID from market/event. Returns None if missing."""
    cids = obj.get("clobTokenIds")
    if isinstance(cids, list) and cids:
        v = cids[0]
        return str(v) if v is not None else None
    if isinstance(cids, str) and cids.strip():
        try:
            parsed = json.loads(cids)
            if isinstance(parsed, list) and parsed:
                v = parsed[0]
                return str(v) if v is not None else None
        except json.JSONDecodeError:
            pass
    return None


def _to_float(val):
    """Safely coerce to float. Returns None if not possible."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_bool_explicit(val):
    """
    Map API value to bool only when explicit. Returns True/False/None.
    None means field missing or not a clear boolean.
    """
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        low = val.strip().lower()
        if low in ("true", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
    return None


def _parse_gamma_price(obj):
    """
    Extract first outcome price from outcomePrices (Gamma API).
    outcomePrices may be a JSON string or a list. Returns float in [0,1] or None.
    """
    raw = obj.get("outcomePrices")
    if raw is None:
        return None
    if isinstance(raw, list) and raw:
        p = _to_float(raw[0])
        if p is not None and 0 <= p <= 1:
            return p
        return None
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                p = _to_float(parsed[0])
                if p is not None and 0 <= p <= 1:
                    return p
        except (json.JSONDecodeError, IndexError, TypeError):
            pass
    return None


def _parse_markets_from_events(raw):
    """Parse events response into list of market dicts. Returns [] if invalid."""
    if not isinstance(raw, list):
        return []
    result = []
    for event in raw:
        if not isinstance(event, dict):
            continue
        event_title = event.get("title") or event.get("question") or ""
        event_volume = _to_float(
            event.get("volumeNum")
            or event.get("volume24hr")
            or event.get("volume")
        )
        event_liquidity = _to_float(event.get("liquidityNum") or event.get("liquidity"))
        event_gamma_price = _parse_gamma_price(event)
        markets = event.get("markets")
        event_enable_order_book = _to_bool_explicit(event.get("enableOrderBook"))
        event_accepting_orders = _to_bool_explicit(event.get("acceptingOrders"))
        event_clob_token_ids = event.get("clobTokenIds")
        event_outcome_prices = event.get("outcomePrices")

        if not isinstance(markets, list):
            token_id = _extract_token_id(event)
            if token_id:
                title = event_title or event.get("question") or ""
                result.append({
                    "title": title,
                    "token_id": token_id,
                    "liquidity": event_liquidity,
                    "volume": event_volume,
                    "gamma_price": event_gamma_price,
                    "enableOrderBook": event_enable_order_book,
                    "acceptingOrders": event_accepting_orders,
                    "clobTokenIds": event_clob_token_ids,
                    "outcomePrices": event_outcome_prices,
                })
            continue
        for m in markets:
            if not isinstance(m, dict):
                continue
            token_id = _extract_token_id(m)
            if not token_id:
                continue
            title = m.get("question") or m.get("title") or event_title or ""
            liquidity = _to_float(m.get("liquidityNum") or m.get("liquidity"))
            if liquidity is None:
                liquidity = event_liquidity
            volume = _to_float(m.get("volumeNum") or m.get("volume24hr") or m.get("volume"))
            if volume is None:
                volume = event_volume
            gamma_price = _parse_gamma_price(m)
            if gamma_price is None:
                gamma_price = event_gamma_price
            enable_order_book = _to_bool_explicit(m.get("enableOrderBook"))
            if enable_order_book is None:
                enable_order_book = event_enable_order_book
            accepting_orders = _to_bool_explicit(m.get("acceptingOrders"))
            if accepting_orders is None:
                accepting_orders = event_accepting_orders
            clob_token_ids = m.get("clobTokenIds") if m.get("clobTokenIds") is not None else event_clob_token_ids
            outcome_prices = m.get("outcomePrices") if m.get("outcomePrices") is not None else event_outcome_prices
            result.append({
                "title": title,
                "token_id": token_id,
                "liquidity": liquidity,
                "volume": volume,
                "gamma_price": gamma_price,
                "enableOrderBook": enable_order_book,
                "acceptingOrders": accepting_orders,
                "clobTokenIds": clob_token_ids,
                "outcomePrices": outcome_prices,
            })
    return result


def _sort_markets(markets, ascending=False):
    """Sort market list by volume (highest first by default). None volume treated as 0."""
    key_volume = lambda m: (m.get("volume") if m.get("volume") is not None else 0) or 0
    return sorted(markets, key=key_volume, reverse=not ascending)


def _fetch_markets_fallback(limit, ascending, timeout_seconds):
    """
    Fallback: GET /markets when /events returns 403.
    Returns list of market dicts with title, token_id, liquidity, volume.
    """
    params = [
        ("limit", max(1, min(limit, 100))),
        ("active", "true"),
        ("closed", "false"),
    ]
    qs = "&".join(f"{k}={v}" for k, v in params)
    url = f"{GAMMA_API_BASE}/markets?{qs}"
    logger.debug("Polymarket discovery fallback URL: %s", url)
    logger.debug("Polymarket discovery fallback headers: %s", DISCOVERY_HEADERS)
    try:
        req = urllib.request.Request(url, headers=DISCOVERY_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            status = getattr(resp, "status", resp.getcode() if callable(getattr(resp, "getcode", None)) else None)
            logger.debug("Polymarket discovery fallback status: %s", status)
            if status != 200:
                body = resp.read().decode("utf-8", errors="replace")
                snippet = (body[:300] + "...") if len(body) > 300 else body
                logger.warning(
                    "Polymarket discovery fallback: non-200 status %s, body snippet: %s",
                    status,
                    snippet,
                )
                return []
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", getattr(e, "status", None))
        try:
            err_body = e.read().decode("utf-8", errors="replace")
            snippet = (err_body[:300] + "...") if len(err_body) > 300 else err_body
        except Exception:
            snippet = "(unable to read body)"
        logger.warning(
            "Polymarket discovery fallback HTTP error: status=%s, body snippet: %s",
            code,
            snippet,
        )
        return []
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.warning(
            "Polymarket discovery fallback request failed: %s: %s",
            type(e).__name__,
            e,
        )
        return []
    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Polymarket discovery fallback: invalid JSON")
        return []
    if not isinstance(raw, list):
        logger.warning("Polymarket discovery fallback: response is not a list")
        return []
    result = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        token_id = _extract_token_id(m)
        if not token_id:
            continue
        title = m.get("question") or m.get("title") or ""
        liquidity = _to_float(m.get("liquidityNum") or m.get("liquidity"))
        volume = _to_float(m.get("volumeNum") or m.get("volume24hr") or m.get("volume"))
        gamma_price = _parse_gamma_price(m)
        enable_order_book = _to_bool_explicit(m.get("enableOrderBook"))
        accepting_orders = _to_bool_explicit(m.get("acceptingOrders"))
        clob_token_ids = m.get("clobTokenIds")
        outcome_prices = m.get("outcomePrices")
        result.append({
            "title": title,
            "token_id": token_id,
            "liquidity": liquidity,
            "volume": volume,
            "gamma_price": gamma_price,
            "enableOrderBook": enable_order_book,
            "acceptingOrders": accepting_orders,
            "clobTokenIds": clob_token_ids,
            "outcomePrices": outcome_prices,
        })
    return _sort_markets(result, ascending)


def fetch_markets(
    limit=50,
    active=True,
    closed=False,
    order="volume_24hr",
    ascending=False,
    timeout_seconds=15,
):
    """
    Fetch active Polymarket markets via the Gamma API /events endpoint.

    Uses GET /events with active, closed, limit only (no server-side order).
    Events contain their associated markets; we flatten to one row per market
    and sort by volume locally.

    Returns a list of dicts with:
        - title: market question/title (from market or event)
        - token_id: first CLOB token ID
        - liquidity: float or None (from liquidityNum / liquidity)
        - volume: float or None (from volumeNum / volume24hr / volume)
        - gamma_price: float in [0,1] or None (first outcome price from outcomePrices)
        - enableOrderBook: bool or None (when available from Gamma)
        - acceptingOrders: bool or None (when available from Gamma)
        - clobTokenIds: raw value or None
        - outcomePrices: raw value or None

    On request or parse failure returns [] and logs.
    """
    params = [
        ("limit", max(1, min(limit, 100))),
        ("active", "true" if active else "false"),
        ("closed", "true" if closed else "false"),
    ]
    qs = "&".join(f"{k}={v}" for k, v in params)
    url = f"{GAMMA_API_BASE}/events?{qs}"

    logger.debug("Polymarket discovery URL: %s (ordering by volume locally)", url)
    logger.debug("Polymarket discovery headers: %s", DISCOVERY_HEADERS)

    try:
        req = urllib.request.Request(url, headers=DISCOVERY_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                status = getattr(resp, "status", resp.getcode() if callable(getattr(resp, "getcode", None)) else None)
                logger.debug("Polymarket discovery HTTP status: %s", status)
                if status != 200:
                    body = resp.read().decode("utf-8", errors="replace")
                    snippet = (body[:300] + "...") if len(body) > 300 else body
                    logger.warning(
                        "Polymarket discovery: non-200 status %s, body snippet: %s",
                        status,
                        snippet,
                    )
                    if status == 403:
                        logger.info("Polymarket discovery: 403 on /events, trying fallback /markets")
                        return _fetch_markets_fallback(limit, ascending, timeout_seconds)
                    return []
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            code = getattr(e, "code", getattr(e, "status", None))
            try:
                err_body = e.read().decode("utf-8", errors="replace")
                snippet = (err_body[:300] + "...") if len(err_body) > 300 else err_body
            except Exception:
                snippet = "(unable to read body)"
            logger.warning(
                "Polymarket discovery HTTP error: status=%s, body snippet: %s",
                code,
                snippet,
            )
            if code == 403:
                logger.info("Polymarket discovery: 403 on /events, trying fallback /markets")
                return _fetch_markets_fallback(limit, ascending, timeout_seconds)
            return []
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.warning(
            "Polymarket discovery request failed: %s: %s",
            type(e).__name__,
            e,
        )
        return []

    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Polymarket discovery: invalid JSON")
        return []

    markets = _parse_markets_from_events(raw)
    sorted_markets = _sort_markets(markets, ascending=ascending)
    logger.info("Polymarket discovery: using local sort by volume (ascending=%s)", ascending)
    return sorted_markets


def fetch_gamma_price_for_token(token_id, timeout_seconds=10, limit=100):
    """
    Fetch current Gamma-derived price for a single market by token_id.
    Uses the Gamma API (events/markets); finds the market with matching token_id
    and returns its gamma_price (first outcome price).
    Returns float in [0,1] or None if not found or on error.
    Used to refresh runtime fallback price without changing the selected market.
    """
    if not token_id or not str(token_id).strip():
        return None
    token_id = str(token_id).strip()
    markets = fetch_markets(limit=max(1, min(limit, 100)), timeout_seconds=timeout_seconds)
    for m in markets:
        if m.get("token_id") == token_id:
            p = m.get("gamma_price")
            if p is not None:
                try:
                    p = float(p)
                    if 0 <= p <= 1:
                        return round(p, 4)
                except (TypeError, ValueError):
                    pass
            return None
    return None
