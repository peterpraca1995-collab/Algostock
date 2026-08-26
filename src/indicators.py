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
