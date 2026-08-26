"""Backtest existujúcej stratégie na historických sviečkach.

Používa presne tú istú rozhodovaciu logiku ako živé obchodovanie —
`strategy.decide()` a všetky funkcie z `indicators.py` — len namiesto
Alpaca účtu simuluje pozíciu v pamäti. Žiadna duplicita pravidiel medzi
backtestom a živou appkou: čo sa tu overí, platí aj naživo.

Zjednodušenia oproti realite (všetky smerom ku konzervatívnejšiemu, nie
optimistickejšiemu výsledku):
  - Vstup aj exit na signál sa plnia na CLOSE sviečky, na ktorej padol —
    naživo by to bolo o pár sekúnd/minút neskôr, za mierne inú cenu.
  - Stop-loss/take-profit sa v rámci jednej sviečky kontrolujú cez jej
    high/low. Ak by boli dotknuté oba v tej istej sviečke, počíta sa
    horší prípad (stop) — v realite by poradie mohlo byť aj opačné.
  - Bez poplatkov (Alpaca ich na akcie nemá) a bez spreadu/sklzu (IEX
    feed spread nedáva) — reálny výsledok by teda bol o niečo horší.
  - `fib` sa pri každom tiku počíta nanovo len z dát PO tento tik (žiadny
    pohľad do budúcnosti) — presne ako naživo, kde budúcnosť ešte nie je.

Pozor: `end` nesmie byť dnešok, kým sa dnešná session ešte neskončila —
posledná stiahnutá sviečka (čokoľvek, čo Alpaca práve má) by sa nesprávne
vyhodnotila ako "koniec dňa" skôr, než trh reálne zavrel. `run_backtest.py`
bez argumentov preto berie do včerajška, nie do dneška.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import alpaca_client, indicators
from .config import SETTINGS
from .strategy import Snapshot, decide

# koľko dní pred `start` sa dodatočne stiahne, nech majú najdlhšie
# indikátory (fib_lookback=60 barov) čím sa "zohriať" už na prvý deň rozsahu
WARMUP_DAYS = 15


def _parse_ts(t: str) -> datetime:
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def _minutes_to_close_at(s: dict, ts: datetime) -> float:
    tz = ZoneInfo(s["market_tz"])
    local = ts.astimezone(tz)
    ch, cm = (int(x) for x in s["market_close"].split(":"))
    close_t = local.replace(hour=ch, minute=cm, second=0, microsecond=0)
    return (close_t - local).total_seconds() / 60


def backtest_symbol(symbol: str, start: date, end: date) -> dict:
    """Vráti {"trades": [...], "bars_used": N} pre jeden symbol."""
    s = SETTINGS
    fetch_from = (datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
                  - timedelta(days=WARMUP_DAYS))
    bars = alpaca_client.get_bars(
        symbol, s["timeframe"], fetch_from.strftime("%Y-%m-%dT%H:%M:%SZ"), limit_total=20000
    )
    if not bars:
        return {"trades": [], "bars_used": 0}

    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]

    ema_fast_arr = indicators.ema(closes, s["ema_fast"])
    ema_slow_arr = indicators.ema(closes, s["ema_slow"])
    rsi_arr = indicators.rsi(closes, s["rsi_period"])
    _, _, macd_hist_arr = indicators.macd(closes, s["macd_fast"], s["macd_slow"], s["macd_signal"])
    atr_arr = indicators.atr(highs, lows, closes, s["atr_period"])
    cci_arr = indicators.cci(highs, lows, closes, s["cci_period"])
    _, _, _, bb_arr = indicators.bollinger_bands(closes, s["bb_period"], s["bb_std"])
    stoch_k_arr, stoch_d_arr = indicators.stochastic(
        highs, lows, closes, s["stoch_k_period"], s["stoch_d_period"]
    )
    vwap_arr = indicators.vwap_session(bars)
    adx_arr = indicators.adx(highs, lows, closes, s["adx_period"])

    start_str, end_str = start.isoformat(), end.isoformat()
    trades: list[dict] = []
    position: dict | None = None

    def close(exit_t: str, exit_price: float, reason: str) -> None:
        pnl = (exit_price - position["entry_price"]) * position["qty"]
        trades.append({
            "symbol": symbol,
            "entry_t": position["entry_t"], "entry_price": round(position["entry_price"], 2),
            "exit_t": exit_t, "exit_price": round(exit_price, 2),
            "qty": position["qty"], "pnl": round(pnl, 2),
            "pnl_pct": round((exit_price / position["entry_price"] - 1) * 100, 2),
            "reason": reason,
        })

    for i, b in enumerate(bars):
        day = b["t"][:10]
        if day < start_str or day > end_str:
            continue  # zahrievacie dáta pred `start`, alebo mimo rozsahu
        is_last_of_day = (i + 1 == len(bars)) or (bars[i + 1]["t"][:10] != day)

        # stop-loss / take-profit v rámci tejto sviečky (predtým, než sa
        # vôbec pozrieme na nový signál — naživo to strážia priamo na Alpaca)
        if position:
            hit_stop = b["l"] <= position["stop"]
            hit_target = b["h"] >= position["target"]
            if hit_stop:
                close(b["t"], position["stop"], "stop-loss")
                position = None
            elif hit_target:
                close(b["t"], position["target"], "take-profit")
                position = None

        if ema_slow_arr[i] is None or adx_arr[i] is None:
            continue  # ešte nedosť histórie na indikátory tohto tiku

        fib = indicators.fibonacci_levels(highs[: i + 1], lows[: i + 1], s["fib_lookback"])
        snap = Snapshot(
            price=closes[i], prev_price=closes[i - 1] if i > 0 else None,
            ema_fast=ema_fast_arr[i], ema_slow=ema_slow_arr[i], rsi=rsi_arr[i],
            macd_hist=macd_hist_arr[i], cci=cci_arr[i], fib=fib,
            bb_percent_b=bb_arr[i], stoch_k=stoch_k_arr[i], stoch_d=stoch_d_arr[i],
            prev_stoch_k=stoch_k_arr[i - 1] if i > 0 else None,
            prev_stoch_d=stoch_d_arr[i - 1] if i > 0 else None,
            vwap=vwap_arr[i], adx=adx_arr[i],
        )

        if position is None:
            mins_to_close = _minutes_to_close_at(s, _parse_ts(b["t"]))
            if mins_to_close <= s["flatten_before_close_minutes"]:
                continue  # tesne pred koncom dňa sa nové pozície neotvárajú
            signal, _, _ = decide(snap, has_position=False)
            if signal == "BUY":
                atr_val = atr_arr[i]
                qty = math.floor(s["allocation_per_symbol_usd"] / snap.price)
                if qty >= 1 and atr_val:
                    position = {
                        "entry_t": b["t"], "entry_price": snap.price, "qty": qty,
                        "stop": snap.price - atr_val * s["atr_stop_mult"],
                        "target": snap.price + atr_val * s["atr_target_mult"],
                    }
        else:
            signal, _, _ = decide(snap, has_position=True)
            if signal == "SELL":
                close(b["t"], snap.price, "signál")
                position = None
            elif is_last_of_day:
                close(b["t"], snap.price, "koniec dňa")
                position = None

    return {"trades": trades, "bars_used": len(bars)}


def run_backtest(start: date, end: date) -> dict:
    """Backtest všetkých symbolov zo settings.json, vráti aj súhrn."""
    per_symbol = {}
    all_trades: list[dict] = []
    for symbol in SETTINGS["tickers"]:
        r = backtest_symbol(symbol, start, end)
        per_symbol[symbol] = r
        all_trades.extend(r["trades"])

    all_trades.sort(key=lambda t: t["entry_t"])
    wins = [t for t in all_trades if t["pnl"] > 0]
    losses = [t for t in all_trades if t["pnl"] <= 0]
    total_pnl = round(sum(t["pnl"] for t in all_trades), 2)

    summary = {
        "start": start.isoformat(), "end": end.isoformat(),
        "trades": len(all_trades),
        "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(all_trades), 1) if all_trades else None,
        "total_pnl": total_pnl,
        "avg_pnl_per_trade": round(total_pnl / len(all_trades), 2) if all_trades else None,
        "avg_win": round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else None,
        "best_trade": max(all_trades, key=lambda t: t["pnl"]) if all_trades else None,
        "worst_trade": min(all_trades, key=lambda t: t["pnl"]) if all_trades else None,
    }
    return {"summary": summary, "trades": all_trades, "per_symbol": per_symbol}
