# Wie die Updates über HACS ankommen (und warum 0.4.1 bisher nicht kam)

Du beziehst alles über HACS und hast nichts von Hand eingespielt – das ist
richtig so. Der Grund, warum die Card fehlt, liegt aber nicht bei HACS, sondern
daran, **was HACS dir ausliefert**:

## Was HACS nimmt
HACS installiert von einem GitHub-**Release** (falls vorhanden), sonst vom
**Default-Branch**. Zwei Dinge müssen deshalb stimmen:

1. **Ein Release mit Tag muss existieren.** Es gab bis jetzt **keinen einzigen
   Tag** im Repo – also hat HACS immer `main` genommen oder gar nichts
   aktualisiert. Ab jetzt: Tag **`v0.4.1`** (gesetzt, gepusht).
2. **`manifest.json` muss die Version tragen.** In 0.2.0/0.3.0 stand teilweise
   noch `0.2.0`; HACS vergleicht diese mit dem Release und meldet sonst kein
   Update. In 0.4.1 steht `"version": "0.4.1"` im Tag.

## Was du jetzt machst
1. HACS → **UltimateControl C64** öffnen → ⋮ → **Update information**
   (bzw. „Neu laden"), damit HACS die Releases neu einliest.
2. Update auf **0.4.1** installieren (falls HACS 0.4.1 noch nicht anbietet:
   ⋮ → **Redownload** → Version `v0.4.1` wählen).
3. Home Assistant neu starten.
4. Prüfen, dass die Card-Datei da ist: Dateieditor/SSH → sie muss existieren:
   `config/custom_components/ultimatecontrol/frontend/ultimatecontrol-panel.js`
   Fehlt der Ordner `frontend`, läuft noch die alte Version.
5. Dashboard-Ressource (einmalig, nur du kannst das):
   Einstellungen → Dashboards → ⋮ → Ressourcen → 
   `/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.1`,
   Typ **JavaScript-Modul**.

## Woran du merkst, dass 0.4.1 läuft
- `http://homeassistant.local:8123/ultimatecontrol_panel/ultimatecontrol-panel.js`
  liefert in einem **privaten Fenster ohne Login** JavaScript (kein Login, keine 401).
- Die Karte erscheint; `entry_id` darf `415204` sein oder ganz fehlen.

## Was noch offen ist: die Ressource automatisch registrieren
Aktuell musst du die Ressource einmal eintragen. Damit sie „von allein" da ist,
müsste die Integration sie in den Lovelace-Speicher schreiben – das geht nur,
wenn das Dashboard im **Speicher-Modus** läuft, und braucht Zugriff auf die
interne Lovelace-Konfiguration. Sag Bescheid, dann baue ich das ein (mit
sauberem Fallback für den YAML-Modus).
