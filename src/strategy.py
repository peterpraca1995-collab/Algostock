"""Rozhodovacia logika: viacero indikátorov hlasuje, obchoduje sa len pri zhode.

Hlasy (každý -1 / 0 / +1):
  trend  – EMA9 vs EMA21 (smer)
  rsi    – RSI14 momentum (mimo extrémov)
  macd   – MACD histogram (smer momentu)
  cci    – CCI20 (silný momentum breakout)
  fib    – cena sa odráža od Fibonacci retracement úrovne v smere trendu

Súčet hlasov (skóre od -5 do +5) sa porovná s prahom v settings.json.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import SETTINGS


@dataclass
class Snapshot:
    price: float
    prev_price: float | None
    ema_fast: float | None
    ema_slow: float | None
    rsi: float | None
    macd_hist: float | None
    cci: float | None
    fib: dict | None  # výstup indicators.fibonacci_levels()


def _vote_trend(snap: Snapshot) -> int:
    if snap.ema_fast is None or snap.ema_slow is None:
        return 0
    return 1 if snap.ema_fast > snap.ema_slow else -1


def _vote_rsi(snap: Snapshot) -> int:
    s = SETTINGS
    if snap.rsi is None:
        return 0
    if s["rsi_buy_min"] <= snap.rsi <= s["rsi_buy_max"]:
        return 1
    if s["rsi_sell_min"] <= snap.rsi <= s["rsi_sell_max"] and snap.rsi < 50:
        return -1
    return 0  # extrémy (prekúpené/prepredané) => opatrnosť, žiadny hlas


def _vote_macd(snap: Snapshot) -> int:
    if snap.macd_hist is None:
        return 0
    if snap.macd_hist > 0:
        return 1
    if snap.macd_hist < 0:
        return -1
    return 0


def _vote_cci(snap: Snapshot) -> int:
    if snap.cci is None:
        return 0
    if snap.cci > 100:
        return 1
    if snap.cci < -100:
        return -1
    return 0


def _vote_fib(snap: Snapshot) -> int:
    """Bullish: v uptrende sa cena priblížila k retracement úrovni a odrazila nahor.
    Bearish: symetricky v downtrende."""
    if not snap.fib or snap.prev_price is None:
        return 0
    tolerance = snap.price * 0.004  # ~0.4 % okolo úrovne
    near_level = any(abs(snap.price - lvl) <= tolerance for lvl in snap.fib["levels"].values())
    if not near_level:
        return 0
    bouncing_up = snap.price > snap.prev_price
    bouncing_down = snap.price < snap.prev_price
    if snap.fib["uptrend"] and bouncing_up:
        return 1
    if not snap.fib["uptrend"] and bouncing_down:
        return -1
    return 0


def decide(snap: Snapshot, has_position: bool) -> tuple[str, str, dict]:
    """Vráti (signal, dôvod, votes). signal je 'BUY' | 'SELL' | 'HOLD'."""
    s = SETTINGS
    votes = {
        "trend": _vote_trend(snap),
        "rsi": _vote_rsi(snap),
        "macd": _vote_macd(snap),
        "cci": _vote_cci(snap),
        "fib": _vote_fib(snap),
    }
    score = sum(votes.values())
    votes_str = ", ".join(f"{k}={v:+d}" for k, v in votes.items())

    buy_th = s["signal_buy_threshold"]
    sell_th = s["signal_sell_threshold"]

    if not has_position:
        if score >= buy_th:
            return "BUY", f"skóre {score:+d} ≥ prah {buy_th:+d} ({votes_str})", votes
        return "HOLD", f"skóre {score:+d} < prah {buy_th:+d} na vstup ({votes_str})", votes
    else:
        if score <= sell_th:
            return "SELL", f"skóre {score:+d} ≤ prah {sell_th:+d}, obrat trendu ({votes_str})", votes
        return "HOLD", f"pozícia drží, skóre {score:+d} nad prahom na exit ({votes_str})", votes
