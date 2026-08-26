#!/usr/bin/env python3
"""Per-symbolové ladenie prahov s walk-forward overením.

    python3 scripts/optimize.py                 # posledný rok, 8/4 mesiace train/test

Prečo per-symbol: 8 sledovaných tickerov majú úplne inú volatilitu a
charakter (napr. SLV vs. TSLA) — jedny globálne prahy im nesedia rovnako.

Prečo walk-forward, nie len "nájdi najlepšie na celom období": keby sa
prahy vyladili na presne tie isté dáta, na ktorých sa aj vyhlási úspech,
je to len prispôsobenie sa šumu (overfitting) — vyzeralo by to skvele
spätne a naživo by to sklamalo. Namiesto toho:

  1. Rozdeliť rok na TRAIN (prvých ~8 mesiacov) a TEST (posledné ~4).
  2. Na TRAIN vyskúšať mriežku kombinácií prahov, vybrať najlepšiu
     (s minimálnym počtom obchodov, nech to nie je náhoda pár kusov).
  3. Tú istú kombináciu overiť na TEST — dátach, ktoré pri hľadaní
     vôbec nevidela.
  4. Override sa do settings.json zapíše LEN keď na TEST naozaj
     prekonala pôvodné (globálne) nastavenie. Inak sa nechá default —
     "nenašlo sa nič spoľahlivo lepšie" je platný, poctivý výsledok.
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.backtest import fetch_indicators, simulate, summarize  # noqa: E402

# mriežka — 3^5 = 243 kombinácií na symbol, nad predpočítanými indikátormi
# to zabehne v priebehu sekúnd (žiadne ďalšie sťahovanie)
GRID = {
    "signal_buy_threshold": [3, 4, 5],
    "signal_sell_threshold": [-2, -3, -4],
    "adx_min_trend": [15, 20, 25],
    "atr_stop_mult": [1.5, 2.0, 2.5],
    "atr_target_mult": [2.0, 3.0, 4.0],
}
MIN_TRAIN_TRADES = 20  # menej než toľko = príliš málo na to, aby to niečo znamenalo


def _grid_combos():
    keys = list(GRID.keys())
    for values in itertools.product(*GRID.values()):
        yield dict(zip(keys, values))


def optimize_symbol(symbol: str, start: date, split: date, end: date) -> dict:
    base = config.effective_settings(symbol)
    data = fetch_indicators(symbol, start, end, base)
    if not data["bars"]:
        return {"symbol": symbol, "error": "žiadne dáta"}

    baseline_train = summarize(simulate(data, start, split, base))
    baseline_test = summarize(simulate(data, split + timedelta(days=1), end, base))

    best = None  # (train_summary, combo)
    for combo in _grid_combos():
        candidate = {**base, **combo}
        train_trades = simulate(data, start, split, candidate)
        if len(train_trades) < MIN_TRAIN_TRADES:
            continue
        train_summary = summarize(train_trades)
        if best is None or train_summary["total_pnl"] > best[0]["total_pnl"]:
            best = (train_summary, combo)

    if best is None:
        return {
            "symbol": symbol, "chosen": None,
            "baseline_train": baseline_train, "baseline_test": baseline_test,
            "note": f"žiadna kombinácia nemala aspoň {MIN_TRAIN_TRADES} obchodov na train — ostáva default",
        }

    train_summary, combo = best
    candidate = {**base, **combo}
    test_trades = simulate(data, split + timedelta(days=1), end, candidate)
    test_summary = summarize(test_trades)

    improved = (test_summary["total_pnl"] or 0) > (baseline_test["total_pnl"] or 0)
    return {
        "symbol": symbol, "combo": combo,
        "train": train_summary, "test": test_summary,
        "baseline_train": baseline_train, "baseline_test": baseline_test,
        "improved_on_test": improved,
        "chosen": combo if improved else None,
    }


def main() -> None:
    end = date.today() - timedelta(days=1)          # včerajšok — dnešok ešte nie je uzavretý deň
    start = end - timedelta(days=365)
    split = start + timedelta(days=245)              # ~8 mesiacov train, ~4 mesiace test

    print(f"Ladenie {start} … {split} (train) / {split + timedelta(days=1)} … {end} (test)\n")

    results = {}
    overrides = dict(config.SETTINGS.get("overrides", {}))
    for symbol in config.SETTINGS["tickers"]:
        print(f"{symbol}…", end=" ", flush=True)
        r = optimize_symbol(symbol, start, split, end)
        results[symbol] = r
        if r.get("error"):
            print(r["error"])
            continue

        bt, bte = r["baseline_train"]["total_pnl"], r["baseline_test"]["total_pnl"]
        if r["chosen"] is None:
            note = r.get("note", "test neprekonal default")
            print(f"bez zmeny ({note}); default train {bt:+.0f} $ / test {bte:+.0f} $")
        else:
            tt, tte = r["train"]["total_pnl"], r["test"]["total_pnl"]
            print(f"vylepšené {r['combo']}")
            print(f"        default:    train {bt:+8.2f} $   test {bte:+8.2f} $")
            print(f"        nájdené:    train {tt:+8.2f} $   test {tte:+8.2f} $  <- naozaj lepšie na dátach, čo nevidelo")
            overrides[symbol] = r["combo"]

    settings_path = Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    settings["overrides"] = overrides
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")

    out_path = Path(__file__).resolve().parent.parent / "data" / f"optimize_{start}_{end}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    n_changed = sum(1 for r in results.values() if r.get("chosen"))
    print(f"\n{n_changed}/{len(results)} symbolov dostalo vlastné prahy (uložené do config/settings.json).")
    print(f"Detaily: {out_path}")


if __name__ == "__main__":
    main()
