"""Web dashboard + REST API. Spusti cez `python -m src.server` alebo Spustit-appku.command."""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from . import alpaca_client, db, engine, scheduler
from .config import SETTINGS

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = Flask(__name__, static_folder=None)


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/app.js")
def app_js():
    return send_from_directory(WEB_DIR, "app.js")


@app.get("/style.css")
def style_css():
    return send_from_directory(WEB_DIR, "style.css")


@app.get("/api/status")
def api_status():
    try:
        account = alpaca_client.get_account()
    except Exception as e:
        account = {"error": str(e)}
    try:
        positions = alpaca_client.get_positions()
    except Exception as e:
        positions = []
    latest = db.latest_tick_per_symbol(SETTINGS["tickers"])
    return jsonify({
        "account": account,
        "positions": positions,
        "latest_ticks": latest,
        "schedule": scheduler.get_status(),
        "tickers": SETTINGS["tickers"],
    })


@app.get("/api/history")
def api_history():
    from flask import request
    symbol = request.args.get("symbol")
    limit = int(request.args.get("limit", 200))
    return jsonify(db.recent_ticks(limit=limit, symbol=symbol))


@app.get("/api/equity")
def api_equity():
    return jsonify(db.equity_curve())


@app.post("/api/run-now")
def api_run_now():
    results = engine.run_all()
    return jsonify(results)


def main() -> None:
    db.init_db()
    # spusti scheduler len raz (nie v podprocese Flask reloadera)
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        scheduler.start_background()
    app.run(host="127.0.0.1", port=8765, debug=False)


if __name__ == "__main__":
    main()
