"""Vyexportuje aktuálny stav do JSON pre statický dashboard (GitHub Pages).

Na rozdiel od src/server.py (živé Flask API) toto beží raz na konci každého
GitHub Actions behu a zapíše docs/data/status.json — statickú stránku potom
netreba nič serverovať, len otvoriť v prehliadači.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import alpaca_client, db
from .config import ROOT, SETTINGS

DOCS_DATA_DIR = ROOT / "docs" / "data"


def write_status_json() -> Path:
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        account = alpaca_client.get_account()
    except Exception as e:
        account = {"error": str(e)}

    try:
        positions = alpaca_client.get_positions()
    except Exception:
        positions = []

    latest = db.latest_tick_per_symbol(SETTINGS["tickers"])
    history = db.recent_ticks(limit=150)
    equity = db.equity_curve(limit=1000)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": SETTINGS["tickers"],
        "account": account,
        "positions": positions,
        "latest_ticks": latest,
        "history": history,
        "equity": equity,
    }

    out_path = DOCS_DATA_DIR / "status.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    path = write_status_json()
    print(f"zapísané: {path}")
