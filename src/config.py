"""Načítanie konfigurácie a API kľúčov.

Kľúče sa hľadajú v tomto poradí:
1. Premenné prostredia ALPACA_KEY_ID / ALPACA_SECRET_KEY — používa sa v GitHub
   Actions (hodnoty prídu z GitHub Secrets, nikdy nie sú v kóde ani v repe).
2. Lokálne súbory v ../kluce/ — pohodlné pre beh appky na vlastnom Macu.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # .../investicna-app
KLUCE_DIR = ROOT.parent / "kluce"                        # .../Claude/kluce
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "trading.db"

with open(ROOT / "config" / "settings.json", "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)


def effective_settings(symbol: str) -> dict:
    """SETTINGS s prípadným prekrytím pre konkrétny symbol.

    `config/settings.json` môže mať kľúč `overrides`: {"SLV": {"adx_min_trend": 25, ...}, ...}
    — každý nástroj má inú volatilitu/charakter, jedny globálne prahy im
    nemusia sedieť rovnako (viď scripts/optimize.py, ktorý tieto hodnoty
    vie nájsť a walk-forward overiť, nie len naslepo odhadnúť)."""
    merged = dict(SETTINGS)
    merged.update(SETTINGS.get("overrides", {}).get(symbol, {}))
    return merged


def _read_key(env_var: str, filename: str) -> str:
    env_val = os.environ.get(env_var)
    if env_val:
        return env_val.strip()
    path = KLUCE_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Chýba kľúč: nie je nastavená premenná {env_var} ani súbor {path}. "
            f"Vytvor paper-trading API kľúče na app.alpaca.markets — lokálne ich ulož "
            f"do {KLUCE_DIR}, v GitHub Actions ich nastav ako repository secrets."
        )
    return path.read_text(encoding="utf-8").strip()


ALPACA_KEY_ID = _read_key("ALPACA_KEY_ID", "alpaca_paper_key_id.key")
ALPACA_SECRET_KEY = _read_key("ALPACA_SECRET_KEY", "alpaca_paper_secret.key")

# Paper trading base URLs. Prepnutie na živý účet = zmena týchto dvoch URL
# a nahradenie kľúčov v kluce/ za live kľúče — nič iné v appke sa meniť nemusí.
ALPACA_TRADING_BASE = "https://paper-api.alpaca.markets"
ALPACA_DATA_BASE = "https://data.alpaca.markets"

DATA_DIR.mkdir(parents=True, exist_ok=True)
