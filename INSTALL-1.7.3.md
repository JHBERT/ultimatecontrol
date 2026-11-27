# UltimateControl 1.7.3 – richtige Demo, richtiger Ordner

## 1. Falsche Demo nach einem Klick

Zwei Klicks kurz hintereinander – oder ein Klick, während die vorige Seite noch
lädt – und die Karte zeigte die zuerst geklickte Demo. Ursache: `_csdbOpenRelease`
schrieb die Antwort jedes Aufrufs, auch wenn inzwischen ein neuerer lief. Jetzt
zählt jede Anfrage mit (`_csdbSeq`), und nur die jüngste darf die Karte
aktualisieren.

## 2. Ordner nach Typ, Gruppe und Jahr

Ein Release landet jetzt unter

```
csdb/<Typ>/<Anfangsbuchstabe der Gruppe>/<Gruppe>/<Name> [<Jahr>]
```

Beispiel <https://csdb.dk/release/?id=82>:

```
sids/csdb/C64 Demo/M/Megastyle/Piece of Cake [1989]/
  Piece of Cake 1 [Side A].d64
  Piece of Cake 1 [Side B].d64
  piece_of_cake_1.zip
```

- Typ, Gruppe und Jahr kommen aus den CSDb-Daten des Releases.
- Fehlt Typ oder Gruppe, steht dort `Unbekannt`; fehlt das Jahr, bleibt die
  eckige Klammer weg.
- Zeichen, die ein Ordner nicht tragen darf (`/ \ : * ? " < > |`), werden zu
  Leerzeichen.

## Tests

164 grün (5 neue in `tests/test_csdb.py`), Kartenprüfungen „Karte lädt: ok",
„CSDb-Klicks: ok", „CSDb-Ablauf: ok", „Kein Sprung: ok".

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.7.3.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
