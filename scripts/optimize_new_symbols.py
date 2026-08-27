#!/usr/bin/env python3
"""Jednorazovo naladí nové symboly (rovnaký walk-forward postup ako optimize.py)
a pridá ich do config/settings.json (tickers + overrides), bez toho aby sa
prepočítavali už existujúce, overené overrides pre pôvodných 8 symbolov."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.optimize import optimize_symbol  # noqa: E402

NEW_SYMBOLS = ["GOOGL", "AMZN", "META", "AVGO", "NFLX", "PLTR", "JPM"]


def main() -> None:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365)
    split = start + timedelta(days=245)

    settings_path = Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    results = {}
    for symbol in NEW_SYMBOLS:
        print(f"{symbol}…", end=" ", flush=True)
        r = optimize_symbol(symbol, start, split, end)
        results[symbol] = r
        if r.get("error"):
            print(r["error"])
            continue
        bt, bte = r["baseline_train"]["total_pnl"], r["baseline_test"]["total_pnl"]
        if r["chosen"] is None:
            print(f"bez zmeny; default train {bt:+.0f} $ / test {bte:+.0f} $")
        else:
            tt, tte = r["train"]["total_pnl"], r["test"]["total_pnl"]
            print(f"vylepšené {r['combo']}")
            print(f"        default:  train {bt:+8.2f} $   test {bte:+8.2f} $")
            print(f"        nájdené:  train {tt:+8.2f} $   test {tte:+8.2f} $")
            settings.setdefault("overrides", {})[symbol] = r["combo"]

        if symbol not in settings["tickers"]:
            settings["tickers"].append(symbol)

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")

    out_path = Path(__file__).resolve().parent.parent / "data" / f"optimize_new_symbols_{start}_{end}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    n_changed = sum(1 for r in results.values() if r.get("chosen"))
    print(f"\n{n_changed}/{len(NEW_SYMBOLS)} nových symbolov dostalo vlastné prahy.")
    print(f"Detaily: {out_path}")


if __name__ == "__main__":
    main()
