"""SQLite úložisko pre históriu signálov, obchodov a equity krivku."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price REAL,
    ema_fast REAL,
    ema_slow REAL,
    rsi REAL,
    macd_hist REAL,
    atr REAL,
    cci REAL,
    score INTEGER,
    votes TEXT,
    signal TEXT,
    action TEXT,
    reason TEXT,
    qty REAL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_ticks_symbol_ts ON ticks(symbol, ts);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    equity REAL,
    cash REAL,
    buying_power REAL
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)


def log_tick(**kwargs) -> None:
    cols = ", ".join(kwargs.keys())
    placeholders = ", ".join("?" for _ in kwargs)
    with connect() as conn:
        conn.execute(f"INSERT INTO ticks ({cols}) VALUES ({placeholders})", list(kwargs.values()))


def log_equity(ts: str, equity: float, cash: float, buying_power: float) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO equity_snapshots (ts, equity, cash, buying_power) VALUES (?, ?, ?, ?)",
            (ts, equity, cash, buying_power),
        )


def recent_ticks(limit: int = 100, symbol: str | None = None) -> list[dict]:
    with connect() as conn:
        if symbol:
            rows = conn.execute(
                "SELECT * FROM ticks WHERE symbol = ? ORDER BY id DESC LIMIT ?", (symbol, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ticks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def latest_tick_per_symbol(symbols: list[str]) -> dict[str, dict]:
    out = {}
    with connect() as conn:
        for sym in symbols:
            row = conn.execute(
                "SELECT * FROM ticks WHERE symbol = ? ORDER BY id DESC LIMIT 1", (sym,)
            ).fetchone()
            if row:
                out[sym] = dict(row)
    return out


def equity_curve(limit: int = 500) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
