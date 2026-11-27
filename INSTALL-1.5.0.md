# UltimateControl 1.5.0 – Autostart per Tastatur

Zwei Wege, eine Diskette zu starten, jetzt wählbar:

| `autostart_method` | Was passiert |
|---|---|
| `prg` (Standard) | Image einlegen, erstes PRG herausziehen, per `run_prg` laden und starten |
| `keyboard` | Image einlegen, Reset, dann `LOAD"*",8,1` + RETURN in den Tastaturpuffer tippen |

Der Tastaturweg nutzt `PUT /v1/machine:writemem`: die Zeichen gehen nach
`$0277`, die Länge nach `$00C6`. Der Puffer fasst 10 Zeichen, längere Befehle
werden in Stücken getippt. Mit `load_command` lässt sich der Befehl überschreiben
(z. B. `LOAD"DEMO",8,1`).

In der Karte: `autostart_method: keyboard` in der Konfiguration setzen, sonst
bleibt es beim PRG-Weg. Der Websocket-Befehl `ultimatecontrol/image_play` hat
dafür `autostart_method` und `load_command`.

## Grenzen

- Der Tastaturweg setzt voraus, dass der C64 am READY-Prompt steht – deshalb
  der Reset vorher und 2 Sekunden Wartezeit.
- `/v1/machine:input` (echte Tastendrücke) bleibt U64-only; hier wird der
  KERNAL-Puffer benutzt, der auf beiden Geräten existiert.
- Am echten Gerät ungetestet.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.5.0.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
