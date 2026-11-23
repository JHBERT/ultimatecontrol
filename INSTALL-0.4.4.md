# Warum unter „Ressourcen" nichts steht – und was 0.4.4 ändert

## Was ich bisher geändert habe und warum es nicht half
| Version | Änderung | Warum es nicht half |
| --- | --- | --- |
| 0.4.2 | Card-URL wird in die Lovelace-Ressourcen geschrieben | Der Schreibvorgang läuft nur, wenn `hass.data["lovelace"]` schon existiert – war es nicht, passierte **still nichts** |
| 0.4.3 | Danach `async_reload` der Sammlung | Setzt denselben Punkt voraus; ohne Lovelace-Daten wird auch das nie erreicht |

## Die Ursache (geprüft am Home-Assistant-Quelltext, Stand dev)
- `homeassistant/components/lovelace/__init__.py`, `async_setup()`:
  `hass.data[LOVELACE_DATA] = LovelaceData(...)` – die Ressourcen-Sammlung hängt
  **ausschließlich** an diesem Eintrag.
- `homeassistant/components/lovelace/const.py`: `LOVELACE_DATA = HassKey(DOMAIN)`
  → Schlüssel ist der String `"lovelace"`.
- `homeassistant/components/frontend/manifest.json`: `lovelace` steht dort in
  `dependencies` – eine Integration **ohne** diese Abhängigkeit darf HA vorher
  einrichten.
- Meine `manifest.json` hatte `lovelace` nicht in `dependencies` → meine
  Registrierung konnte ins Leere laufen und meldete keinen Fehler (mein Code
  fängt das bewusst ab).

## Was 0.4.4 macht
- `dependencies`: `["media_source", "http", "websocket_api", "lovelace"]` –
  damit ist beim Setup garantiert da, was ich brauche.
- Das Modul importiert die Lovelace-Komponente nicht mehr selbst (nur noch für
  die Typ-Prüfung), damit ein fehlendes Dashboard das Setup nie stören kann.

## Was ich hier tatsächlich ausgeführt habe
- Das Modul aus dem **Release-ZIP v0.4.4** geladen, mit absichtlich *nicht*
  vorhandener Lovelace-Komponente: lädt fehlerfrei.
- Registrierung gegen eine nachgebaute Sammlung ausgeführt:
  Eintrag `{"res_type": "module", "url": "/x.js?version=0.4.4"}` wird angelegt,
  Reload wird ausgelöst.
- Release-ZIP geprüft: `version` 0.4.4, `dependencies` enthält `lovelace`,
  Card-URL `?version=0.4.4`.
- 31 Tests grün.

## Was du machen musst
1. HACS → UltimateControl C64 → Update auf **0.4.4**
2. Home Assistant **neu starten** (die Abhängigkeit wirkt nur beim Setup)
3. Einstellungen → Dashboards → **Ressourcen**: dort muss jetzt
   `…/ultimatecontrol-panel.js?version=0.4.4` stehen
4. Protokoll, Filter `ultimatecontrol`: „Added the dashboard card as a Lovelace resource“
5. Karte: `type: custom:ultimatecontrol-panel` (`entry_id` optional), dann Strg+F5

## Wenn es dann immer noch leer ist
Dann ist eine der drei Annahmen falsch – und das Protokoll sagt, welche:
- **„Lovelace is not set up"** (Debug-Level): Lovelace fehlt weiterhin → dann
  läuft bei dir kein Standard-Dashboard.
- **„Lovelace runs in YAML mode"**: dein Dashboard läuft im YAML-Modus, dann
  gehört die Ressource in deine `configuration.yaml`:
  `- url: /ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.4` / `type: module`
- **gar keine Zeile**: die Registrierung wurde nie erreicht → dann stimmt die
  installierte Version nicht (HACS zeigt sie unter „Installierte Version").
