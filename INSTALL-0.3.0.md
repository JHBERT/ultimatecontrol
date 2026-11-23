# UltimateControl 0.3.0 – Medienbrowser repariert

## Was der Fehler war
Die REST-API der Firmware 3.14 kann **kein Verzeichnis auflisten**:

- `GET /v1/files/` → 404 (das war dein Fehler)
- `GET /v1/files/<ordner>:info` → nur ein einzelner Stat
- Wildcard-Stat `GET /v1/files/<ordner>/*:info` → nur **der erste** Treffer
- Auf dem Ultimate II+ sieht das blanke `*` nicht einmal die obersten Ordner
  (nur `Flash` und `Temp` existieren dort; `C64`, `Usb0`, `Sd` gibt es nicht)

Deshalb liefert die Integration die Ordnerliste jetzt über den **FTP-Server des
Geräts** (`NLST`, read-only) und fragt per REST, ob ein Name ein Ordner ist.
Das läuft gegen dein Gerät 192.168.178.63 nachweislich:

```
/            -> dir Flash, dir Temp
/Flash       -> dir carts, dir html, dir roms
/Flash/roms  -> 6 Dateien
```

## Zweites Problem: nur ein Gerät
Der Medienbrowser hat immer nur das **erste** konfigurierte Gerät genommen.
Jetzt:

- Bei mehreren Geräten zeigt der Browser zuerst die **Geräteliste** (Ultimate 2
  Cartridge / C64 Ultimate) – du wählst aus.
- Die Medien-ID enthält das Gerät, der Player entfernt es wieder.

## Installation
1. ZIP entpacken, Inhalt nach `config/custom_components/ultimatecontrol/`
   (Ordner ersetzen – neu dabei ist `ftp.py`).
2. Home Assistant neu starten.
3. Integration ist bereits eingerichtet – keine Änderung nötig.

## Testen
- **Medien → Ultimate C64** öffnen: du siehst beide Geräte.
- Gerät wählen → Ordner wählen → SID antippen.
- Firmware-/Textdateien werden ausgeblendet; PRG/CRT/D64 erscheinen nur in
  Ordnern, die sonst leer wären (gestartet werden sie über die
  `media_player`-Entity).

## Voraussetzungen am Gerät
- **FTP muss im Ultimate-Menü aktiviert sein** (Standard: an).
- Netzwerk-Passwort, falls gesetzt, nutzt die Integration auch für FTP.
- Ist FTP aus, fällt der Browser auf die Wildcard-Methode zurück (unvollständig,
  aber besser als nichts).
