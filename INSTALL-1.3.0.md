# UltimateControl 1.3.0 – Disketten und Programme aus der Bibliothek

Neu: Die Karte zeigt neben SIDs auch **D64/D71/D81/G64/G71**, **PRG** und **CRT**.
Ein Klick lädt die Datei hoch und startet sie – ohne FTP-Kopie vorher.

- Diskette: `POST /v1/drives/a:mount` mit dem Image als Rumpf, Modus `readonly`.
- PRG: `POST /v1/runners:run_prg` mit der Datei als Anhang.
- CRT: `POST /v1/runners:run_crt` mit der Datei als Anhang.

Nach dem Einlegen bleibt das Laufwerk bestückt; gestartet wird wie am C64
üblich von Hand (`LOAD"*",8,1`, dann `RUN`). Ein Automatikstart ist nicht
eingebaut, weil dafür Tastatureingaben nötig wären (siehe unten).

## Was die API laut Gideons Dokumentation kann

Geprüft gegen <https://1541u-documentation.readthedocs.io/en/latest/api/api_calls.html>:

- `POST /v1/drives/<drive>:mount` nimmt das Image als Anhang, `type` und `mode`
  optional – genau so setzen wir es ein.
- `POST /v1/runners:run_prg` und `POST /v1/runners:run_crt` nehmen die Datei
  als Anhang.
- **Kein** Startbefehl für den Inhalt einer Diskette: es gibt kein
  „autostart“-Kommando. Möglich wären `PUT /v1/machine:writemem` (Tastaturpuffer
  $0277) oder `POST /v1/machine:input` – letzteres ist laut Dokumentation
  **U64-only** und antwortet auf dem Ultimate II+ mit HTTP 501.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.3.0.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
