"""Technické indikátory, čistý Python (žiadna pandas/numpy závislosť).

Každá funkcia vracia zoznam rovnakej dĺžky ako vstup; kým nie je dosť dát na
výpočet, hodnota je None.
"""
from __future__ import annotations


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Wilderovo RSI."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from_avg(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from_avg(avg_gain, avg_loss)
    return out


def _rsi_from_avg(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line: list[float | None] = [
        (a - b) if a is not None and b is not None else None
        for a, b in zip(ema_fast, ema_slow)
    ]
    # signal = EMA zo strany, kde macd_line už existuje
    first = next((i for i, v in enumerate(macd_line) if v is not None), None)
    signal_line: list[float | None] = [None] * len(closes)
    if first is not None:
        tail = [v for v in macd_line[first:]]  # type: ignore[misc]
        sig_tail = ema(tail, signal)  # type: ignore[arg-type]
        for i, v in enumerate(sig_tail):
            signal_line[first + i] = v
    hist: list[float | None] = [
        (m - s) if m is not None and s is not None else None
        for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, hist


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out
    trs = [0.0] * n
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs[i] = tr
    avg = sum(trs[1 : period + 1]) / period
    out[period] = avg
    for i in range(period + 1, n):
        avg = (avg * (period - 1) + trs[i]) / period
        out[i] = avg
    return out


def cci(highs: list[float], lows: list[float], closes: list[float], period: int = 20) -> list[float | None]:
    """Commodity Channel Index. >100 = silný bullish moment, <-100 = silný bearish moment."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    typical = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(n)]
    for i in range(period - 1, n):
        window = typical[i - period + 1 : i + 1]
        sma_tp = sum(window) / period
        mean_dev = sum(abs(tp - sma_tp) for tp in window) / period
        if mean_dev == 0:
            out[i] = 0.0
        else:
            out[i] = (typical[i] - sma_tp) / (0.015 * mean_dev)
    return out


def fibonacci_levels(highs: list[float], lows: list[float], lookback: int = 60) -> dict | None:
    """Swing high/low za posledných `lookback` sviečok + retracement úrovne.

    Vracia dict s hranicami swingu, smerom trendu a úrovňami 23.6/38.2/50/61.8/78.6%.
    None, ak nie je dosť histórie.
    """
    n = len(highs)
    if n < lookback:
        return None
    window_highs = highs[-lookback:]
    window_lows = lows[-lookback:]
    swing_high = max(window_highs)
    swing_low = min(window_lows)
    idx_high = len(window_highs) - 1 - window_highs[::-1].index(swing_high)
    idx_low = len(window_lows) - 1 - window_lows[::-1].index(swing_low)
    uptrend = idx_low < idx_high  # low bolo skôr než high => rastúci swing
    span = swing_high - swing_low
    if span <= 0:
        return None
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    if uptrend:
        levels = {f"{r * 100:.1f}%": swing_high - span * r for r in ratios}
    else:
        levels = {f"{r * 100:.1f}%": swing_low + span * r for r in ratios}
    return {
        "swing_high": swing_high,
        "swing_low": swing_low,
        "uptrend": uptrend,
        "levels": levels,
    }


def bollinger_bands(
    closes: list[float], period: int = 20, num_std: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None], list[float | None]]:
    """Vracia (horné pásmo, stred/SMA, dolné pásmo, %B).

    %B = 0 na dolnom pásme, 1 na hornom, 0.5 v strede — ukazuje polohu ceny
    voči volatilite, nezávisle od trendových indikátorov.
    """
    n = len(closes)
    upper: list[float | None] = [None] * n
    mid: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    percent_b: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        m = sum(window) / period
        variance = sum((c - m) ** 2 for c in window) / period
        sd = variance ** 0.5
        u = m + num_std * sd
        l = m - num_std * sd
        mid[i], upper[i], lower[i] = m, u, l
        percent_b[i] = (closes[i] - l) / (u - l) if (u - l) != 0 else 0.5
    return upper, mid, lower, percent_b


def stochastic(
    highs: list[float], lows: list[float], closes: list[float], k_period: int = 14, d_period: int = 3
) -> tuple[list[float | None], list[float | None]]:
    """Stochastic oscillator (%K, %D) — časovanie obratu, iný výpočet než RSI."""
    n = len(closes)
    k: list[float | None] = [None] * n
    for i in range(k_period - 1, n):
        hh = max(highs[i - k_period + 1 : i + 1])
        ll = min(lows[i - k_period + 1 : i + 1])
        k[i] = 100 * (closes[i] - ll) / (hh - ll) if (hh - ll) != 0 else 50.0
    d: list[float | None] = [None] * n
    for i in range(n):
        if k[i] is None:
            continue
        window = [k[j] for j in range(max(0, i - d_period + 1), i + 1) if k[j] is not None]
        if len(window) == d_period:
            d[i] = sum(window) / d_period
    return k, d


def vwap_session(bars: list[dict]) -> list[float | None]:
    """Kumulatívny (session-anchored) VWAP — resetuje sa na začiatku každého
    obchodného dňa (podľa dátumu v `t` timestampe sviečky). Používa objem,
    na rozdiel od ostatných indikátorov tu počítaných len z ceny."""
    out: list[float | None] = []
    cum_pv = 0.0
    cum_vol = 0.0
    current_day = None
    for b in bars:
        day = b["t"][:10]
        if day != current_day:
            current_day = day
            cum_pv = 0.0
            cum_vol = 0.0
        typical = (b["h"] + b["l"] + b["c"]) / 3
        vol = b.get("v") or 0
        cum_pv += typical * vol
        cum_vol += vol
        out.append(cum_pv / cum_vol if cum_vol > 0 else None)
    return out


def adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    """Average Directional Index (Wilder) — sila trendu (0-100), bez smeru.
    Používa sa ako filter: nízke ADX = trh nemá trend, signály sa ignorujú."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period * 2:
        return out

    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    def _di(smoothed_dm: float, smoothed_tr: float) -> float:
        return 100 * smoothed_dm / smoothed_tr if smoothed_tr != 0 else 0.0

    atr_s = sum(tr[1 : period + 1]) / period
    plus_dm_s = sum(plus_dm[1 : period + 1]) / period
    minus_dm_s = sum(minus_dm[1 : period + 1]) / period

    dx: list[float | None] = [None] * n
    plus_di = _di(plus_dm_s, atr_s)
    minus_di = _di(minus_dm_s, atr_s)
    dx[period] = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) != 0 else 0.0

    for i in range(period + 1, n):
        atr_s = (atr_s * (period - 1) + tr[i]) / period
        plus_dm_s = (plus_dm_s * (period - 1) + plus_dm[i]) / period
        minus_dm_s = (minus_dm_s * (period - 1) + minus_dm[i]) / period
        plus_di = _di(plus_dm_s, atr_s)
        minus_di = _di(minus_dm_s, atr_s)
        dx[i] = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) != 0 else 0.0

    valid_dx = [v for v in dx[period : period * 2] if v is not None]
    if len(valid_dx) < period:
        return out
    adx_val = sum(valid_dx) / period
    idx = period * 2 - 1
    out[idx] = adx_val
    for i in range(idx + 1, n):
        if dx[i] is None:
            continue
        adx_val = (adx_val * (period - 1) + dx[i]) / period
        out[i] = adx_val
    return out
