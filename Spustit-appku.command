#!/bin/bash
# Dvojklikom spustí Investičnú appku a otvorí ju v prehliadači.
cd "$(dirname "$0")" || exit 1

if curl -s -o /dev/null -m 1 http://127.0.0.1:8765/; then
    echo "Appka už beží, otváram prehliadač…"
    open http://127.0.0.1:8765
else
    source .venv/bin/activate
    python -m src.server &
    SERVER_PID=$!
    sleep 1.5
    open http://127.0.0.1:8765
    wait $SERVER_PID
fi
