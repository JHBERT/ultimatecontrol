# UltimateControl 1.7.2 – CSDb-Download robuster

Fehler in 1.7.1: Beim Download etwa von <https://csdb.dk/release/?id=82> stand
auf der Karte „File is not a zip file".

Ursache: Ein Release hat oft **mehrere** Download-Links, und der erste zeigt
nicht selten auf einen anderen Server. Antwortet der mit einer HTML-Seite
statt mit dem Archiv, warf das Entpacken genau diesen Fehler – ohne zu sagen,
welcher Link gemeint war und was tatsächlich kam.

Jetzt gilt:

- Jeder Link wird der Reihe nach versucht, der gewählte zuerst. Der erste, der
  wirklich mit `PK` beginnt, wird genommen.
- Der Dateiname kommt aus `Content-Disposition`, damit im Ordner
  `sids/csdb/<ID>/` der richtige Name liegt (`piece_of_cake_1.zip` statt
  `download.php?id=1368`).
- Scheitern alle Links, nennt die Meldung jeden Link und was er geliefert hat,
  zum Beispiel: `No download answered with a ZIP archive – download.php?id=1368:
  HTML instead of a ZIP (text/html): <!DOCTYPE html>…`.
- Die Karte zeigt nach dem Entpacken den Archvnamen und die Zahl der Dateien;
  findet sich keine Diskette, kein Programm und kein SID, sagt sie das.

## Installation über HACS

1. HACS → UltimateControl → **Update** auf 1.7.2.
2. Home Assistant neu starten.
3. Seite hart neu laden (Strg+F5).
