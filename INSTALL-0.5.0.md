# UltimateControl 0.5.0 – Geräteauswahl & Ordner-Import

## 1. Update
HACS → UltimateControl C64 → **Update auf 0.5.0** → Home Assistant neu starten.
Die Ressourcen-URL stellt die Integration selbst auf `?version=0.5.0` um;
danach einmal **Strg+F5** im Browser.

## 2. Gerät in der Karte wählen
Karte → Stift (Bearbeiten) → im Dialog:

- **Gerät**: Dropdown mit allen eingerichteten Ultimates
  („Automatisch“ = erstes Gerät). Bei dir: *Ultimate 2 Cartridge*
  (192.168.178.63) und *C64 Ultimate* (192.168.178.97, sobald erreichbar).
- **Titel**: frei wählbar.

In YAML bleibt `entry_id` optional – die Karte sucht das Gerät sonst selbst.

## 3. SIDs importieren
In der Karte auf **＋** (neben HVSC / ★ Favoriten):

1. Der Ordner-Browser startet bei den üblichen Orten (`/config`, `/share`,
   `/media`, …).
2. Ordner antippen, mit **↑** nach oben.
3. Unten steht, wie viele SID-Dateien im Ordner liegen (Unterordner zählen mit).
4. **Diesen Ordner importieren** – die Dateien landen in
   `config/ultimatecontrol/sids/`, die Karte springt auf die HVSC-Liste.

Derselbe Vorgang per Service: `ultimatecontrol.import_folder`
(`folder`, optional `subfolder`, `overwrite`).

## Was geprüft ist
- Card-Datei: `node --check` grün und mit nachgebautem `customElements`/`window`
  ausgeführt → `ultimatecontrol-panel-editor` und `ultimatecontrol-panel`
  werden definiert.
- Release-ZIP v0.5.0: `version` 0.5.0, Card-URL `?version=0.5.0`, Editor,
  Import-Knopf und `host_folders` enthalten.
- 34 Tests grün (`pytest -q`), davon 3 neue für die Ordnerliste
  (Wurzeln, Unterordner + SID-Zählung, fehlender Ordner).

## Was nicht geprüft ist
Der Klickweg in deiner HA-Instanz (kein Zugang) – insbesondere, ob der
Ordner-Browser bei dir `/config` findet. Steht dort kein passender Ort, tippe
den Pfad direkt in den Service `ultimatecontrol.import_folder`.
