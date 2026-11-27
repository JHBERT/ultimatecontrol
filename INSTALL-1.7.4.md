# UltimateControl 1.7.4 – richtige Demo, kein Sprung mehr

## 1. CSDb öffnete die falsche Demo

**Ursache gefunden:** Der Websocket-Client von Home Assistant setzt vor dem
Senden `message.id` auf die laufende Befehlsnummer:

```js
message.id = commandId;
this.socket.send(JSON.stringify(message));
```

Die Karte schickte die Release-ID ebenfalls als `id` – sie wurde also
überschrieben, und der Handler las die **Befehlsnummer** statt der Demo. Bei
`Next Level` (ID 232976) kam so `id=2` an, und die Karte zeigte irgendein
Release mit der ID 2.

Jetzt heißt der Schlüssel `release`:

```js
this._ws("csdb_release", { release: id })
```

`csdb_release` und `csdb_install` lesen `msg["release"]`; ein Test in
`tests/test_ws_schemas.py` verbietet künftig jeden Befehl mit eigenem
Schlüssel `id`.

## 2. Liste sprang bei mehrteiligen SIDs nach oben

Das Auf- und Zuklappen der Tune-Auswahl baute die ganze Karte neu
(`innerHTML`), und damit stand die Liste wieder auf 0. Jetzt werden die
Tune-Knöpfe mit `insertAdjacentHTML` hinter die Zeile gehängt und mit `remove()`
entfernt; das Symbol wechselt zwischen ♪ und ▾. Kein Neuaufbau, kein Sprung.

## Tests

169 grün, davon neu: `tests/test_csdb_websocket.py` (3, fährt den Handler mit
`id` = Befehlsnummer und `release` = Demo), 2 in `tests/test_ws_schemas.py`.
Kartenprüfungen: „Karte lädt: ok", „Kein Sprung: ok", „Aufklappen ohne Sprung:
ok", „CSDb-Klicks: ok", „CSDb-Ablauf: ok".

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.7.4.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
