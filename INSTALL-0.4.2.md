# UltimateControl 0.4.2 – die Card trägt sich selbst ein

## Neu
Beim Setup schreibt die Integration ihre Card als **Lovelace-Ressource**:

- im normalen (Speicher-)Modus automatisch, du musst nichts eintragen
- eine vorhandene Ressource mit älterer Versions-Marke
  (`…panel.js?version=0.4.1`) wird auf 0.4.2 umgeschrieben – kein Doppel-Eintrag
- im YAML-Modus wird **nichts** verändert; das Snippet steht dann im Log:
  `- url: /ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.2` / `type: module`
- schlägt etwas fehl, läuft die Integration trotzdem weiter

## So aktualisierst du
1. HACS → UltimateControl C64 → ⋮ → **Update information** → Update auf **0.4.2**
2. Home Assistant **neu starten**
3. Karte aufs Dashboard:

```yaml
type: custom:ultimatecontrol-panel
entry_id: 415204        # optional, darf auch fehlen
title: Ultimate 2 Cartridge
```

## Woran du 0.4.2 erkennst
- Einstellungen → Dashboards → **Ressourcen** enthält
  `/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.2` (Typ JavaScript-Modul),
  ohne dass du sie angelegt hast.
- Die Karte lädt; „Custom element doesn't exist“ ist weg.
- Im Log (Einstellungen → System → Protokolle) steht einmalig
  „Added the dashboard card as a Lovelace resource“.

## Falls die Karte trotzdem nicht kommt
1. Browser hart neu laden (Strg+F5) bzw. HA-App neu öffnen.
2. Prüfen, ob die Datei existiert:
   `config/custom_components/ultimatecontrol/frontend/ultimatecontrol-panel.js`
3. Die URL ohne Login im privaten Fenster öffnen:
   `http://homeassistant.local:8123/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.2`
   – muss JavaScript liefern, keinen Login-Dialog.
4. Steht in den Ressourcen noch `?version=0.4.1` oder fehlt der Eintrag, wurde
   die neue Fassung noch nicht geladen (Schritt 1/2 wiederholen).

## Stand der Versionen im Repo
| Ort | Wert |
| --- | --- |
| `manifest.json` | 0.4.2 |
| Tag | `v0.4.2` |
| GitHub-Release | v0.4.2 (kein Draft, kein Pre-Release) |
| Card-URL | `?version=0.4.2` |

29 Tests grün (`pytest -q`), davon 5 für die Ressourcen-Registrierung.
