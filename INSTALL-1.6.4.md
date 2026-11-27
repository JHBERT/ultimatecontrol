# UltimateControl 1.6.4 – kein Sprung mehr bei mehreren Tunes

Beim Klick auf einen Tune eines SID mit mehreren Untertunes sprang die Liste
noch nach oben. Ursache: nach dem Start wurde die aufgeklappte Tune-Liste neu
geholt und die ganze Karte neu aufgebaut.

Jetzt wird auch dort nur markiert, was sich ändert:

- Der laufende Tune wird **grün** und mit **▶** markiert, der Haupttune bleibt
  **blau** mit **★** – direkt in der bestehenden Liste, ohne Neuaufbau.
- Die Songlängen werden nicht erneut geladen; sie stehen schon in der
  aufgeklappten Liste.
- Die Scrollposition bleibt dadurch exakt stehen, bei einzelnen Tunes und bei
  SIDs mit Untertunes.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.6.4.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
