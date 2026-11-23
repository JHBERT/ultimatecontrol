# UltimateControl 0.8.0 – Playlists

## Was neu ist

**＋ Playlist.** Beim laufenden Tune steht jetzt neben ★ Favorit ein Knopf
**＋ Playlist**. Er fragt nach einem Namen (Vorschlag: die zuletzt benutzte
Playlist) und legt den Tune dort ab – Tune-Nummer inklusive. Eine neue Playlist
entsteht dabei automatisch.

**Die Playlist-Ansicht.** Der Reiter **Playlists** in der Kopfzeile zeigt alle
gespeicherten Playlists mit ihrer Anzahl. Eine antippen:

- die Tunes der Playlist, jeder einzeln antippbar (spielt ihn sofort),
- **✕** entfernt einen Eintrag,
- **▶ Playlist abspielen** startet sie als Warteschlange (derselbe Timer wie
  beim Ordner: nach der Länge des Tunes kommt der nächste),
- **🔀** dasselbe in zufälliger Reihenfolge,
- **Playlist löschen**.

**Gespeichert wird nur der Verweis.** Eine Playlist ist eine kleine JSON-Datei
unter `<config>/ultimatecontrol/playlists/<Name>.json` mit Pfad, Quelle und
Tune-Nummer – keine Kopie der SID. Dadurch bleibt sie winzig und folgt der
Bibliothek, wenn dort Dateien umsortiert werden.

## Für dich: aktualisiert sich die Karte bei einem Update?

**Ja, von selbst – bis auf den Browser-Cache.** So läuft es ab:

1. Beim Start der Integration trägt sie ihre Karte als Dashboard-Ressource ein
   und **aktualisiert dabei auch die Versionsnummer in der URL**
   (`...?version=0.8.0`). Diese Nummer ist der Cache-Schlüssel des Browsers:
   neue Nummer → neue Datei.
2. Die Karte selbst wird mit `Cache-Control: no-cache` ausgeliefert, wird also
   bei jedem Dashboard-Laden neu geprüft.
3. **Was du tun musst:** nach dem HACS-Update und dem HA-Neustart die Seite
   **einmal hart neu laden** (Strg+F5), damit das Dashboard die geänderte
   Ressourcen-URL mitbekommt. Danach ist alles beim Alten – bis zum nächsten
   Update.

Nur wenn du Lovelace im **YAML-Modus** fährst, schreibt die Integration nichts
in die Ressourcen; dann steht die URL in deiner `configuration.yaml` und du
musst dort die Versionsnummer selbst hochziehen (das Log nennt die passende
URL beim Start).

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 0.8.0.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).

## Technisch

Neu `playlist.py` (PlaylistStore: list/load/save/delete/add/remove_entry/clear,
atomar geschrieben, Namen entschärft) und fünf Websocket-Befehle:
`playlists`, `playlist_get`, `playlist_add`, `playlist_edit`, `playlist_play`.
`browse` kennt jetzt `file: true` und meldet einen einzelnen Tune auch aus
Unterordnern (für „＋ Playlist“ beim laufenden Tune). 22 neue Tests,
insgesamt **112 grün**.
