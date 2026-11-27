# Danksagung und fremde Bestandteile

UltimateControl steht unter der **MIT-Lizenz** (siehe `LICENSE`);
Rechteinhaber ist **JHBERT** (github.com/JHBERT). Dieses Dokument nennt, was
darin von anderen stammt – Code, Schnittstellen, Daten und Wissen. Es ist
bewusst ausführlich: man soll nachlesen können, woher etwas kommt.

## 1. Fremder Code im Repository

**Keiner.** Alles in `custom_components/ultimatecontrol/` ist für dieses Projekt
geschrieben. Es wird kein fremder Quelltext mitgeliefert, kopiert oder
eingebunden; auch die Karte (`frontend/ultimatecontrol-panel.js`) ist ein
eigenes Web Component ohne Fremdbibliotheken (kein Lit, kein Frameworks).

Damit enthält das Repository **keine** Bestandteile unter einer anderen Lizenz,
die genannt werden müssten. Das ist auch der Grund für die MIT-Lizenz: sie
verträgt sich mit allem, was hier sonst noch zusammenkommt.

## 2. Laufzeit-Abhängigkeiten (nicht mitgeliefert)

Diese Pakete werden zur Laufzeit von Home Assistant bereitgestellt und **nicht**
in dieses Repository kopiert. Ihre Lizenzen gelten für die Pakete selbst:

| Paket | Zweck | Lizenz |
|---|---|---|
| Home Assistant Core | Host, auf dem die Integration läuft | Apache-2.0 |
| aiohttp | HTTP-Client für die REST-Aufrufe am Ultimate | Apache-2.0 |
| voluptuous | Prüfung der Dienst- und Websocket-Parameter | BSD-3-Clause |
| Python-Standardbibliothek (`lzma`, `hashlib`, `json`, `asyncio`, …) | 7z-Kopf lesen, MD5, Dateien | PSF License |

## 3. Schnittstellen und Formate anderer Projekte

Diese Dinge haben wir **nicht** von anderen übernommen, sondern aus der
Dokumentation und aus dem Verhalten des Geräts selbst ermittelt und
nachgebaut:

- **Ultimate REST API** (`/v1/info`, `/v1/runners:sidplay`, `/v1/drives/…`) –
  dokumentiert in der offiziellen Ultimate-Dokumentation
  (<https://1541u-documentation.readthedocs.io>). Eine API nachzubauen ist keine
  Lizenzfrage; der Quelltext der Firmware wurde nicht verwendet.
- **Songlängen-Übergabe (`.ssl`)** – Format (zwei gepackte BCD-Bytes pro
  Sub-Tune, höchstens 512 Bytes) aus dem Verhalten des SID-Players abgeleitet.
  Bestätigt haben wir es durch die öffentliche Beschreibung des Projekts
  *u64deck* von **zildac** (MIT-Lizenz) – der Code wurde dabei **nicht**
  kopiert.
- **HVSC `Songlengths.md5`** – das Dateiformat der High Voltage SID Collection
  (INI-Stil, MD5 über die ganze Datei). Das Format ist dokumentiert in
  `Songlengths.faq` der HVSC. Der Parser in `songlengths.py` ist eigener Code.

## 4. Daten und Dienste Dritter

- **High Voltage SID Collection (HVSC)** – die SID-Sammlung und ihre
  Songlängen-Datenbank gehören der HVSC und ihren Autoren. UltimateControl
  **lädt** nur `Songlengths.md5` und `HVSC.txt` von den offiziellen Mirrors
  (`hvsc.c64.org`, `hvsc.brona.dk`); es wird nichts davon mitgeliefert oder
  weitergegeben. SID-Dateien selbst stellst du aus deiner eigenen Sammlung
  bereit.
- **Commodore 64, 1541 Ultimate, Ultimate 64** – Marken und Firmware ihrer
  jeweiligen Rechteinhaber. Dieses Projekt steht in keiner Verbindung zu ihnen
  und wird von ihnen nicht unterstützt.

## 5. Wissen und Anregungen

Diese Projekte haben uns beim Verstehen des Geräts geholfen; es wurde **kein
Code** daraus übernommen:

- **u64deck** von zildac (MIT) – Bestätigung, dass der SID-Player eine
  mitgelieferte Längenliste (`.ssl`) liest.
- **ultimate64** von mlund (Apache-2.0) – Rust-Bibliothek, die zeigt, wie
  `sidplay` mit `songnr` aufgerufen wird.
- **c64-pi-jukebox** von sedorrr (GPL-3.0) – Warteschlange und Songlängen-Idee.
  Aus diesem Projekt ist **kein Code** übernommen; es diente nur als Vorbild,
  deshalb zieht seine GPL keine Pflichten für UltimateControl nach sich.
- **Home Assistant** – die Integration folgt den offiziellen
  Entwicklerrichtlinien (`config_flow`, `DataUpdateCoordinator`, `media_source`,
  eigene Lovelace-Ressource).

## 6. Danksagung

Dieses Projekt steht auf den Schultern anderer. Danken möchten wir ausdrücklich:

- **Gideon Zweijtzer** – für die 1541 Ultimate und die Ultimate 64 und für eine
  REST-Schnittstelle, die so gut dokumentiert ist, dass man sie nachbauen kann
  (<https://1541u-documentation.readthedocs.io>). Ohne diese Hardware und diese
  Dokumentation gäbe es UltimateControl nicht.
- **Christian „Peri Fractic“ Simpson** – für die Arbeit am und mit dem C64 und für
  die Hilfsbereitschaft in der Szene.
- **Dem Commodore-Team und der Community** – dafür, dass der C64 seit über
  vierzig Jahren lebt: Hardware, Software, Wissen, Geduld und Freude an einer
  Maschine, die längst fertig war.
- **Der High Voltage SID Collection** (<https://hvsc.c64.org>) – für die
  Songlängen-Datenbank und über 61.000 zusammengetragene SIDs. Ohne diese
  Sammlung wüsste niemand, wann ein Tune zu Ende ist.
- **CSDb** (<https://csdb.dk>) – für das größte Archiv der C64-Szene: Releases,
  Gruppen, Scener und SIDs an einem Ort, durchsuchbar und offen zugänglich.

Danke.

## 7. Eigener Code, eigene Fehler

Der Ablauf der Ordner-Warteschlange mit Timer in Home Assistant, die
Playlists, das Lesen des Haupt-Tunes aus dem SID-Kopf und die Karte sind eigene
Entwicklung. Fehler darin gehen allein zu unseren Lasten.
