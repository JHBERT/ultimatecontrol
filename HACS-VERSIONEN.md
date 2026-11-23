# Versionen: was GitHub/HACS anzeigt und was 0.4.1 ändert

## Warum da eine „kryptische Nummer" steht
HACS nimmt die Version **aus `custom_components/ultimatecontrol/manifest.json`**,
nicht aus dem Tag und nicht aus dem Release-Namen. Dein HA zeigt 0.4.0 – also
lag dort `0.4.0` im installierten Code. Die kryptische Nummer daneben ist der
**Commit-Hash** (`3b90185…`): HACS sieht in dem, was es installiert hat, keine
Version, die es einem Release zuordnen kann, und zeigt dann den Commit.

Ursache: im Repo gab es **keinen Release**, nur einen Tag `v0.4.1`. Ein Tag
allein reicht HACS nicht – es sucht ein GitHub-Release mit dem Tag.

## Was jetzt richtig ist
| Sache | Stand |
| --- | --- |
| `manifest.json` auf `main` | `"version": "0.4.1"` |
| Git-Tag | `v0.4.1` → Commit `c248476` |
| GitHub-**Release** | **v0.4.1** (kein Draft, kein Pre-Release) |
| Release-Notes | im Release-Text |

Ab jetzt liefert HACS eine **echte Versionsnummer** statt des Commit-Hash.

## So holst du es
1. HACS → UltimateControl C64 → ⋮ → **Update information** (Reload).
2. Update auf 0.4.1 – oder ⋮ → **Redownload** → Version `v0.4.1`.
3. Home Assistant neu starten.
4. Dashboard-Ressource eintragen:
   `/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.1`,
   Typ **JavaScript-Modul**.

## Damit das in Zukunft sauber bleibt
Bei jeder Änderung, die du installieren willst:
1. `manifest.json` → neue Version (`0.4.2`, `0.5.0`, …)
2. commit + push
3. Tag `v<dieselbe Version>` setzen und pushen
4. GitHub-Release mit genau diesem Tag anlegen

Nur wenn **alle vier** dieselbe Nummer tragen, zeigt HACS die Version an, bietet
das Update an und kann es sauber installieren.
