"""Jeden 'tick' vyhodnotenia: stiahne dáta, spočíta indikátory, rozhodne, zaloguje, prípadne obchoduje."""
from __future__ import annotations

import json
import math
import traceback
from datetime import datetime, timedelta, timezone

from . import alpaca_client, db, indicators
from .alpaca_client import AlpacaError
from .config import SETTINGS
from .strategy import Snapshot, decide


def _start_iso(days: int) -> str:
    start = datetime.now(timezone.utc) - timedelta(days=days)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_symbol(symbol: str) -> dict:
    s = SETTINGS
    ts_now = datetime.now(timezone.utc).isoformat()
    try:
        bars = alpaca_client.get_bars(
            symbol, s["timeframe"], _start_iso(s["bars_lookback_days"]), limit_total=1000
        )
    except AlpacaError as e:
        db.log_tick(ts=ts_now, symbol=symbol, price=None, ema_fast=None, ema_slow=None,
                     rsi=None, macd_hist=None, atr=None, signal="HOLD", action="ERROR",
                     reason="chyba pri sťahovaní dát", qty=None, notes=str(e))
        return {"symbol": symbol, "error": str(e)}

    needed = max(
        s["ema_slow"], s["rsi_period"], s["macd_slow"] + s["macd_signal"],
        s["atr_period"], s["cci_period"], s["fib_lookback"],
        s["bb_period"], s["stoch_k_period"] + s["stoch_d_period"], s["adx_period"] * 2 + 2,
    ) + 2
    if len(bars) < needed:
        db.log_tick(ts=ts_now, symbol=symbol, price=None, ema_fast=None, ema_slow=None,
                     rsi=None, macd_hist=None, atr=None, signal="HOLD", action="HOLD",
                     reason="málo histórie sviečok", qty=None, notes=f"{len(bars)}/{needed}")
        return {"symbol": symbol, "error": "not enough bars"}

    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]

    ema_fast_arr = indicators.ema(closes, s["ema_fast"])
    ema_slow_arr = indicators.ema(closes, s["ema_slow"])
    rsi_arr = indicators.rsi(closes, s["rsi_period"])
    _, _, macd_hist_arr = indicators.macd(closes, s["macd_fast"], s["macd_slow"], s["macd_signal"])
    atr_arr = indicators.atr(highs, lows, closes, s["atr_period"])
    cci_arr = indicators.cci(highs, lows, closes, s["cci_period"])
    fib = indicators.fibonacci_levels(highs, lows, s["fib_lookback"])
    _, _, _, bb_percent_b_arr = indicators.bollinger_bands(closes, s["bb_period"], s["bb_std"])
    stoch_k_arr, stoch_d_arr = indicators.stochastic(highs, lows, closes, s["stoch_k_period"], s["stoch_d_period"])
    vwap_arr = indicators.vwap_session(bars)
    adx_arr = indicators.adx(highs, lows, closes, s["adx_period"])

    try:
        position = alpaca_client.get_position(symbol)
    except AlpacaError:
        position = None
    try:
        pending_order = alpaca_client.has_open_order(symbol)
    except AlpacaError:
        pending_order = False

    snap = Snapshot(
        price=closes[-1],
        prev_price=closes[-2],
        ema_fast=ema_fast_arr[-1],
        ema_slow=ema_slow_arr[-1],
        rsi=rsi_arr[-1],
        macd_hist=macd_hist_arr[-1],
        cci=cci_arr[-1],
        fib=fib,
        bb_percent_b=bb_percent_b_arr[-1],
        stoch_k=stoch_k_arr[-1],
        stoch_d=stoch_d_arr[-1],
        prev_stoch_k=stoch_k_arr[-2],
        prev_stoch_d=stoch_d_arr[-2],
        vwap=vwap_arr[-1],
        adx=adx_arr[-1],
    )
    atr_val = atr_arr[-1]

    signal, reason, votes = decide(snap, has_position=bool(position))
    action, qty, notes = "HOLD", None, ""

    if signal == "BUY" and not position and pending_order:
        action, notes = "HOLD", "BUY signál, ale objednávka na tento symbol už čaká na vyplnenie"

    elif signal == "BUY" and not position:
        allocation = s["allocation_per_symbol_usd"]
        qty = math.floor(allocation / snap.price)
        if qty < 1:
            action, notes = "HOLD", "alokácia na symbol je menšia než cena 1 kusu"
        else:
            stop_price = snap.price - atr_val * s["atr_stop_mult"]
            target_price = snap.price + atr_val * s["atr_target_mult"]
            try:
                order = alpaca_client.submit_bracket_buy(symbol, qty, stop_price, target_price)
                action = "BUY"
                notes = f"order {order.get('id')}, stop={stop_price:.2f}, target={target_price:.2f}"
            except AlpacaError as e:
                action, notes = "HOLD", f"chyba objednávky BUY: {e}"

    elif signal == "SELL" and position:
        qty = float(position.get("qty", 0))
        try:
            alpaca_client.close_position(symbol)
            action = "SELL"
            notes = "pozícia zatvorená (exit signál)"
        except AlpacaError as e:
            action, notes = "HOLD", f"chyba zatvorenia pozície: {e}"

    score = sum(votes.values())
    db.log_tick(
        ts=ts_now, symbol=symbol, price=snap.price,
        ema_fast=snap.ema_fast, ema_slow=snap.ema_slow, rsi=snap.rsi,
        macd_hist=snap.macd_hist, atr=atr_val, cci=snap.cci, score=score,
        bb_percent_b=snap.bb_percent_b, stoch_k=snap.stoch_k, vwap=snap.vwap, adx=snap.adx,
        votes=json.dumps(votes),
        signal=signal, action=action, reason=reason, qty=qty, notes=notes,
    )
    return {"symbol": symbol, "signal": signal, "action": action, "reason": reason, "notes": notes, "score": score}


def run_all() -> list[dict]:
    results = []
    for symbol in SETTINGS["tickers"]:
        try:
            results.append(run_symbol(symbol))
        except Exception as e:  # nikdy nezhoď celý cyklus kvôli jednému symbolu
            results.append({"symbol": symbol, "error": f"{e}\n{traceback.format_exc()}"})

    try:
        acct = alpaca_client.get_account()
        db.log_equity(
            ts=datetime.now(timezone.utc).isoformat(),
            equity=float(acct["equity"]),
            cash=float(acct["cash"]),
            buying_power=float(acct["buying_power"]),
        )
    except Exception as e:
        results.append({"symbol": "_account_", "error": str(e)})

    return results
