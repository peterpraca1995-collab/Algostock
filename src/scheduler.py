"""Jednoduchý scheduler na pozadí: spustí engine.run_all() každú hodinu počas obchodných hodín."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import engine
from .config import SETTINGS

_tz = ZoneInfo(SETTINGS["market_tz"])
_last_run: datetime | None = None
_next_run: datetime | None = None
_lock = threading.Lock()


def _parse_hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _is_market_open(now: datetime) -> bool:
    if now.weekday() >= 5:  # so/ne
        return False
    oh, om = _parse_hm(SETTINGS["market_open"])
    ch, cm = _parse_hm(SETTINGS["market_close"])
    open_t = now.replace(hour=oh, minute=om, second=0, microsecond=0)
    close_t = now.replace(hour=ch, minute=cm, second=0, microsecond=0)
    return open_t <= now <= close_t


def _next_trigger(now: datetime) -> datetime:
    """Najbližší budúci čas HH:{run_minutes_after_hour} v rámci obchodných hodín."""
    minute = SETTINGS["run_minutes_after_hour"]
    candidate = now.replace(minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(hours=1)
    # posuň na najbližší okamih, keď je zároveň trh otvorený
    for _ in range(24 * 8):  # max ~8 dní dopredu
        if _is_market_open(candidate):
            return candidate
        candidate += timedelta(hours=1)
        candidate = candidate.replace(minute=minute, second=0, microsecond=0)
    return candidate


def get_status() -> dict:
    with _lock:
        return {
            "last_run": _last_run.isoformat() if _last_run else None,
            "next_run": _next_run.isoformat() if _next_run else None,
        }


def _loop() -> None:
    global _last_run, _next_run
    while True:
        now = datetime.now(_tz)
        nxt = _next_trigger(now)
        with _lock:
            _next_run = nxt
        sleep_s = max(1.0, (nxt - datetime.now(_tz)).total_seconds())
        time.sleep(min(sleep_s, 3600))  # kontroluj aspoň raz za hodinu (napr. po spánku Macu)
        now = datetime.now(_tz)
        if now >= nxt:
            try:
                engine.run_all()
            finally:
                with _lock:
                    _last_run = now


def start_background() -> None:
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
