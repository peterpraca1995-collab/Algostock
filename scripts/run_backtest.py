#!/usr/bin/env python3
"""Backtest stratégie na historických sviečkach.

    python3 scripts/run_backtest.py                       # posledné 3 mesiace
    python3 scripts/run_backtest.py 2026-07-01 2026-08-26  # vlastný rozsah

Simuluje deň po dni presne to, čo appka robí naživo — ráno by rozhodla,
poobede/večer sa to vyhodnotí (pozícia sa zavrie sama, viď README časť
o `flatten_before_close_minutes`). Výsledok sa vypíše aj uloží do
`data/backtest_<od>_<do>.json`.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest import run_backtest  # noqa: E402


def main() -> None:
    if len(sys.argv) >= 3:
        start = date.fromisoformat(sys.argv[1])
        end = date.fromisoformat(sys.argv[2])
    else:
        # včerajšok, nie dnešok — dnešný deň ešte nemusí byť ukončený a
        # posledná stiahnutá sviečka by sa nesprávne vyhodnotila ako
        # "koniec dňa", hoci trh ešte reálne nezavrel
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=90)

    print(f"Backtest {start} … {end} (môže trvať pár minút, sťahujú sa historické sviečky)\n")
    result = run_backtest(start, end)
    s = result["summary"]

    print("=" * 60)
    print(f"  {s['trades']} obchodov · výhier {s['wins']} · prehier {s['losses']}"
          + (f" · úspešnosť {s['win_rate_pct']} %" if s["win_rate_pct"] is not None else ""))
    print(f"  Celkový P&L: {s['total_pnl']:+.2f} $"
          + (f" · priemer na obchod {s['avg_pnl_per_trade']:+.2f} $" if s["avg_pnl_per_trade"] is not None else ""))
    if s["avg_win"] is not None:
        print(f"  Priemerná výhra {s['avg_win']:+.2f} $ · priemerná prehra {s['avg_loss']:+.2f} $")
    if s["best_trade"]:
        bt = s["best_trade"]
        print(f"  Najlepší: {bt['symbol']} {bt['entry_t'][:16]} -> {bt['exit_t'][:16]}  {bt['pnl']:+.2f} $ ({bt['reason']})")
    if s["worst_trade"]:
        wt = s["worst_trade"]
        print(f"  Najhorší: {wt['symbol']} {wt['entry_t'][:16]} -> {wt['exit_t'][:16]}  {wt['pnl']:+.2f} $ ({wt['reason']})")
    print("=" * 60)

    print(f"\nPo symboloch:")
    for symbol, r in result["per_symbol"].items():
        t = r["trades"]
        pnl = sum(x["pnl"] for x in t)
        print(f"  {symbol:6} {len(t):3} obchodov   {pnl:+9.2f} $   ({r['bars_used']} sviečok stiahnutých)")

    print(f"\nObchody podľa dátumu:")
    for t in result["trades"]:
        print(f"  {t['entry_t'][:16]}  {t['symbol']:6} kúpa {t['entry_price']:8.2f} -> "
              f"predaj {t['exit_price']:8.2f}  ({t['exit_t'][11:16]}, {t['reason']:11})  {t['pnl']:+8.2f} $")

    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"backtest_{start}_{end}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nUložené do {out_path}")


if __name__ == "__main__":
    main()
