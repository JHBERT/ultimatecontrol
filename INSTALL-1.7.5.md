# UltimateControl 1.7.5 – Datenordner heißt jetzt DATA

Der Ordner `config/ultimatecontrol/sids` heißt ab jetzt
`config/ultimatecontrol/DATA`. Er enthält nicht mehr nur SIDs, sondern auch
Disketten-Images, Programme, Cartridges und die aus CSDb geladenen Releases –
der alte Name passte nicht mehr.

## Was sich ändert

| vorher | jetzt |
| --- | --- |
| `config/ultimatecontrol/sids/` | `config/ultimatecontrol/DATA/` |
| `config/ultimatecontrol/sids/csdb/...` | `config/ultimatecontrol/DATA/csdb/...` |
| `config/ultimatecontrol/favorites/` | unverändert |

Betroffen sind Bibliothek, Medienbrowser, Karte, Ordner-Import und der
CSDb-Download; alle lesen den Pfad aus `library.LIBRARY_DIR`.

## Umzug bestehender Daten

Beim Start ruft die Integration `SidLibrary.migrate_dirs()` auf: existiert
`config/ultimatecontrol/sids` und noch kein `DATA`, wird der Ordner einmalig
umbenannt – die Sammlung bleibt also vollständig erhalten. Liegen beide
Ordner vor, gewinnt `DATA` und `sids` bleibt unangetastet liegen (dann bitte
von Hand zusammenführen).

## Tests

172 grün, davon neu in `tests/test_library.py`: der Ordner heißt `DATA`, ein
alter `sids`-Ordner wird umbenannt und ist danach über die Bibliothek
lesbar, und bei beiden Ordnern bleibt `DATA` unverändert.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.7.5.
2. Home Assistant neu starten (dabei läuft der Umzug).
3. Seite hart neu laden (Strg+F5).
