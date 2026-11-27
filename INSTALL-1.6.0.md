# UltimateControl 1.6.0 – Diskettenwechsel für mehrteilige Demos

Drei Wege, jetzt auch der für Demo-Serien:

| `autostart_method` | Was passiert |
|---|---|
| `prg` (Standard) | einlegen + erstes PRG per `run_prg` laden und starten |
| `keyboard` | einlegen + Reset + `LOAD"*",8,1` in den Tastaturpuffer |
| `none` | **nur einlegen** – für den nächsten Part eines laufenden Demos |

`none` macht bewusst nichts weiter: kein Reset, kein Ladebefehl. Das laufende
Demo merkt den Diskettenwechsel selbst und lädt nach. Damit lässt sich eine
Demo-Serie durchklicken, ohne den C64 anzufassen.

In der Karte: `autostart_method: none` in der Konfiguration. Per Websocket:
`ultimatecontrol/image_play` mit `autostart: true` und `autostart_method: "none"`
(oder `autostart: false`, das ist dasselbe).

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.6.0.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
