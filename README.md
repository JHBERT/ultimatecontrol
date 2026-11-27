# UltimateControl

Home Assistant custom integration for a Commodore 64 with a **1541 Ultimate II+**
cartridge (also works with the Ultimate 64 / Ultimate 64 Elite mainboards).

The integration talks to the device's REST API (firmware 3.11 or newer, *Web
Remote Control* enabled in the Ultimate menu) and gives you:

* a **media player** entity that plays SID files on the real C64, runs PRG and
  CRT files, mounts D64/D71/D81 disk images on drive A, and can reset, pause
  and resume the machine,
* a **media browser source** ("Ultimate C64") that browses the file system of
  the device – your HVSC copy on the USB stick or SD card included – from the
  Home Assistant UI, a phone or a tablet,
* **HVSC song lengths**: with the Songlengths database in place, a SID stops
  being reported as playing when the tune is over,
* a **config flow**: set the device up in the UI, no YAML.


### Karte konfigurieren (ab 0.5.0)
Beim Hinzufügen der Karte öffnet sich ein Dialog mit einem **Geräte-Dropdown**
(alle eingerichteten Ultimates, „Automatisch“ = erstes Gerät) und einem
Titel-Feld. In YAML bleibt `entry_id` optional.

### SIDs importieren (ab 0.5.0)
Der Knopf **＋** in der Karte öffnet einen Ordner-Browser für den
Home-Assistant-Rechner: mit `↑` nach oben, Ordner antippen, unten steht, wie viele
SID-Dateien drin liegen; „Diesen Ordner importieren“ kopiert sie (samt
Unterordnern) in die Bibliothek. Derselbe Vorgang per Service:
`ultimatecontrol.import_folder`.

## SID-Auswahl im Dashboard (ab 0.4.0)

Die Integration bringt eine eigene Lovelace-Card mit: HVSC durchsuchen, einen
Tune wählen, auf dem C64 abspielen, Favoriten pflegen.

**Card hinzufügen**

```yaml
type: custom:ultimatecontrol-panel
entry_id: <ID des Geräts>      # optional; sonst nimmt die Card das einzige Gerät
title: Ultimate 2 Cartridge
```

`entry_id` akzeptiert die Config-Entry-ID, die `unique_id` des Geräts (z. B.
`415204`) oder einen Teil des Namens; ohne Angabe wird das einzige eingerichtete
Gerät genommen.

Die Card wird von der Integration selbst ausgeliefert
(`/ultimatecontrol_panel/ultimatecontrol-panel.js`) und seit 0.4.2 **automatisch
als Lovelace-Ressource eingetragen** – im UI-Modus musst du nichts tun. Nur wenn
dein Dashboard im YAML-Modus läuft, gehört die Ressource in deine
`configuration.yaml`:

```yaml
lovelace:
  resources:
    - url: /ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.5.0
      type: module
```

Im UI-Modus: Einstellungen → Dashboards → ⋮ → Ressourcen → URL oben eintragen,
Typ „JavaScript-Modul“.

**Was die Card kann**

| Aktion | Wie |
| --- | --- |
| HVSC/Bibliothek durchsuchen | Reiter **HVSC**, Ordner antippen |
| Tune wählen | Datei mit mehreren Tunes antippen → Tune-Knöpfe mit Länge |
| Abspielen | Tune-Knopf antippen; die Datei wird zum C64 gestreamt |
| Favorit hinzufügen | Knopf **★ Favorit** in der Zeile „läuft gerade“ |
| Favoriten anhören | Reiter **★ Favoriten** |

**Ordner auf dem HA-Rechner**

| Ordner | Inhalt |
| --- | --- |
| `config/ultimatecontrol/sids` | Bibliothek (HVSC); Unterordner erlaubt |
| `config/ultimatecontrol/favorites` | Favoriten (Kopien aus der Bibliothek) |
| `config/ultimatecontrol/Songlengths.md5` | optionale HVSC-Songlängen |

