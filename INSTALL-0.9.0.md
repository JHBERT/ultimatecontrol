# UltimateControl 0.9.0 – laufender Tune, Haupttune, 5-Minuten-Regel

## 1) Nach dem Öffnen der Seite sieht man, was läuft

Die Warteschlange merkt sich jetzt, **wann** der laufende Tune endet
(Zeitstempel, nicht nur eine Restzeit). Damit gilt:

- Beim Aufrufen der Seite fragt die Karte den Stand ab und zeigt sofort
  **den laufenden Tune**, die Position (`3/48`), die **Restzeit** und den
  nächsten Tune.
- Die Restzeit läuft **sekündlich** mit, ohne die Karte neu zu bauen.
- Die Integration meldet jeden Wechsel (`ultimatecontrol_queue_changed`); die
  Karte hört darauf und zieht nach, auch wenn sie zwischendurch geschlossen war.
- Eine geöffnete Tune-Liste markiert den laufenden Tune **grün**.

## 2) SIDs ohne Titelinformation → 5 Minuten, dann weiter

Die Länge wird über die MD5 der Datei gesucht. Ist eine Datei unbekannt (z. B.
eine Kopie aus einer älteren HVSC-Version, deren MD5 nicht mehr passt), gibt es
keine Länge – dann gilt **300 Sekunden**, und die Warteschlange schaltet danach
normal weiter. Das war schon so eingebaut, ist jetzt geprüft und getestet:
`FALLBACK_LENGTH = 300`.

## 3) Haupttune: blau vorbelegt, grün beim Abspielen

Ein SID nennt in seinem Kopf, welcher Sub-Tune der Haupttune ist (Feld
„start song“, Offset 16; `0` heißt Tune 1). Das liest die Integration jetzt:

- In der Tune-Auswahl ist der **Haupttune blau** und mit ★ markiert.
- Der **laufende Tune ist grün** und mit ▶ markiert.
- **Ordner und Playlists spielen den Haupttune**, nicht mehr fest Tune 1.
  Wer in der Tune-Liste einen bestimmten Tune antippt, bekommt weiter genau
  diesen – und eine Playlist speichert die Tune-Nummer, die man hinzugefügt hat.

Ein SID mit nur einem Tune verhält sich wie bisher.

## Neustart von Home Assistant

Der Timer lebt in Home Assistant. Ein HA-Neustart mitten im Ordner lässt den C64
weiterspielen, aber niemand würde den nächsten Tune schicken. Dafür gibt es
jetzt den Dienst **`ultimatecontrol.restore_queue`** – z. B. in einer Automation
beim Start:

```yaml
alias: Ultimate Warteschlange wieder aufnehmen
trigger:
  - platform: homeassistant
    event: start
action:
  - service: ultimatecontrol.restore_queue
    data:
      entry_id: <ID des Geräts>
      folder: MUSICIANS/H/Hubbard_Rob
```

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 0.9.0.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).

19 neue Tests, insgesamt **124 grün**.
