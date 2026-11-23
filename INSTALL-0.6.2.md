# UltimateControl 0.6.2 – Songlänge kommt jetzt beim C64 an

## Was falsch war

Die Songlängen-Datenbank war geladen und die Karte hat die richtigen Längen
angezeigt – der C64 hat aber weiter 5 Minuten gespielt. Grund: der SID-Player im
Ultimate kennt eine Länge nur, wenn sie **zusammen mit der Datei** hochgeladen
wird. Wir haben nur die SID geschickt, also hat das Gerät seine Voreinstellung
(5 Minuten) genommen.

## Was jetzt passiert

Beim Abspielen schickt die Integration zwei Teile in einem Upload an
`POST /v1/runners:sidplay`:

1. die SID-Datei,
2. eine kleine Längenliste (`tune.ssl`) mit **zwei Bytes pro Sub-Tune**:
   Minuten und Sekunden, je als gepackte Dezimalzahl (BCD). Ein Tune von 5:17
   wird zu `05 17`. Das Gerät liest höchstens 512 Bytes (256 Sub-Tunes);
   Sub-Tunes ohne bekannte Länge bleiben `00 00`, dort gilt weiter die
   Geräte-Voreinstellung.

Damit zeigt der SID-Player im Ultimate die dokumentierte Länge an und stoppt am
Ende selbst. Die Home-Assistant-Entität beendet ihren Wiedergabe-Zustand
zusätzlich nach derselben Zeit.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 0.6.2.
2. Home Assistant neu starten.
3. Browser **hart neu laden** (Strg+F5).

## Ausprobieren

Einen Tune aus der Bibliothek starten und am Ultimate auf den SID-Player
schauen: bei „Länge“ muss jetzt die HVSC-Zeit stehen (z. B. `5:17`), nicht mehr
`5:00`. Bleibt es bei 5:00, dann ist für genau diese Datei keine Länge in
`Songlengths.md5` – die Zuordnung läuft über die MD5 der ganzen Datei, eine
anders bearbeitete Kopie hat eine andere MD5.
