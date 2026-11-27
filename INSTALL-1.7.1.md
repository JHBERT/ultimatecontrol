# UltimateControl 1.7.1 – CSDb-Tab lädt wieder

Fehler in 1.7.0: Der CSDb-Tab zeigte „Nichts geladen." und darunter

    not a valid option at 'entry_id': '01KPBXTJKSR8ER5FZKMPGWYKXB'

Ursache: Die Karte schickt in **jeder** Websocket-Nachricht eine `entry_id`
mit, Home Assistant prüft jede Nachricht gegen das Schema ihres Befehls und
lehnt unbekannte Schlüssel ab. Die drei CSDb-Befehle `csdb_front`, `csdb_list`
und `csdb_release` hatten `entry_id` nicht im Schema – sie brauchen es auch
nicht, aber sie müssen es annehmen. Jetzt steht es dort als optionaler
Schlüssel, und ein Test (`tests/test_ws_schemas.py`) prüft, dass **jeder**
Befehl der Integration `entry_id` akzeptiert.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.7.1.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
