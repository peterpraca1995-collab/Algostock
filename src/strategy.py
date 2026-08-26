"""Rozhodovacia logika: viacero indikátorov hlasuje, obchoduje sa len pri zhode.

Hlasy (každý -1 / 0 / +1):
  trend  – EMA9 vs EMA21 (smer)
  rsi    – RSI14 momentum (mimo extrémov)
  macd   – MACD histogram (smer momentu)
  cci    – CCI20 (silný momentum breakout)
  fib    – cena sa odráža od Fibonacci retracement úrovne v smere trendu
  bb     – Bollinger %B (odraz od pásma — volatilita/mean-reversion)
  stoch  – Stochastic %K/%D kríž z extrému (časovanie obratu)
  vwap   – cena nad/pod session VWAP (objemovo vážená cena)

Súčet hlasov (skóre) sa porovná s prahom v settings.json. ADX navyše
funguje ako filter sily trendu — pri slabom trende appka signál ignoruje,
aj keby skóre inak prah splnilo (chráni pred obchodovaním v "chaose").
"""
from __future__ import annotations

from dataclasses import dataclass

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
    bb_percent_b: float | None
    stoch_k: float | None
    stoch_d: float | None
    prev_stoch_k: float | None
    prev_stoch_d: float | None
    vwap: float | None
    adx: float | None


def _vote_trend(snap: Snapshot) -> int:
    if snap.ema_fast is None or snap.ema_slow is None:
        return 0
    return 1 if snap.ema_fast > snap.ema_slow else -1


def _vote_rsi(snap: Snapshot, s: dict) -> int:
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


def _vote_bb(snap: Snapshot) -> int:
    """Cena blízko dolného pásma a odráža sa hore => bullish (mean-reversion),
    symetricky pri hornom pásme."""
    if snap.bb_percent_b is None or snap.prev_price is None:
        return 0
    if snap.bb_percent_b <= 0.15 and snap.price > snap.prev_price:
        return 1
    if snap.bb_percent_b >= 0.85 and snap.price < snap.prev_price:
        return -1
    return 0


def _vote_stoch(snap: Snapshot) -> int:
    """Kríž %K nad %D z prepredanosti (<30) => bullish, opačne z prekúpenosti (>70)."""
    if None in (snap.stoch_k, snap.stoch_d, snap.prev_stoch_k, snap.prev_stoch_d):
        return 0
    crossed_up = snap.prev_stoch_k <= snap.prev_stoch_d and snap.stoch_k > snap.stoch_d
    crossed_down = snap.prev_stoch_k >= snap.prev_stoch_d and snap.stoch_k < snap.stoch_d
    if crossed_up and snap.stoch_k < 30:
        return 1
    if crossed_down and snap.stoch_k > 70:
        return -1
    return 0


def _vote_vwap(snap: Snapshot) -> int:
    if snap.vwap is None or snap.vwap == 0:
        return 0
    diff_pct = (snap.price - snap.vwap) / snap.vwap
    if diff_pct > 0.001:
        return 1
    if diff_pct < -0.001:
        return -1
    return 0


def decide(snap: Snapshot, has_position: bool, settings: dict | None = None) -> tuple[str, str, dict]:
    """Vráti (signal, dôvod, votes). signal je 'BUY' | 'SELL' | 'HOLD'.

    `settings`, ak je zadané, prebije globálny SETTINGS — používa sa na
    per-symbolové prahy (`config.effective_settings`) a na sweep v
    scripts/optimize.py, ktorý skúša veľa kombinácií bez zápisu na disk."""
    s = settings if settings is not None else SETTINGS
    votes = {
        "trend": _vote_trend(snap),
        "rsi": _vote_rsi(snap, s),
        "macd": _vote_macd(snap),
        "cci": _vote_cci(snap),
        "fib": _vote_fib(snap),
        "bb": _vote_bb(snap),
        "stoch": _vote_stoch(snap),
        "vwap": _vote_vwap(snap),
    }
    score = sum(votes.values())
    votes_str = ", ".join(f"{k}={v:+d}" for k, v in votes.items())

    buy_th = s["signal_buy_threshold"]
    sell_th = s["signal_sell_threshold"]

    if not has_position:
        if score >= buy_th:
            if snap.adx is not None and snap.adx < s["adx_min_trend"]:
                return (
                    "HOLD",
                    f"skóre {score:+d} by stačilo, ale trend je slabý "
                    f"(ADX={snap.adx:.1f} < {s['adx_min_trend']}), signál ignorovaný ({votes_str})",
                    votes,
                )
            return "BUY", f"skóre {score:+d} ≥ prah {buy_th:+d}, ADX={_fmt(snap.adx)} ({votes_str})", votes
        return "HOLD", f"skóre {score:+d} < prah {buy_th:+d} na vstup ({votes_str})", votes
    else:
        if score <= sell_th:
            return "SELL", f"skóre {score:+d} ≤ prah {sell_th:+d}, obrat trendu ({votes_str})", votes
        return "HOLD", f"pozícia drží, skóre {score:+d} nad prahom na exit ({votes_str})", votes


def _fmt(v: float | None) -> str:
    return f"{v:.1f}" if v is not None else "—"
