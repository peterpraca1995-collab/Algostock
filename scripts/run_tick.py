"""Vstupný bod pre GitHub Actions: jedno hodinové vyhodnotenie + export dashboardu.

Ak je trh zatvorený (víkend, sviatok, mimo hodín), nič neobchoduje a iba to
zaloguje — bezpečné spúšťať aj mimo obchodných hodín.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # aby `src` išlo importnúť bez ohľadu na cwd

from src import alpaca_client, db, engine, export_status


def main() -> None:
    db.init_db()

    try:
        clock = alpaca_client.get_clock()
    except Exception as e:
        print(f"Nepodarilo sa zistiť stav trhu: {e}", file=sys.stderr)
        clock = {"is_open": False}

    if not clock.get("is_open"):
        print(f"Trh je zatvorený (next_open={clock.get('next_open')}), preskakujem obchodovanie.")
        results = []
    else:
        results = engine.run_all()
        print(json.dumps(results, indent=2, default=str, ensure_ascii=False))

    out_path = export_status.write_status_json()
    print(f"dashboard export: {out_path}")


if __name__ == "__main__":
    main()
