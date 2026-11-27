# UltimateControl 1.7.6 – Reiter heißt DATA

Der erste Reiter der Karte hieß **HVSC**, obwohl dort seit 1.7.5 der Ordner
`config/ultimatecontrol/DATA` mit SIDs, Disketten, Programmen und den
CSDb-Releases liegt. Er heißt jetzt **DATA**; ein Tooltip nennt den Pfad.

Technisch unverändert: der Reiter schaltet weiterhin `data-src="library"`, also
die Bibliothek. Nur die Beschriftung ist neu.

## Tests

172 grün. Kartenprüfungen: „Karte lädt: ok", „Kein Sprung: ok", „Aufklappen
ohne Sprung: ok", „CSDb-Klicks: ok", „CSDb-Ablauf: ok".

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.7.6.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
