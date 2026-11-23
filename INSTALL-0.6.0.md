# UltimateControl 0.6.0 – Songlängen und HVSC-Version

## Was neu ist

**Songlängen aus der HVSC.** Bisher hat jede Melodie 5 Minuten gespielt. Jetzt
lädt die Karte die Datei `Songlengths.md5` (5 MB, 61 157 SIDs) direkt vom
HVSC-Mirror – danach spielt jeder Tune so lange, wie die HVSC es vorgibt, und
die Karte zeigt die Länge an. Die Zuordnung läuft über die MD5 der Datei, greift
also für die **Bibliothek und die Favoriten** gleichermaßen.

**HVSC-Version und Update-Hinweis.** Am Kartenende steht jetzt z. B.

```
Songlängen: 61157 SIDs · HVSC 85 · aktuell
```

Steht eine neuere Version bereit, wird daraus „Update 85 verfügbar“. Der Knopf
**Prüfen** fragt den Mirror erneut; der zweite Knopf lädt die Songlängen.

**Favoriten-Ansicht.** Dort gibt es keinen ★-Favorit-Knopf mehr, sondern
**✕ Entfernen**.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 0.6.0 (erscheint als „0.6.0“,
   nicht als Commit-Hash).
2. Home Assistant neu starten.
3. Browser **hart neu laden** (Strg+F5), damit die Karte die neue Version zieht.

## Erster Lauf

1. Karte auf ein Dashboard legen (oder die vorhandene Karte neu laden).
2. Unten steht „Keine Songlängen – jede Melodie spielt 5 Minuten“ und der Knopf
   **Songlängen laden**.
3. Knopf drücken: der Download dauert je nach Leitung einige Sekunden bis
   Minuten (5 MB). Danach steht dort „Songlängen: 61157 SIDs“.
4. Einen Tune abspielen – die Länge wird jetzt aus der HVSC genommen.

Die Datei liegt danach unter
`/config/ultimatecontrol/Songlengths.md5`. Ein erneuter Download überschreibt
sie. Bricht die Verbindung ab, bleibt keine halbe Datei zurück (es wird erst in
`Songlengths.md5.part` geschrieben und dann umbenannt).

## Was noch nicht drin ist

Das **HVSC-Vollpaket** (81 MB, 61 157 SIDs) und das **Anwenden von Updates**
kommen in 0.6.1. Beides hängt am selben Punkt: HVSC packt mit dem BCJ2-Filter,
den Python nicht entpacken kann – dafür entsteht ein eigener Entpacker. Der
Hinweis und die Kette der fehlenden Updates (z. B. 84 → 85) werden aber schon
jetzt korrekt angezeigt.

## Offline

Ohne Internetzugang bleibt die Statuszeile leer bzw. zeigt die zuletzt bekannte
Version; die Songlängen funktionieren weiter, weil sie lokal gespeichert sind.

## Bekannte Kleinigkeit

Sind Tunes kürzer als eine Sekunde angegeben (z. B. 5,202 s), wird für die
Anzeige auf ganze Sekunden abgerundet.
