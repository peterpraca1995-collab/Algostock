"""Tenký wrapper nad Alpaca REST API (trading + market data)."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import requests

from . import config

_HEADERS = {
    "APCA-API-KEY-ID": config.ALPACA_KEY_ID,
    "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
}


class AlpacaError(RuntimeError):
    pass


def _get(base: str, path: str, params: dict | None = None) -> Any:
    r = requests.get(f"{base}{path}", headers=_HEADERS, params=params, timeout=20)
    if r.status_code >= 400:
        raise AlpacaError(f"GET {path} -> {r.status_code}: {r.text}")
    return r.json()


def _post(base: str, path: str, payload: dict) -> Any:
    r = requests.post(f"{base}{path}", headers=_HEADERS, json=payload, timeout=20)
    if r.status_code >= 400:
        raise AlpacaError(f"POST {path} -> {r.status_code}: {r.text}")
    return r.json()


def _delete(base: str, path: str) -> Any:
    r = requests.delete(f"{base}{path}", headers=_HEADERS, timeout=20)
    if r.status_code >= 400:
        raise AlpacaError(f"DELETE {path} -> {r.status_code}: {r.text}")
    return r.json() if r.text else None


# ---------------------------------------------------------------- account --

def get_account() -> dict:
    return _get(config.ALPACA_TRADING_BASE, "/v2/account")


def get_positions() -> list[dict]:
    return _get(config.ALPACA_TRADING_BASE, "/v2/positions")


def get_position(symbol: str) -> dict | None:
    try:
        return _get(config.ALPACA_TRADING_BASE, f"/v2/positions/{symbol}")
    except AlpacaError as e:
        if "404" in str(e):
            return None
        raise


def has_open_order(symbol: str) -> bool:
    """True, ak už na symbol existuje nevyplnená (čakajúca) objednávka."""
    orders = _get(
        config.ALPACA_TRADING_BASE, "/v2/orders",
        {"status": "open", "symbols": symbol, "limit": 10},
    )
    return len(orders) > 0


# ------------------------------------------------------------------ data --

def get_bars(symbol: str, timeframe: str, start_iso: str, limit_total: int = 500) -> list[dict]:
    """Stiahne hodinové (alebo iné) sviečky, so stránkovaním."""
    bars: list[dict] = []
    page_token = None
    while len(bars) < limit_total:
        params = {
            "timeframe": timeframe,
            "start": start_iso,
            "limit": min(1000, limit_total - len(bars)),
            "feed": "iex",
            "adjustment": "raw",
        }
        if page_token:
            params["page_token"] = page_token
        data = _get(config.ALPACA_DATA_BASE, f"/v2/stocks/{symbol}/bars", params)
        bars.extend(data.get("bars", []))
        page_token = data.get("next_page_token")
        if not page_token:
            break
    return bars


# ---------------------------------------------------------------- orders --

def submit_bracket_buy(symbol: str, qty: int, stop_price: float, target_price: float) -> dict:
    payload = {
        "symbol": symbol,
        "qty": str(qty),
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
        "order_class": "bracket",
        "take_profit": {"limit_price": round(target_price, 2)},
        "stop_loss": {"stop_price": round(stop_price, 2)},
    }
    return _post(config.ALPACA_TRADING_BASE, "/v2/orders", payload)


def close_position(symbol: str) -> dict:
    return _delete(config.ALPACA_TRADING_BASE, f"/v2/positions/{symbol}")


def get_clock() -> dict:
    return _get(config.ALPACA_TRADING_BASE, "/v2/clock")
