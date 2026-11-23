# UltimateControl 0.7.0 – ganze Ordner abspielen

## Was neu ist

**„▶ Ordner abspielen“.** Über der Dateiliste steht jetzt ein Knopf, der alle
SIDs des aktuellen Ordners – Unterordner inklusive – nacheinander spielt. Der
Timer dafür läuft **in Home Assistant**: Ist ein Tune zu Ende, schickt die
Integration den nächsten an den C64 und startet den Timer neu.

- Die Länge kommt aus der HVSC-Datenbank (`Songlengths.md5`), also z. B.
  `1:30` → nach 1:30 kommt der nächste Tune.
- Kennt die Datenbank einen Tune nicht, wird nach 5 Minuten weitergeschaltet
  (das ist auch die Voreinstellung des C64).
- Nach dem letzten Tune endet die Warteschlange, sie läuft nicht in Schleife.
- **🔀** startet denselben Ordner in zufälliger Reihenfolge.

**Die Warteschlangen-Leiste** unter der Liste zeigt, was läuft:

```
▶ Commando.sid · 3/48 · noch 2:41 · dann Monty_on_the_Run.sid    ⏮ ⏭ ⏸ ⏹
```

- **⏮ / ⏭** vorheriger / nächster Tune (der Timer wird dabei neu gestartet),
- **⏸ / ▶** Pause und Weiter (Pause hält den C64 an),
- **⏹** beendet die Warteschlange und setzt den C64 zurück.

Wird ein Tune von Hand gestartet (Tune-Nummer antippen), bleibt die
Warteschlange an ihrer Stelle stehen – sie läuft nicht weiter.

## Technisch

Neu ist `queue_player.py`: eine Warteschlange je Gerät mit einem Timer-Task.
Jeder Tune bekommt seine eigene Wartezeit (`Länge + 0,5 s`), der Task wird für
jeden Tune neu erzeugt – ein alter Timer kann also nie doppelt weiterschalten.
Neue Websocket-Befehle: `queue_play_folder`, `queue_action`, `queue_status`.
Der Timer läuft als Home-Assistant-Hintergrund-Task und wird beim Entladen des
Eintrags beendet. 26 neue Tests, insgesamt **90 grün**.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 0.7.0.
2. Home Assistant neu starten.
3. Browser **hart neu laden** (Strg+F5).

## Ausprobieren

In einen Ordner mit mehreren Tunes wechseln (z. B. einen Komponisten-Ordner)
und **▶ Ordner abspielen** drücken. Die Leiste unten zeigt den laufenden Tune
und die Restzeit; nach dessen Ende beginnt der nächste von selbst.
