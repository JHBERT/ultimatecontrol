# 0.4.2 war installiert – und trotzdem blieb die Card weg

## Was ich geändert habe und warum es nicht gereicht hat
- **0.4.2**: Die Integration schreibt ihre Card-URL in die Lovelace-Ressourcen.
  Das hat auch funktioniert – HACS zeigte „Installierte Version 3b90185 /
  Neueste v0.4.2", der Knopf ist **ausgegraut, weil 0.4.2 bereits installiert
  ist**. Der Knopf sagt also nichts über die Card.
- **Warum die Card trotzdem fehlte**: Ein laufendes Dashboard hält eine
  **eigene Kopie** der Ressourcenliste. Der neue Eintrag lag zwar im Speicher,
  aber die Dashboards wurden nie angewiesen, ihn zu lesen. Der Browser hat die
  Card-Datei deshalb nie geladen → „Custom element doesn't exist".

## Was 0.4.3 ändert (kleinster Eingriff)
Nach dem Anlegen bzw. Aktualisieren des Eintrags wird die Ressourcen-Sammlung
neu geladen (`async_reload`). Die Dashboards bekommen die URL damit **ohne
Neustart**.

## Woran du merkst, dass es diesmal ankommt
1. Nach dem Update auf 0.4.3 und einem Neustart: Einstellungen → Dashboards →
   **Ressourcen** enthält `…/ultimatecontrol-panel.js?version=0.4.3`.
2. Protokoll (Einstellungen → System → Protokolle), Filter `ultimatecontrol`:
   „Added the dashboard card as a Lovelace resource“.
3. Card-Datei ohne Login im privaten Fenster öffnen:
   `http://homeassistant.local:8123/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.3`
   → muss JavaScript liefern, keinen Login-Dialog.
4. Karte anlegen: `type: custom:ultimatecontrol-panel` (mit `entry_id: 415204`
   oder ganz ohne), danach Browser hart neu laden (Strg+F5).

## Der „Aktualisieren"-Knopf
Ist die installierte Version gleich der neuesten, bleibt er ausgegraut – das ist
kein Fehler. Nach dem Update auf 0.4.3 zeigt HACS wieder eine echte
Versionsnummer statt des Commits, weil Manifest, Tag und Release jetzt
dieselbe Nummer tragen.

## Was ich hier nicht prüfen kann
Deine HA-Instanz (kein Zugang). Geprüft habe ich am Release-ZIP von v0.4.3:
`manifest.json` = 0.4.3, Card-URL mit `?version=0.4.3`, `async_reload` im Code
vorhanden; 31 Tests grün.
