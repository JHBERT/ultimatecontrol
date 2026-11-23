# UltimateControl 1.0.0 – die Ansicht bleibt beim Tune stehen

## Was neu ist

Ein Klick auf einen Tune baut die Liste neu auf – dabei setzt der Browser die
Scrollposition einer Liste auf 0, die Ansicht sprang also nach oben. Das ist
jetzt behoben:

- Die Karte merkt sich die Position der Liste **vor** jedem Neuaufbau und stellt
  sie danach wieder her.
- Der **laufende Tune** ist zusätzlich grün hinterlegt. Steht er außerhalb des
  sichtbaren Bereichs, holt die Karte ihn ins Bild – sonst bleibt die Ansicht
  genau da, wo du geklickt hast.
- Gilt für **HVSC-Ordner, Favoriten, Playlists und den Import-Dialog**.

## Warum 1.0

Damit ist der Funktionsumfang rund:

- SID-Bibliothek durchsuchen, Tune (mit Haupttune-Vorwahl) abspielen,
- Favoriten und Playlists,
- ganze Ordner und Playlists als Warteschlange mit Timer in Home Assistant,
- HVSC-Songlängen an das Gerät (`.ssl`) und lokal als Timer,
- laufender Tune samt Restzeit auch nach dem erneuten Öffnen der Seite,
- Wiederaufnahme nach einem HA-Neustart über `ultimatecontrol.restore_queue`.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.0.0.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).

## Ausprobieren

In einen Ordner mit vielen Tunes wechseln, weit nach unten scrollen und einen
Tune antippen: die Liste bleibt an ihrer Stelle, der Tune ist grün markiert.
