# UltimateControl 0.4.0 – Tune-Auswahl im Dashboard, Favoriten, Import

## Was neu ist

**Tune-Auswahl pro Datei.** Eine SID mit mehreren Tunes antippen → Tune-Knöpfe
**1 … 19** mit der jeweiligen Länge. Ein Klick auf die Nummer startet genau
diesen Tune auf dem C64. Am Gerät geprüft: `songnr` 1…19 werden angenommen,
20 → `Invalid Song Number Requested`, also kann die Integration vorher prüfen.

**Songlängen aus der HVSC.** Beim Abspielen wird die Länge des gewählten Tunes
mitgeschickt und angezeigt. Sie kommt aus `Songlengths.md5` (MD5 der Datei,
Untertune-genau) – das funktioniert auch für Dateien, die nur als Stream zum C64
gehen. Datei nach `config/ultimatecontrol/Songlengths.md5` legen (aus dem HVSC:
`DOCUMENTS/Songlengths.md5`). Ohne die Datei bleibt die Länge leer („–“).

**Favoriten.** In der Zeile „läuft gerade“ sitzt der Knopf **★ Favorit**: er
kopiert die laufende Datei in den Favoriten-Ordner. Der Reiter **★ Favoriten**
spielt sie wieder ab.

**Deinen eigenen Favoriten-Ordner übernehmen.** Einstellungen → Integrationen →
UltimateControl → **Konfigurieren** → *Favourites folder* auf den Pfad setzen
(z. B. `/config/media/favoriten`). Beim Speichern werden alle `.sid`-Dateien
(inkl. Unterordner) in die Favoriten kopiert – nichts wird verschoben.

**Import in die Bibliothek.** Alles, was in `config/ultimatecontrol/sids` liegt
(mit Unterordnern), erscheint im Reiter **HVSC**. Ein Ordner auf dem HA-Rechner
lässt sich per Service-Aufruf übernehmen:

```yaml
action: ultimatecontrol.import_folder
data:
  entry_id: <Geräte-ID>
  folder: /config/media/phat - Test Set
  subfolder: phat            # optional
```

**Warum eine eigene Card und nicht der Medienbrowser?** Das Ultimate II+ kann
Dateien weder per REST herunter- noch hochladen (geprüft: 404) und hat kein
beschreibbares RAM-Laufwerk. Alles, was nicht schon auf dem Gerät liegt, wird
deshalb als Stream an den `sidplay`-Runner geschickt. Und eine Untertune-Auswahl
braucht den Header der Datei – also muss die Datei auf dem HA-Rechner liegen.
Der Medienbrowser bleibt für das, was auf dem Gerät ist (Flash, USB).

## Installation

1. ZIP entpacken, Inhalt nach `config/custom_components/ultimatecontrol/`
   (Ordner ersetzen; neu: `frontend/`, `library.py`, `websocket_api.py`).
2. Home Assistant neu starten.
3. Card aufs Dashboard:

```yaml
type: custom:ultimatecontrol-panel
entry_id: <ID des Geräts>     # Einstellungen → Geräte → dein Ultimate
title: Ultimate 2 Cartridge
```

Die Card wird von der Integration ausgeliefert
(`/ultimatecontrol_panel/ultimatecontrol-panel.js`). Läuft dein Dashboard im
YAML-Modus, als Ressource eintragen; im UI-Modus unter Einstellungen →
Dashboards → ⋮ → Ressourcen mit Typ „JavaScript-Modul“:

```
/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.0
```

## Test-Stand

- 40 SIDs aus `D:\phat - Test Set` per Stream auf dem Ultimate II+
  (192.168.178.63) gespielt: 40/40 ohne Fehler.
- Bibliothek/Favoriten/Import lokal gegen die 40 Dateien getestet
  (Tune-Zahlen aus dem PSID-Header: `Bad_Cat_PSID.SID` 19, `Alien_Syndrome.SID` 27 …).
- 24 automatisierte Tests grün (`pytest -q`).
- Card im Browser durchgeklickt: Tune-Knöpfe erscheinen, Auswahl startet,
  Favoriten-Reiter listet die Kopien.

## Was als Nächstes kommt (noch nicht drin)

- **Demos aus der Demoscene direkt starten**: über den `run_prg`-Runner mit
  Stream (wie bei SIDs) – die Card bekommt dafür einen dritten Reiter.
- **SID-Streaming** (Icecast), damit der Browser mithört.
- Laufende Anzeige (Play/Pause/Stop) mit Songlängen-Timer auf der Card.
