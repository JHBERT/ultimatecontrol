# 🕹️ UltimateControl for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

**UltimateControl** is a custom Home Assistant integration that brings your **Commodore 64** equipped with an **Ultimate-II+** cartridge (or Ultimate 64) straight into your smart home. Play authentic SID music directly on real hardware, browse the High Voltage SID Collection (HVSC), and launch `.d64` disk images or demos without leaving your couch.

---

## ✨ Features

* **Real Hardware SID Playback:** Send `.sid` files directly to your Ultimate-II+ / C64 and enjoy genuine 6581/8580 sound through your stereo system.
* **HVSC Support:** Browse and play tunes from the High Voltage SID Collection.
* **Disk & Demo Launcher:** Mount and run `.d64` images directly via Home Assistant services or dashboard buttons.
* **Smart Home Automation Ready:** Trigger your favorite chiptune when you get home, start a demo on movie/retro night, or control playback via Lovelace media player cards.

Beyond that, the integration gives you:

* a **media player** entity that plays SID files on the real C64, runs PRG and CRT files, mounts D64/D71/D81 disk images on drive A, and can reset, pause and resume the machine,
* a **media browser source** ("Ultimate C64") that browses the file system of the device — your HVSC copy on the USB stick or SD card included — from the Home Assistant UI, a phone or a tablet,
* **HVSC song lengths**: with the Songlengths database in place, a SID stops being reported as playing when the tune is over,
* a **dashboard card** with a library browser, favourites, playlists, a folder queue and a CSDb tab,
* a **config flow**: set the device up in the UI, no YAML.

---

## 📖 The Story Behind UltimateControl

Ever since the **HardSID** hit the market back in the day, I’ve been looking for a way to enjoy real SID chip tunes on my proper hi-fi setup. Due to a rather tight budget at the time, my chance to grab a HardSID passed me by. The love for the SID, however, never faded.

Fast forward about 20 years: armed with an **Ultimate-II+**, a **C64CU**, and my **Home Assistant** setup — *BOOM!* One man and his SID: **UltimateControl** was born. 

I’m fully aware that this is a massive niche, but maybe a few fellow retro nerds out there will have just as much fun with this integration as I do. 

And hey — **don't buy me a coffee, buy me a beer instead** at one of the next demoscene parties! Just look out for **Hbert** ;-) (most probably standing right next to **Rayden** ;-) ).

> *Rayden, thanks for sharing the love for the SID and the C64 with me! It’s entirely your fault that I’m infected with this virus!* 🍻

---

## ⚙️ Prerequisites

