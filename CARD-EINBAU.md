# Die Dashboard-Card einbauen (UltimateControl 0.4.0)

Die Card wird **von der Integration selbst ausgeliefert** – du musst keine Datei
nach `config/www` kopieren. Nötig sind drei Schritte: ZIP einspielen, Ressource
eintragen, Card anlegen.

## 1. Integration aktualisieren

Inhalt von `ultimatecontrol-0.4.0.zip` nach
`config/custom_components/ultimatecontrol/` (Ordner ersetzen; neu sind
`frontend/`, `library.py`, `websocket_api.py`, `services.yaml`), dann
**Home Assistant neu starten**.

Prüfen: Einstellungen → Geräte & Dienste → UltimateControl – die beiden Geräte
müssen da sein, und unter *Entwicklerwerkzeuge → Aktionen* taucht
`ultimatecontrol.import_folder` auf. Wenn nicht, wurde der Ordner nicht richtig
ersetzt.

## 2. Ressource eintragen

Die Card ist ein JavaScript-Modul. Home Assistant muss wissen, wo es liegt.

**Mit UI (Standard):** Einstellungen → Dashboards → oben rechts **⋮** →
**Ressourcen** → **Ressource hinzufügen**

```
URL:  /ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.0
Typ:  JavaScript-Modul
```

**Im YAML-Modus** (`configuration.yaml`):

```yaml
lovelace:
  mode: yaml
  resources:
    - url: /ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.0
      type: module
```

Danach einmal hart neu laden (Strg+F5). Fehlt die Ressource, zeigt das Dashboard
nur „Custom element doesn't exist: ultimatecontrol-panel“.

## 3. Geräte-ID heraussuchen

Die Card braucht die ID deines Ultimate-2-Cartridge-Eintrags.

Einstellungen → Geräte & Dienste → **UltimateControl** → auf den Eintrag
„Ultimate 2 Cartridge" klicken. Die ID steht in der Adresszeile:

```
http://homeassistant.local:8123/config/integrations/integration/ultimatecontrol#config_entry=01JABCDEF...
```

Alles nach `config_entry=` ist die ID (`01JAB…`).

## 4. Card aufs Dashboard

Dashboard öffnen → **Bearbeiten** → **Karte hinzufügen** → unten
**Manuell** (YAML) und einfügen:

```yaml
type: custom:ultimatecontrol-panel
entry_id: 01JABCDEF...
title: Ultimate 2 Cartridge
```

Speichern. Die Card zeigt oben rechts die Reiter **HVSC** und **★ Favoriten**.

## 5. Dateien bereitstellen

| Was | Wohin |
| --- | --- |
| HVSC / Sammlung | `config/ultimatecontrol/sids` (Unterordner erlaubt) |
| Favoriten | `config/ultimatecontrol/favorites` (füllt die Card selbst) |
| Songlängen | `config/ultimatecontrol/Songlengths.md5` (aus dem HVSC: `DOCUMENTS/Songlengths.md5`) |

Ohne Songlängen-Datei bleibt die Länge leer („–“). Deinen eigenen
Favoriten-Ordner einmalig setzen: UltimateControl → **Konfigurieren** →
*Favourites folder* (z. B. `/config/media/favoriten`). Beim Speichern werden
alle `.sid` daraus kopiert.

Ordner in die Bibliothek holen:

```yaml
action: ultimatecontrol.import_folder
data:
  entry_id: 01JABCDEF...
  folder: /config/media/phat - Test Set
  subfolder: phat
```

## Wenn etwas nicht geht

- **„Custom element doesn't exist“** – Ressource fehlt oder wurde nicht neu
  geladen (Strg+F5 bzw. App neu starten).
- **„entry_id fehlt“** – die ID aus Schritt 3 in die Card eintragen.
- **Leere Liste** – in `config/ultimatecontrol/sids` liegen noch keine
  `.sid`-Dateien, oder der Ordner hat die falschen Rechte (HA-Benutzer muss
  lesen dürfen).
- **„device_error“…** – das Gerät ist aus oder die IP hat sich geändert; die
  Integration prüft das alle 30 Sekunden (Option *Status polling interval*).