Deinen Favoriten-Ordner einmalig übernehmen: Einstellungen → Integrationen →
UltimateControl → **Konfigurieren** → *Favourites folder* auf den Pfad setzen
(z. B. `/config/media/favoriten`). Beim Speichern werden alle `.sid`-Dateien
hineinkopiert.

**Songlängen**: werden beim Abspielen mitgeschickt und aus der HVSC-Datei
`Songlengths.md5` per MD5 gelesen – Untertune-genau, auch für Dateien, die nur
als Stream zum C64 gehen.

## Installation (HACS)

1. HACS → *Integrations* → three-dot menu → *Custom repositories*
2. Add `https://github.com/JHBERT/ultimatecontrol`, category *Integration*
3. Install **UltimateControl C64** and restart Home Assistant
4. *Settings → Devices & services → Add integration → UltimateControl C64*

Manual install: copy `custom_components/ultimatecontrol` into your
`config/custom_components/` folder and restart.

## Configuration

| Field | Meaning |
| --- | --- |
| Host | IP address or hostname of the Ultimate, e.g. `192.168.178.50` |
| Port | REST API port, `80` by default |
| Network password | Only if you set one on the device (firmware 3.12+); it is sent as the `X-Password` header |
| Name | Name of the device in Home Assistant |

The options flow (*Configure*) holds the status polling interval (default 30 s)
and lets you change the network password.

## Using it

The integration creates one device with one media player entity.

### From the media browser

*Media → Ultimate C64* shows the folders of the device (`/Usb0`, `/Sd`, ...).
Open a folder, tap a `.sid` file → *Play* → pick the media player entity. The
C64 starts playing it.

For a specific sub tune, play `media-source://ultimatecontrol//Usb0/path/tune.sid#2`
(`#2` = sub tune 2) through the `media_player.play_media` action.

### From automations

```yaml
# Play a SID from the Ultimate's own file system
action: media_player.play_media
target:
  entity_id: media_player.ultimate_c64
data:
  media_content_id: /Usb0/C64Music/MUSICIANS/H/Hubbard_Rob/Commando.sid
  media_content_type: music

# Play sub tune 3 of that file
data:
  media_content_id: "/Usb0/C64Music/MUSICIANS/H/Hubbard_Rob/Commando.sid#3"

# Start a game
data:
  media_content_id: /Usb0/Games/Bubble_Bobble.prg

# Mount a disk image on drive A (read-only)
data:
  media_content_id: /Usb0/D64/Giana_Sisters.d64
```

Supported files: `.sid` (play), `.prg` / `.crt` (run), `.d64` `.d71` `.d81`
`.g64` `.g71` (mount on drive A, read-only).

`media_player.turn_off` and `media_player.media_stop` reset the C64;
`media_player.media_pause` / `media_player.media_play` freeze and continue the
machine through the device's pause/resume API.

## HVSC on Home Assistant instead of on the C64

If the HVSC lives on the Home Assistant host rather than on the Ultimate, put
the folder in your config directory and play the files by their local path.
The integration uploads the SID to `/Temp/UltimateControl` on the device and
plays it from there.

For song lengths, place the HVSC song length database in
`config/ultimatecontrol/`:

* `Songlengths.md5` from the HVSC (`C64Music/DOCUMENTS/Songlengths.md5`), or
* a faster JSON version, built once with

  ```
  python tools/build_songlengths.py Songlengths.md5 Songlengths.json
  ```

Without the database, a SID simply keeps playing on the C64 until it is stopped
or another file is started.

## Requirements and notes

* Ultimate firmware **3.11+** (network password: 3.12+), *Web Remote Control*
  enabled, and the Home Assistant host must be able to reach the device over
  HTTP.