1. A **Commodore 64** with an **Ultimate-II+** cartridge (or an **Ultimate 64**) connected to your local network.
2. **Network Interface / REST API** enabled on your Ultimate device.
3. **Home Assistant** (with [HACS](https://hacs.xyz/) recommended for easy installation).

---

## 🚀 Installation

### Option 1: HACS (Custom Repository)
1. Open **HACS** in your Home Assistant instance.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add the URL `https://github.com/JHBERT/ultimatecontrol` and select **Integration** as the category.
4. Search for **UltimateControl**, click **Download**, and restart Home Assistant.

### Option 2: Manual Installation
1. Copy the `custom_components/ultimatecontrol` folder into your Home Assistant's `config/custom_components/` directory.
2. Restart Home Assistant.

After a HACS update, restart Home Assistant and reload the dashboard hard
(Ctrl+F5) so the browser picks up the new card version.

---

## 🔧 Configuration

*Settings → Devices & services → Add integration → UltimateControl*

| Field | Meaning |
| --- | --- |
| Host | IP address or hostname of the Ultimate, e.g. `192.168.178.50` |
| Port | REST API port, `80` by default |
| Network password | Only if you set one on the device (firmware 3.12+); it is sent as the `X-Password` header |
| Name | Name of the device in Home Assistant |

The options flow (*Configure*) holds the status polling interval (default 30 s)
and lets you change the network password. Several Ultimates can be added; each
one becomes its own device with its own media player entity.

---

## 🗂️ Data folders on the Home Assistant host

The Ultimate cannot download or store files over REST, so anything that is not
already on the device is kept on the Home Assistant host and streamed to the C64
when it is played.

| Folder | Content |
| --- | --- |
| `config/ultimatecontrol/DATA` | The library: SIDs, disks, programs, cartridges, CSDb releases; sub-folders allowed |
| `config/ultimatecontrol/favorites` | Favourites (copies taken out of the library) |
| `config/ultimatecontrol/playlists` | Playlists (references only, one JSON file per playlist) |
| `config/ultimatecontrol/Songlengths.md5` | Optional HVSC song length database |

Up to 1.7.4 the library folder was called `sids`. On startup the integration
renames an existing `config/ultimatecontrol/sids` to `DATA` once; if a `DATA`
folder already exists it wins and the old folder is left untouched.

To take over an existing favourites folder: *Settings → Devices & services →
UltimateControl → Configure → Favourites folder* and point it at the path (for
example `/config/media/favorites`). On save every `.sid` file is copied in.

---

## 🎛️ The dashboard card

The integration brings its own Lovelace card: browse the library, pick a tune,
play it on the C64, keep favourites, build playlists, queue a whole folder and
browse CSDb.

```yaml
type: custom:ultimatecontrol-panel
entry_id: <device entry id>      # optional; otherwise the only device is used
title: Ultimate 2 Cartridge
autostart_method: prg            # prg | keyboard | none
device_picker: true              # show the device dropdown even with entry_id
```

`entry_id` accepts the config entry id, the `unique_id` of the device (for
example `415204`) or part of its name; without it the only configured device is
used.

The card is served by the integration itself
(`/ultimatecontrol_panel/ultimatecontrol-panel.js`) and is registered as a
Lovelace resource automatically. Only a dashboard in YAML mode needs the
resource in `configuration.yaml`:

```yaml
lovelace:
  resources:
    - url: /ultimatecontrol_panel/ultimatecontrol-panel.js?version=1.7.6
      type: module
```

In UI mode: *Settings → Dashboards → ⋮ → Resources*, enter the URL and pick
“JavaScript module”.

### What the card can do

| Action | How |
| --- | --- |
| Browse the library | Tab **DATA**, tap a folder |
| Pick a tune | Tap a file with several tunes → tune buttons with their length |
| Play | Tap a tune button; the file is streamed to the C64 |
| Add a favourite | **★ Favorit** in the “now playing” row |
| Listen to favourites | Tab **★ Favoriten** |
| Import a folder | **＋** opens a folder browser of the Home Assistant host |
| Queue a folder | **▶ Ordner abspielen** plays every SID of the folder in turn |
| Playlists | Tab **Playlists**: create, fill, reorder, play |
| Demos from CSDb | Tab **CSDb**: latest releases, top demos, release page, download |
| Choose the device | Dropdown in the header when several Ultimates are configured |

Selecting a sub-tune or opening the tune list never rebuilds the list, so the
scroll position stays where it is.

### Importing SIDs

The **＋** button opens a folder browser for the Home Assistant host: `↑` goes
up, tap a folder, the bottom line says how many SID files it holds; “Diesen
Ordner importieren” copies them, sub-folders included, into the library. The
same thing as a service: `ultimatecontrol.import_folder`.

---

## 🎵 Song lengths

Song lengths are sent along with the upload and read from the HVSC file
`Songlengths.md5` by MD5 — sub-tune accurate, also for files that only travel to
the C64 as a stream. Put the database in `config/ultimatecontrol/`:

* `Songlengths.md5` from the HVSC (`C64Music/DOCUMENTS/Songlengths.md5`), or
* a faster JSON version, built once with

  ```
  python tools/build_songlengths.py Songlengths.md5 Songlengths.json
  ```

The card's footer shows the local HVSC release, offers **Prüfen** to ask a
mirror for a newer one and **Holen** to download the database. Without the
database a SID simply keeps playing on the C64 until it is stopped or another
file is started.

The player on the device takes the length as a second `file` part of the
multipart request to `/v1/runners:sidplay`: two packed BCD bytes (minutes,
seconds) per sub-tune, 512 bytes at most.

---

## 💾 Disks, programs and cartridges

The card shows **D64/D71/D81/G64/G71**, **PRG** and **CRT** from the library
next to the SIDs. A click uploads the file and starts it:

| File | Call on the device |
| --- | --- |
| D64, D71, D81, G64, G71 | `POST /v1/drives/a:mount` with the image as body (mode `readonly`) |
| PRG | `POST /v1/runners:run_prg` with the file as attachment |
| CRT | `POST /v1/runners:run_crt` with the file as attachment |

Nothing has to be copied to the Ultimate over FTP first. The websocket command
is `ultimatecontrol/image_play` (`path`, `source`, optional `drive`, `mode` and
`autostart`).

### Disk autostart

The card inserts a disk **and starts it**: the first PRG is read out of the image
(`d64.py`) and loaded through `POST /v1/runners:run_prg` — the autostart the API
does not offer for disks itself. The disk stays in drive A, so loading further
files works. With `autostart: false` it is only inserted.

`autostart_method: keyboard` starts a disk the way you would by hand: the
machine is reset, then the integration types `LOAD"*",8,1` and RETURN into the
KERNAL keyboard buffer (`PUT /v1/machine:writemem` at `$0277`, length at
`$00C6`). That is the classic route and also works for images whose directory
cannot be read here. The command can be overridden with `load_command` (for
example `LOAD"DEMO",8,1`). In the card `autostart_method: keyboard|prg` switches
between the two; the default is `prg`.

### Multi-part demos: insert only

`autostart_method: none` inserts the disk and starts nothing. That is what
multi-part demos need: the running demo asks for the next disk and the swap is
only a mount — no reset, no `LOAD`. Set it in the card configuration or send
`autostart_method: "none"` over the websocket.

---

## ⏭️ Folder queue

**▶ Ordner abspielen** puts every SID of the current folder into a queue and
plays them one after another. The timer lives in Home Assistant: one background
task per tune with a generation counter, the end time in the entity state. The
bar in the card has ⏮ ⏭ ⏸ ⏹. Websocket commands:
`ultimatecontrol/queue_play_folder`, `queue_action`, `queue_status`; the service
`ultimatecontrol.restore_queue` restores the queue after a restart.

---

## 🎼 Playlists

The **Playlists** tab keeps named lists that store references only, never copies
of the SIDs — one JSON file per playlist under
`config/ultimatecontrol/playlists`. Websocket commands:
`ultimatecontrol/playlists`, `playlist_get`, `playlist_add`, `playlist_edit`,
`playlist_play`.

---

## 🖥️ Several devices in one card

When several Ultimates are configured and the card has **no** `entry_id`, the
header shows a **dropdown** to pick the player. Folder, queue, playlists and the
running tune each belong to the selected device, and the browser remembers the
choice. With `entry_id` the card stays on one device (`device_picker: true`
shows the dropdown anyway, `false` hides it).

---

## 🎬 CSDb (csdb.dk)

The **CSDb** tab shows the two tables of the CSDb front page: **Latest
Releases** and **Top Demos**, five entries each. A click on the heading opens
the whole list (25 releases, or the complete demo chart), a click on an entry
opens the release page with type, date, group, event and placing, rating,
credits, the SIDs used, download links and the newest comments. **‹ Zurück** in
the top left goes one level back.

A download can be unpacked straight into the library
(`config/ultimatecontrol/DATA/csdb/<Type>/<initial>/<Group>/<Name> [<Year>]/`)
and started from there; the websocket commands are
`ultimatecontrol/csdb_front`, `csdb_list`, `csdb_release` and `csdb_install`.
Lists are cached for five minutes so a dashboard refresh does not load CSDb.

CSDb has no search webservice, only a lookup by id, so the lists are parsed from
the HTML of the pages and a release comes from
`/webservice/?type=release&id=<id>&depth=2`.

---

## 🤖 Media browser, actions and automations

*Media → Ultimate C64* shows the folders of the device (`/Usb0`, `/Sd`, ...).
Open a folder, tap a `.sid` file → *Play* → pick the media player entity. The C64
starts playing it.

For a specific sub-tune, play
`media-source://ultimatecontrol//Usb0/path/tune.sid#2` (`#2` = sub-tune 2)
through the `media_player.play_media` action.

```yaml
# Play a SID from the Ultimate's own file system
action: media_player.play_media
target:
  entity_id: media_player.ultimate_c64
data:
  media_content_id: /Usb0/C64Music/MUSICIANS/H/Hubbard_Rob/Commando.sid
  media_content_type: music

# Play sub-tune 3 of that file
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

### HVSC on Home Assistant instead of on the C64

If the HVSC lives on the Home Assistant host rather than on the Ultimate, put
the folder in the library and play the files by their local path. The
integration uploads the SID to `/Temp/UltimateControl` on the device and plays
it from there.

---

## 📌 Requirements and notes

* Ultimate firmware **3.11+** (network password: 3.12+), *Web Remote Control*
  enabled, and the Home Assistant host must be able to reach the device over
  HTTP.
* The C64 has no feedback channel, so the entity's state follows what Home
  Assistant started: a SID is “playing” until its song length has passed, a
  program or disk image leaves the entity “on”. The device itself is polled
  (`/v1/info`) so the entity becomes unavailable when it is switched off.
* Browsing the device uses FTP (`NLST`) plus the REST stat call; playing by path
  works without a listing.
* Not implemented yet: Icecast streaming, mounting images on drive B, importing
  the full HVSC package (it ships as `.7z` with a BCJ2 filter that Python's
  `lzma` cannot unpack).

---

## 🛠️ Development

```
pip install aiohttp pytest pytest-asyncio
pytest -q
```

The tests in `tests/` start a small aiohttp server that answers like an Ultimate
device, so the API client, the request it builds and the song length parser are
covered without hardware and without Home Assistant.

---

## 📄 License

UltimateControl is released under the **MIT license** — see [`LICENSE`](LICENSE).
In short: use it, change it, pass it on, commercial use included; the copyright
notice and the license text have to stay with it. No warranty.

What comes from others (interfaces, formats, data, ideas) and what does not is
listed in [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md). In short: **no
third-party code in the repository**, no bundled third-party libraries, no HVSC
data in the package.

---

## 🙏 Acknowledgements

Thanks to **Gideon Zweijtzer** for the 1541 Ultimate and the Ultimate 64 and for
the open, well documented REST interface
(<https://1541u-documentation.readthedocs.io>) — without both, this integration
would not exist.

Thanks to Christian „Peri Fractic“ Simpson for the work on the C64 and for the
help in the scene.

Thanks to the **Commodore team and the community** who have kept this computer
alive for more than forty years.

Thanks to the **High Voltage SID Collection** (<https://hvsc.c64.org>) for the
song length database and more than 61,000 SIDs, and to **CSDb**
(<https://csdb.dk>) for the largest archive of the C64 scene.
