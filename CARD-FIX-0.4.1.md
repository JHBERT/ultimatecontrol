# „Custom element doesn't exist" – was wirklich los war (0.4.1)

## Was ich geändert hatte und warum es nicht half
In 0.4.0 habe ich die Card über eine eigene View der Integration ausgeliefert
(`/ultimatecontrol_panel/ultimatecontrol-panel.js`, `requires_auth = True`).
Bei dir kann die Datei deshalb gar nicht geladen werden – also wird das Element
nie definiert, und Lovelace sagt „Custom element doesn't exist“. Meine Anleitung
(Schritt 2) war zusätzlich falsch, weil sie dich die Ressource eintragen ließ,
ohne dass die Integration sie selbst mitregistriert.

## Woran es liegt (zwei Ursachen)
1. **Die URL lag hinter dem Login.** Home Assistant lädt eine Dashboard-Ressource
   als `<script type="module">`. Der Modul-Lader des Browsers schickt dabei keine
   Auth-Header; ein 401 lässt das Modul still scheitern → Element fehlt.
   (Dass dieselbe Datei im Browser-Direktaufruf 200 liefert, hat mich in die Irre
   geführt: dort gibt es ein Cookie, im Modul-Loader nicht.)
2. **`entry_id: 415204` ist nicht die Config-Entry-ID**, sondern die
   `unique_id` des Geräts (die Firmware-Nummer). Damit wäre die Card auch nach
   dem Laden mit „unknown_entry" stehen geblieben.

## Was 0.4.1 macht
- Die Card wird **ohne Auth** ausgeliefert (Code, keine Daten; jeder Aufruf, den
  die Card macht, ist authentifiziert).
- Die Card **sucht ihr Gerät selbst**: neuer Befehl `ultimatecontrol/devices`.
  Sie akzeptiert die Config-Entry-ID, die `unique_id` (`415204`), Teile des
  Namens – oder nimmt das einzige eingerichtete Gerät. Passt nichts, zeigt sie
  die echten IDs an, statt nur „unknown_entry".

## Einbau
1. ZIP-Inhalt nach `config/custom_components/ultimatecontrol/` (ersetzen),
   Home Assistant neu starten.
2. Ressource: Einstellungen → Dashboards → ⋮ → Ressourcen →
   `/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.1`
   Typ **JavaScript-Modul**. (Die Integration registriert sie nicht selbst –
   das ist der eine Schritt, den nur du machen kannst.)
3. Karte:

```yaml
type: custom:ultimatecontrol-panel
entry_id: 415204          # oder ganz weglassen
title: Ultimate 2 Cartridge
```

Beides ist jetzt gültig: die `unique_id` (`415204`) wird erkannt, und ohne
`entry_id` nimmt die Card das einzige Gerät.

## Woran du merkst, dass es geklappt hat
- Beim Laden der Datei
  `http://homeassistant.local:8123/ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.4.1`
  in einem **privaten Fenster ohne Login** kommt JavaScript (kein Login-Dialog,
  keine 401).
- Die Karte erscheint mit den Reitern „HVSC" und „★ Favoriten".
- Kommt stattdessen eine Meldung mit „IDs:" – dort steht die richtige ID für
  `entry_id`.