* The C64 has no feedback channel, so the entity's state follows what Home
  Assistant started: a SID is "playing" until its song length has passed, a
  program or disk image leaves the entity "on". The device itself is polled
  (`/v1/info`) so the entity becomes unavailable when it is switched off.
* Browsing uses `GET /v1/files/<path>`. Firmware releases answer that route in
  slightly different shapes; the client accepts the common ones. If your
  firmware returns nothing useful there, playing by path still works.
* Not implemented yet: FTP upload of large collections, Icecast streaming
  (see the project notes), and mounting images on drive B.

## Development

```
pip install aiohttp pytest pytest-asyncio
pytest -q
```

The tests in `tests/` start a small aiohttp server that answers like an
Ultimate device, so the API client, the request it builds and the song length
parser are covered without hardware and without Home Assistant.

## Disketten und Programme aus der Bibliothek (ab 1.3.0)

Neben SIDs zeigt die Karte jetzt auch **D64/D71/D81/G64/G71**, **PRG** und
**CRT** aus der Bibliothek. Ein Klick lädt die Datei hoch und startet sie:

| Datei | Aufruf am Gerät |
|---|---|
| D64, D71, D81, G64, G71 | `POST /v1/drives/a:mount` mit dem Image als Rumpf (Modus `readonly`) |
| PRG | `POST /v1/runners:run_prg` mit der Datei als Anhang |
| CRT | `POST /v1/runners:run_crt` mit der Datei als Anhang |

Es muss also nichts vorher per FTP auf das Ultimate kopiert werden. Der
Websocket-Befehl heißt `ultimatecontrol/image_play` (`path`, `source`, optional
`drive`, `mode` und `autostart`).

### Autostart einer Diskette (ab 1.4.0)

Die Karte legt eine Diskette ein **und startet sie**: aus dem Image wird das
erste PRG gelesen (`d64.py`) und über `POST /v1/runners:run_prg` geladen und
gestartet – das ist der Autostart, den die API für Disketten selbst nicht hat.
Die Diskette bleibt dabei in Laufwerk A eingelegt, Nachladen funktioniert also.
Mit `autostart: false` wird nur eingelegt.

### Autostart per Tastatur (ab 1.5.0)

`autostart_method: keyboard` startet eine Diskette wie von Hand: die Maschine
wird zurückgesetzt, dann tippt die Integration `LOAD"*",8,1` und RETURN in den
Tastaturpuffer des KERNAL (`PUT /v1/machine:writemem` auf `$0277`, Länge nach
`$00C6`). Das ist der klassische Weg und funktioniert auch bei Images, deren
Verzeichnis hier nicht lesbar ist. Der Befehl lässt sich mit `load_command`
überschreiben (z. B. `LOAD"DEMO",8,1`). In der Karte schaltet
`autostart_method: keyboard|prg` um; Standard ist `prg`.

## Mehrere Geräte in einer Karte (ab 1.2.0)

Sind mehrere Ultimates eingerichtet und die Karte hat **keine** `entry_id`,
zeigt sie im Kopf ein **Dropdown** zur Wahl des Abspielgeräts. Ordner, Queue,
Playlists und der laufende Tune gehören jeweils zum gewählten Gerät; die Wahl
merkt sich der Browser. Mit `entry_id` bleibt die Karte fest an einem Gerät
(`device_picker: true` zeigt das Dropdown trotzdem, `false` blendet es aus).

## Lizenz

UltimateControl steht unter der **MIT-Lizenz** – siehe [`LICENSE`](LICENSE).
Kurz gesagt: benutzen, verändern, weitergeben und auch kommerziell einsetzen
ist erlaubt; es muss nur der Copyright-Hinweis und der Lizenztext beiliegen.
Keine Gewährleistung.

Was von anderen stammt (Schnittstellen, Formate, Daten, Anregungen) und was
nicht, steht in [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md). Kurz:
**kein fremder Code im Repository**, keine mitgelieferten Fremdbibliotheken,
keine HVSC-Daten im Paket.
