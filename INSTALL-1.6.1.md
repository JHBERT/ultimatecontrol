# UltimateControl 1.6.1 – kein Sprung mehr in der Dateiliste

Beim Starten eines Tunes sprang die Liste nach oben, weil die Karte bei jedem
Klick komplett neu aufgebaut wurde. Jetzt wird nur noch die betroffene Zeile
markiert:

- **Einzelner Tune:** die Zeile bekommt „lädt" und danach „läuft" – ohne
  Neuaufbau, die Scrollposition bleibt exakt stehen.
- **Tune mit Untertunes:** die aufgeklappte Tune-Liste wird weiterhin neu
  gezeichnet (der laufende Tune soll grün sein), aber die Karte merkt sich die
  Position der Liste **und** der Seite und stellt beides wieder her; der
  laufende Tune wird nur dann ins Bild geholt, wenn er außer Sicht ist.
- **Disketten und Programme:** gleiches Verhalten.
- **Import-Dialog:** hält seine Position ebenfalls.

Gilt für die SID-Auswahl und die Demo-Auswahl, weil beide dieselbe Liste
benutzen.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.6.1.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
