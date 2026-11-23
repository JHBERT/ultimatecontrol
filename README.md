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
