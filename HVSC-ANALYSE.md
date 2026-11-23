# HVSC – was geprüft ist (Stand 23.11.2026)

## Quellen

| Was | Adresse | Größe |
|---|---|---|
| Vollpaket Release 85 | `https://hvsc.brona.dk/HVSC/HVSC_85-all-of-them.7z` | 81 MB → entpackt **61.157 SIDs** |
| Update 85 | `https://hvsc.brona.dk/HVSC/HVSC_Update_85.7z` | 3,4 MB → 630 SIDs + Skript |
| Songlängen | `https://hvsc.brona.dk/HVSC/C64Music/DOCUMENTS/Songlengths.md5` | 5,2 MB, 61.157 Einträge |
| Versionsangabe | `.../C64Music/DOCUMENTS/HVSC.txt` | „Release 85“, 57 KB |

Ein ZIP gibt es im offiziellen Mirror **nicht** – nur `.7z` und `.rar`.

## Songlängen (Punkt 3) – funktioniert

Der Parser liest die echte Datei in **0,22 s**, 61.157 Einträge, Mehrtune-Längen
korrekt (`5th_Demo`: 5:17 / 1:00 / 0:42). Zuordnung über die **MD5 der Datei** –
greift damit für Bibliothek **und** Favoriten, unabhängig vom Dateinamen.

Fehlt bei dir nur die Datei: `config/ultimatecontrol/Songlengths.md5`.

## Update-Skript – gelesen und verstanden

`update/Update85.hvs` ist Text. Erste Zeilen:

```
# Resulting Version: 85
#  Previous Version: 84
```

Damit ist die Kette **83 → 84 → 85** sauber planbar (Lücken-Check vor dem
ersten Download, Merkzettel pro Schritt, Sicherung vorher).

Anweisungen im Skript (Update 85):

| Direktive | Anzahl | Bedeutung |
|---|---|---|
| `REPLACE` | 45 | Datei aus `update/fix/…` über die Sammlung kopieren |
| `MOVE` | 290 | 587 neue SIDs aus `update/new/…` + 9 Umbenennungen |
| `DELETE` | 271 | Dateien und ganze Ordner löschen |
| `TITLE`, `SONGS`, `CLOCK`, … | 13 Blöcke | **übersprungen** (ändern Bytes im SID – fürs Abspielen egal) |

Der Python-Parser dafür steht (`hvsc.py`, getestet gegen das echte Skript).

## Der Haken: 7z mit BCJ2

HVSC packt mit dem BCJ2-Filter. Python kann ihn **nicht** entpacken
(`lzma` hat keinen BCJ2-Filter), py7zr 1.1.4 ebenso wenig.

- **Vollpaket:** von den 61.326 Dateien liegen fast alle in einem BCJ2-Stream.
  `bsdtar`/libarchive kann es – auf einem Windows-PC in **5:26 min** entpackt,
  61.157 SIDs geprüft. In Home Assistant (HAOS-Container) gibt es `bsdtar` nicht.
- **Update-Archiv:** 632 der 649 Einträge (alle SIDs + das `.hvs`) liegen im
  BCJ2-Stream. Nur 15 Dokumente sind unkomprimiert lesbar.

## Konsequenz für 0.6.0

1. **Songlängen automatisch laden** – sofort machbar, größter Effekt.
2. **Update-Hinweis** (Release aus `HVSC.txt`) – machbar.
3. **Vollimport** – braucht einen BCJ2-Entpacker. Zwei Wege:
   - **a)** BCJ2 in Python nachbauen (~100 Zeilen, Kontrollstrom + 3 Adressströme).
     Muss gegen die echten 81 MB getestet werden, sonst Risiko kaputter Sammlung.
   - **b)** Nur die **unkomprimierten** Teile nutzen: `Songlengths.md5`,
     `HVSC.txt`, `STIL.txt` liegen im Copy-Stream und sind ohne BCJ2 lesbar.
4. **Update anwenden** – geht erst, wenn das `.hvs` lesbar ist (BCJ2) → hängt an 3a.
