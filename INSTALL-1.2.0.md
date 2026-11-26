# UltimateControl 1.2.0 – ein Gerät wählen, eine Karte

- Mit mehreren Geräten zeigt die Karte im Kopf ein **Dropdown** (z. B. Ultimate II+ / C64U) statt des festen Titels. Eine zweite Karte ist nicht mehr nötig.
- Beim Wechsel lädt die Karte Ordner, Queue, Playlists, laufenden Tune und Songlängen-Status des gewählten Geräts neu. Die Wahl bleibt im Browser gespeichert.
- Queue-Ereignisse anderer Geräte werden ignoriert (das Ereignis trägt jetzt `entry_id`).
- Karten mit fester `entry_id` bleiben unverändert; `device_picker: true|false` erzwingt/versteckt das Dropdown.
- Bestehende Dashboards: zweite Karte entfernen, bei der ersten die `entry_id` weglassen.

## Installation über HACS
HACS → Update auf 1.2.0, HA neu starten, Strg+F5.
