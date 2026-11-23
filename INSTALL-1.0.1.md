# UltimateControl 1.0.1 – Lizenz und Danksagung

Keine Funktionsänderung, nur Formalia für die Veröffentlichung:

- **`LICENSE`** neu im Repository: die vollständige **GNU General Public
  License v3.0** mit Copyright-Zeile.
- **`THIRD-PARTY-NOTICES.md`** neu: was von anderen stammt und was nicht –
  Laufzeit-Abhängigkeiten (Home Assistant, aiohttp, voluptuous), nachgebaute
  Schnittstellen (Ultimate REST API, `.ssl`-Längenliste, HVSC
  `Songlengths.md5`), Daten Dritter (HVSC, Marken) und die Projekte, die beim
  Verstehen geholfen haben (u64deck MIT, ultimate64 Apache-2.0,
  c64-pi-jukebox GPL-3.0).
- **README** hat einen Abschnitt „Lizenz“.

Im Repository liegt **kein fremder Quelltext** und keine Fremdbibliothek – die
Integration nutzt nur, was Home Assistant ohnehin mitbringt.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.0.1.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
