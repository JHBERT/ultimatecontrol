# UltimateControl 1.4.0 – Autostart für Disketten

Ja, Autostart geht – nur nicht mit einem eigenen Kommando für Laufwerke,
sondern über den PRG-Runner:

1. Das Image wird in Laufwerk A eingelegt (`POST /v1/drives/a:mount`, Image als
   Rumpf, `readonly`).
2. Aus dem Image wird das **erste PRG** gelesen (neues Modul `d64.py`: Track 18
   Verzeichnis, Sektorkette, PETSCII-Name).
3. Dieses PRG geht an `POST /v1/runners:run_prg` – laut Gideons Doku „loads the
   program into memory using DMA. Then it automatically runs the program.“

Die Diskette bleibt eingelegt, Nachladen funktioniert also. Der
Websocket-Befehl `ultimatecontrol/image_play` hat dafür den Schalter
`autostart` (die Karte setzt ihn). Mit `autostart: false` wird nur eingelegt.

## Was weiterhin nicht geht

- **PRG mit Nachladen von Diskette:** der Runner lädt nur das eine Programm.
  Der Rest der Diskette ist zwar da, aber das PRG muss selbst nachladen können.
- **`/v1/machine:input`** (Tastatureingaben) ist U64-only; auf dem Ultimate II+
  antwortet es mit HTTP 501.
- **G64/G71** werden nicht automatisch gestartet: dort ist der Inhalt GCR-kodiert,
  ein PRG lässt sich nicht ohne Weiteres herausziehen. Sie werden nur eingelegt.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.4.0.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
