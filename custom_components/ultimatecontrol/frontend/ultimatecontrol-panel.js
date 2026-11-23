/**
 * UltimateControl – SID-Auswahl für das Dashboard.
 *
 * Die Integration liefert diese Datei unter
 *   /ultimatecontrol_panel/ultimatecontrol-panel.js
 * aus; als Dashboard-Ressource (Typ: JavaScript-Modul) eintragen:
 *   /ultimatecontrol_panel/ultimatecontrol-panel.js?version=0.9.0
 *
 * type: custom:ultimatecontrol-panel
 * entry_id: <ID des Geräts>          (Einstellungen → Geräte → Ultimate)
 * title: Ultimate 2 Cartridge        (optional)
 */
const DOMAIN = "ultimatecontrol";

/* ------------------------------------------------------------------
 * Konfigurations-Dialog der Karte
 * ------------------------------------------------------------------
 * Ohne Editor kann eine Karte in der Oberfläche nur als YAML eingefügt
 * werden. Mit `getConfigElement` bekommt sie ein Formular mit einem
 * Geräte-Dropdown, damit man bei mehreren Ultimates das richtige wählt.
 */
class UltimateControlPanelEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._loadDevices();
  }

  async _loadDevices() {
    try {
      this._devices = await this._hass.connection.sendMessagePromise({
        type: `${DOMAIN}/devices`,
      });
    } catch (err) {
      this._devices = [];
      this._deviceError = err.message || String(err);
    }
    this._render();
  }

  _fire() {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _set(key, value) {
    this._config = { ...this._config, [key]: value };
    if (!value) delete this._config[key];
    this._fire();
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const cfg = this._config || {};
    const devices = this._devices || [];
    const options = devices
      .map((device) => {
        const label = `${device.title || device.entry_id}${
          device.host ? ` (${device.host})` : ""
        }`;
        const selected =
          device.entry_id === cfg.entry_id ||
          String(device.unique_id || "") === String(cfg.entry_id || "") ||
          (!cfg.entry_id && devices.length === 1);
        return `<option value="${this._esc(device.entry_id)}" ${
          selected ? "selected" : ""
        }>${this._esc(label)}</option>`;
      })
      .join("");

    this.shadowRoot.innerHTML = `
      <style>
        .form { display:flex; flex-direction:column; gap:12px; padding:4px 2px 8px; }
        label { font-size:.85rem; color: var(--secondary-text-color,#999); display:block; margin-bottom:4px; }
        select, input {
          width:100%; box-sizing:border-box; font:inherit; padding:8px 10px; border-radius:8px;
          border:1px solid var(--divider-color,#444); background: var(--card-background-color,#1c1c1c);
          color: var(--primary-text-color,#eee);
        }
        .hint { font-size:.78rem; color: var(--secondary-text-color,#888); }
      </style>
      <div class="form">
        <div>
          <label for="device">Gerät</label>
          <select id="device">
            <option value="">Automatisch (erstes Gerät)</option>
            ${options}
          </select>
          <div class="hint">${
            devices.length
              ? `${devices.length} Gerät(e) eingerichtet.`
              : this._deviceError || "Noch keine Geräte gefunden."
          }</div>
        </div>
        <div>
          <label for="title">Titel</label>
          <input id="title" type="text" value="${this._esc(cfg.title || "SID-Auswahl")}" />
        </div>
      </div>`;

    this.shadowRoot.querySelector("#device").addEventListener("change", (event) =>
      this._set("entry_id", event.target.value)
    );
    this.shadowRoot.querySelector("#title").addEventListener("change", (event) =>
      this._set("title", event.target.value)
    );
  }

  _esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }
}

customElements.define("ultimatecontrol-panel-editor", UltimateControlPanelEditor);

class UltimateControlPanel extends HTMLElement {
  setConfig(config) {
    // entry_id darf fehlen: die Card sucht sich das Gerät dann selbst.
    this._config = { source: "library", path: "", title: "SID-Auswahl", ...config };
    this._hass = null;
    this._view = { source: this._config.source, path: this._config.path };
    this._entries = [];
    this._error = null;
    this._current = {};
    this._lastDir = {};
    // Ordner-Warteschlange: was läuft, was kommt als Nächstes.
    this._queue = { count: 0, index: -1, playing: false, items: [] };
    // Gespeicherte Playlists und die gerade geöffnete.
    this._playlists = [];
    this._playlist = null;
    this._playlistView = false;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // Nur eine echte Home-Assistant-Verbindung hat `states`; die Demo-Attrappe
    // reicht ein Objekt ohne, damit die Vorschau ohne HA funktioniert.
    this._live = !!(hass && hass.states && hass.connection);
    if (first) {
      this._firstLoad();
      // Die Integration meldet jeden Wechsel der Warteschlange; damit zieht
      // die Karte auch nach, wenn sie zwischenzeitlich geschlossen war.
      if (this._live && hass.connection && hass.connection.subscribeEvents) {
        hass.connection
          .subscribeEvents((event) => {
            const state = event && event.data ? event.data : null;
            if (!state) return;
            this._queue = state;
            this._queueTick();
            this._render();
          }, `${DOMAIN}_queue_changed`)
          .catch(() => {});
      }
    }
  }

  getCardSize() {
    return 8;
  }

  /* Der Konfigurations-Dialog der Karte (Geräte-Dropdown + Titel). */
  static getConfigElement() {
    return document.createElement("ultimatecontrol-panel-editor");
  }

  /* Vorschlag, wenn die Karte über „Karte hinzufügen“ eingefügt wird. */
  static getStubConfig(hass) {
    return { title: "SID-Auswahl" };
  }

  /* -------------------------------------------------- Laden */
  async _firstLoad() {
    if (this._live) {
      await this._resolveDevice();
    }
    if (this._resolveError) {
      this._render();
      return;
    }
    await this._load();
    await this._refreshCurrent();
    await this._queueStatus();
    // Läuft noch eine Warteschlange (Seite war zu), gleich den Tune setzen.
    this._queueTick();
    await this._playlistsLoad();
    await this._hvscStatus(false);
  }

  /* -------------------------------------------------- Warteschlange */
  /* Restzeit aus der Endzeit rechnen (die Seite kann zwischenzeitlich zu sein). */
  _queueRemaining() {
    const q = this._queue || {};
    if (!q.playing || !q.ends_at) return null;
    return Math.max(0, q.ends_at - Date.now() / 1000);
  }

  _queueTick() {
    const left = this._queueRemaining();
    if (left === null) {
      if (this._queueTimer) {
        clearInterval(this._queueTimer);
        this._queueTimer = null;
      }
      return;
    }
    // Einmal pro Sekunde die Leiste nachziehen, ohne die ganze Karte neu zu bauen.
    if (!this._queueTimer) {
      this._queueTimer = setInterval(() => {
        const rest = this._queueRemaining();
        const el = this.shadowRoot && this.shadowRoot.querySelector("#qLeft");
        if (el && rest !== null) el.textContent = `noch ${this._fmtLength(rest)}`;
        if (rest === null || rest <= 0) {
          clearInterval(this._queueTimer);
          this._queueTimer = null;
          // Tune ist zu Ende: Zustand neu holen (die Integration schaltet weiter).
          this._queueStatus();
        }
      }, 1000);
    }
  }

  async _queueStatus() {
    if (!this._live) return;
    try {
      this._queue = await this._ws("queue_status");
    } catch (err) {
      this._queue = { count: 0, index: -1, playing: false, items: [] };
    // Gespeicherte Playlists und die gerade geöffnete.
    this._playlists = [];
    this._playlist = null;
    this._playlistView = false;
    }
    this._render();
  }

  /* Ganzen Ordner abspielen: HA schickt Tune für Tune und timert dazwischen. */
  async _playFolder(shuffle) {
    if (this._folderBusy) return;
    this._folderBusy = true;
    this._error = null;
    this._flash = null;
    this._render();
    try {
      this._queue = await this._ws("queue_play_folder", {
        source: this._view.source,
        path: this._view.path,
        shuffle: !!shuffle,
      });
      const count = this._queue.count || 0;
      this._flash = `${count} Tune(s) in der Warteschlange`;
      await this._refreshCurrent();
    } catch (err) {
      this._error = err.message || String(err);
    } finally {
      this._folderBusy = false;
      this._render();
    }
  }

  async _queueAction(action) {
    if (this._queueBusy) return;
    this._queueBusy = true;
    this._error = null;
    this._render();
    try {
      this._queue = await this._ws("queue_action", { action });
      if (action === "next" || action === "previous" || action === "resume") {
        await this._refreshCurrent();
      }
    } catch (err) {
      this._error = err.message || String(err);
    } finally {
      this._queueBusy = false;
      this._render();
    }
  }

  /* Songlängen und HVSC-Version holen; refresh=true fragt den Mirror. */
  async _hvscStatus(refresh) {
    if (!this._live) return;
    try {
      this._hvsc = await this._ws("hvsc_status", { refresh: !!refresh });
    } catch (err) {
      this._hvsc = { error: err.message || String(err) };
    }
    this._render();
  }

  async _hvscDownload() {
    if (this._hvscBusy) return;
    this._hvscBusy = true;
    this._flash = null;
    this._error = null;
    this._render();
    try {
      const result = await this._ws("hvsc_download_songlengths");
      this._flash =
        `Songlängen geladen: ${result.entries} SIDs` +
        (result.bytes ? ` (${Math.round(result.bytes / 1024)} KB)` : "");
      await this._load();
      await this._hvscStatus(false);
    } catch (err) {
      this._error = err.message || String(err);
    } finally {
      this._hvscBusy = false;
      this._render();
    }
  }

  /* Sucht das Gerät, wenn 'entry_id' fehlt oder nicht (mehr) stimmt.
     Akzeptiert auch die unique_id des Geräts (z. B. 415204). */
  async _resolveDevice() {
    try {
      const devices = await this._hass.connection.sendMessagePromise({
        type: `${DOMAIN}/devices`,
      });
      if (!devices.length) {
        this._resolveError =
          "Kein UltimateControl-Gerät eingerichtet (Einstellungen → Geräte & Dienste).";
        return;
      }
      const wanted = String(this._config.entry_id || "").trim();
      const match =
        devices.find((d) => d.entry_id === wanted) ||
        devices.find((d) => String(d.unique_id || "") === wanted) ||
        devices.find((d) => String(d.info?.unique_id || "") === wanted) ||
        devices.find((d) =>
          String(d.title || "").toLowerCase().includes(wanted.toLowerCase())
        );
      if (match) {
        this._entryId = match.entry_id;
      } else if (!wanted) {
        this._entryId = devices[0].entry_id;
      } else {
        this._resolveError =
          `Gerät "${wanted}" nicht gefunden. IDs: ` +
          devices
            .map((d) => `${d.title} → ${d.entry_id}`)
            .join(" · ");
      }
    } catch (err) {
      this._resolveError = err.message || String(err);
    }
  }

  async _ws(type, payload = {}) {
    return this._hass.connection.sendMessagePromise({
      type: `${DOMAIN}/${type}`,
      entry_id: this._entryId || this._config.entry_id,
      ...payload,
    });
  }

  async _load() {
    this._error = null;
    this._render();
    try {
      const result = await this._ws("browse", {
        source: this._view.source,
        path: this._view.path,
      });
      this._entries = result.entries || [];
      this._lastDir[`${this._view.source}:${this._view.path}`] = this._entries;
    } catch (err) {
      this._error = err.message || String(err);
      this._entries = [];
    }
    this._render();
  }

  async _refreshCurrent() {
    try {
      this._current = await this._ws("current");
    } catch (err) {
      this._current = {};
    }
    this._render();
  }

  /* -------------------------------------------------- Aktionen */
  async _open(entry) {
    if (entry.is_dir) {
      this._view = {
        source: this._view.source,
        path: this._view.path ? `${this._view.path}/${entry.name}` : entry.name,
      };
      this._load();
      return;
    }
    // SID mit mehreren Tunes: Tune-Auswahl aufklappen, sonst direkt spielen.
    if (entry.songs > 1) {
      const key = `${this._view.path}/${entry.name}`;
      this._openTunes = this._openTunes === key ? null : key;
      if (this._openTunes === key) {
        try {
          this._detail = await this._ws("inspect", {
            source: this._view.source,
            path: key,
          });
        } catch (err) {
          this._error = err.message || String(err);
        }
      }
      this._render();
      return;
    }
    this._play(entry.name, 1);
  }

  async _play(name, song, source, fullPath) {
    const path = fullPath || (this._view.path ? `${this._view.path}/${name}` : name);
    this._playing = path;
    this._render();
    try {
      this._current = await this._ws("play", {
        source: source || this._view.source,
        path,
        song,
      });
      this._error = null;
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._playing = null;
    // Läuft ein Tune, die aufgeklappte Tune-Liste neu holen, damit der
    // laufende Tune grün markiert ist.
    if (this._openTunes) {
      try {
        this._detail = await this._ws("inspect", {
          source: this._view.source,
          path: this._openTunes,
        });
      } catch (err) {
        /* Die Liste bleibt dann eben ohne Markierung. */
      }
    }
    this._render();
  }

  async _favorite() {
    const cur = this._current || {};
    if (!cur.path || cur.source === "device") {
      return;
    }
    try {
      await this._ws("favorite_add", { path: cur.path });
      this._flash = `${cur.name} liegt jetzt in den Favoriten`;
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  async _unfavorite() {
    const cur = this._current || {};
    if (!cur.path || cur.source !== "favorites") return;
    try {
      await this._ws("favorite_remove", { path: cur.path });
      this._flash = `${cur.name} ist nicht mehr in den Favoriten`;
      this._current = {};
      await this._load();
      return;
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  /* Zeile am Kartenende: Songlängen-Status und HVSC-Version. */
  _hvscBar() {
    if (!this._live || !this._hvsc) return "";
    const st = this._hvsc;
    const count = st.songlengths || 0;
    const parts = [];
    if (count) {
      parts.push(`Songlängen: <strong>${count}</strong> SIDs`);
    } else {
      parts.push(`<span class="warn">Keine Songlängen – jede Melodie spielt 5 Minuten.</span>`);
    }
    if (st.local) parts.push(`HVSC ${st.local}`);
    if (st.remote && st.update_available) {
      parts.push(`<span class="warn">Update ${st.remote} verfügbar</span>`);
    } else if (st.remote && st.local) {
      parts.push(`aktuell`);
    }
    return `<div class="hvsc">
      <span class="grow">${parts.join(" · ")}</span>
      ${
        count
          ? ""
          : `<button class="primary" id="hvscGet" ${this._hvscBusy ? "disabled" : ""}>
               ${this._hvscBusy ? "lädt …" : "Songlängen laden"}
             </button>`
      }
      <button id="hvscCheck" title="Beim HVSC-Mirror nach einer neuen Version fragen">Prüfen</button>
    </div>`;
  }

  _up() {
    const parts = (this._view.path || "").split("/").filter(Boolean);
    parts.pop();
    this._view = { source: this._view.source, path: parts.join("/") };
    this._load();
  }

  _switch(source) {
    this._view = { source, path: "" };
    this._openTunes = null;
    this._load();
  }

  /* -------------------------------------------------- Import */
  async _openImport() {
    this._import = { path: "", parent: null, entries: [], sidCount: null, busy: false };
    this._render();
    await this._importGo("");
  }

  async _importGo(path) {
    if (!this._import) return;
    this._import.busy = true;
    this._render();
    try {
      const result = await this._ws("host_folders", path ? { path } : {});
      this._import = {
        path: result.path,
        parent: result.parent,
        entries: result.entries || [],
        sidCount: result.sid_count,
        busy: false,
      };
      this._error = null;
    } catch (err) {
      this._import.busy = false;
      this._error = err.message || String(err);
    }
    this._render();
  }

  async _importRun() {
    if (!this._import || !this._import.path) return;
    this._import.busy = true;
    this._render();
    try {
      const result = await this._ws("import", { folder: this._import.path });
      this._flash = `${result.imported} SID-Datei(en) importiert`;
      if (result.skipped && result.skipped.length) {
        this._error = `${result.skipped.length} übersprungen: ${result.skipped[0]}`;
      }
      this._import = null;
      this._view = { source: "library", path: "" };
      await this._load();
      return;
    } catch (err) {
      this._error = err.message || String(err);
    }
    if (this._import) this._import.busy = false;
    this._render();
  }

  _importClose() {
    this._import = null;
    this._render();
  }

  /* -------------------------------------------------- Playlists */
  async _playlistsLoad() {
    if (!this._live) return;
    try {
      const result = await this._ws("playlists");
      this._playlists = result.playlists || [];
    } catch (err) {
      this._playlists = [];
    }
    this._render();
  }

  /* Den laufenden Tune in eine Playlist legen (Name wird abgefragt). */
  async _addToPlaylist() {
    const cur = this._current || {};
    if (!cur.path) {
      this._error = "Es läuft gerade kein Tune aus der Bibliothek.";
      this._render();
      return;
    }
    let name = "";
    try {
      name = window.prompt(
        "In welche Playlist? (neuer Name legt sie an)",
        (this._playlists[0] && this._playlists[0].name) || "Meine Playlist"
      ) || "";
    } catch (err) {
      name = "";
    }
    if (!name.trim()) return;
    try {
      // Der laufende Tune kann tiefer liegen als der offene Ordner, deshalb
      // über die Bibliothek suchen lassen.
      const found = await this._ws("browse", {
        source: cur.source || "library",
        path: cur.path,
        file: true,
      });
      const file = found.file || {};
      const result = await this._ws("playlist_add", {
        name: name.trim(),
        source: cur.source || "library",
        path: cur.path,
        song: cur.song || 1,
        // Für den Fall, dass die Datei in einem Unterordner liegt:
        items: [
          {
            source: cur.source || "library",
            path: cur.path,
            name: file.name || cur.name,
            song: cur.song || 1,
          },
        ],
      });
      this._flash = `„${cur.name}“ → Playlist „${result.name}“ (${result.count})`;
      this._error = null;
      await this._playlistsLoad();
    } catch (err) {
      this._error = err.message || String(err);
      this._render();
    }
  }

  async _openPlaylist(name) {
    try {
      this._playlist = await this._ws("playlist_get", { name });
      this._error = null;
    } catch (err) {
      this._playlist = null;
      this._error = err.message || String(err);
    }
    this._render();
  }

  async _playPlaylist(shuffle) {
    if (!this._playlist) return;
    this._playlistBusy = true;
    this._render();
    try {
      this._queue = await this._ws("playlist_play", {
        name: this._playlist.name,
        shuffle: !!shuffle,
      });
      this._flash = `Playlist „${this._playlist.name}“ läuft (${this._queue.count} Tune(s))`;
      await this._refreshCurrent();
    } catch (err) {
      this._error = err.message || String(err);
    } finally {
      this._playlistBusy = false;
      this._render();
    }
  }

  async _playlistRemove(index) {
    if (!this._playlist) return;
    try {
      this._playlist = await this._ws("playlist_edit", {
        name: this._playlist.name,
        action: "remove",
        index,
      });
      await this._playlistsLoad();
    } catch (err) {
      this._error = err.message || String(err);
      this._render();
    }
  }

  async _playlistDelete() {
    if (!this._playlist) return;
    const name = this._playlist.name;
    try {
      await this._ws("playlist_edit", { name, action: "delete" });
      this._playlist = null;
      this._flash = `Playlist „${name}“ gelöscht`;
      await this._playlistsLoad();
    } catch (err) {
      this._error = err.message || String(err);
      this._render();
    }
  }

  /* -------------------------------------------------- Darstellung */
  /* Die Leiste unter der Liste: was läuft, wie lange noch, nächster Tune. */
  _queueBar() {
    const q = this._queue || {};
    if (!q.count) return "";
    const items = q.items || [];
    const cur = items[q.index] || null;
    const next = items[q.index + 1] || null;
    const rest = this._queueRemaining();
    const left = rest !== null ? this._fmtLength(rest) : null;
    const info = cur
      ? `<b>${this._esc(cur.name)}</b>${
          cur.song > 1 ? ` · Tune ${cur.song}` : ""
        } · ${q.index + 1}/${q.count}` +
        (left ? ` · <span id="qLeft">noch ${left}</span>` : "") +
        (next ? ` · dann ${this._esc(next.name)}` : " · letzter Tune")
      : `${q.count} Tune(s) bereit`;
    return `<div class="queue">
      <div class="qtext">${q.playing ? "▶" : "⏸"} ${info}</div>
      <div class="qbtns">
        <button id="qPrev" title="Vorheriger Tune" ${q.index > 0 ? "" : "disabled"}>⏮</button>
        <button id="qNext" title="Nächster Tune" ${next ? "" : "disabled"}>⏭</button>
        ${
          q.playing
            ? `<button id="qPause" title="Anhalten">⏸</button>`
            : `<button id="qPlay" title="Weiter" ${cur ? "" : "disabled"}>▶</button>`
        }
        <button id="qStop" title="Warteschlange beenden">⏹</button>
      </div>
    </div>`;
  }

  _fmtLength(seconds) {
    if (!seconds && seconds !== 0) return "–";
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  _render() {
    if (!this.shadowRoot) return;
    const view = this._view;
    const cur = this._current || {};
    const rows = this._entries
      .map((entry) => {
        if (entry.is_dir) {
          return `<div class="row dir" data-dir="${this._esc(entry.name)}">
            <span class="icon">📁</span><span class="name">${this._esc(entry.name)}</span>
          </div>`;
        }
        const tunes =
          entry.songs > 1 ? `<span class="badge">${entry.songs} Tunes</span>` : "";
        const len = entry.duration ? `<span class="len">${this._fmtLength(entry.duration)}</span>` : "";
        const key = `${view.path}/${entry.name}`;
        const open = this._openTunes === key;
        let tuneRows = "";
        if (open && this._detail && this._detail.path === key) {
          const lengths = this._detail.lengths || [];
          const main = this._detail.start_song || 1;
          const cur = this._current || {};
          const playing =
            cur.source === view.source && cur.path === key ? cur.song || 0 : 0;
          let html = "";
          for (let i = 1; i <= Math.min(this._detail.songs, 64); i += 1) {
            const cls = i === playing ? "tune playing" : i === main ? "tune main" : "tune";
            const mark = i === playing ? "▶ " : i === main ? "★ " : "";
            html += `<button class="${cls}" data-song="${i}" data-name="${this._esc(entry.name)}"
              title="${i === playing ? "läuft gerade" : i === main ? "Haupttune des SID" : ""}">
              ${mark}<b>${i}</b>${lengths[i - 1] ? `<span>${this._fmtLength(lengths[i - 1])}</span>` : ""}
            </button>`;
          }
          tuneRows = `<div class="tunes">${html}</div>`;
        }
        return `<div class="row file ${this._playing === key ? "busy" : ""}"
                     data-play="${this._esc(entry.name)}">
            <span class="icon">${open ? "▾" : "♪"}</span>
            <span class="name">${this._esc(entry.name)}</span>
            ${tunes}${len}
          </div>${tuneRows}`;
      })
      .join("");

    if (this._resolveError) {
      this.shadowRoot.innerHTML = `
        <style>
          ha-card { padding:14px; font-size:.88rem; color: var(--primary-text-color,#eee); }
          .t { font-weight:600; margin-bottom:6px; }
        </style>
        <ha-card>
          <div class="t">UltimateControl</div>
          <div>${this._esc(this._resolveError)}</div>
        </ha-card>`;
      return;
    }

    if (this._playlistView) {
      const list = this._playlist;
      const items = list ? list.items || [] : [];
      const rows = items
        .map(
          (item, index) => `<div class="row file">
            <span class="icon">♪</span>
            <span class="name" data-plplay="${index}" title="Diesen Tune jetzt spielen"
                  style="cursor:pointer">${this._esc(item.name)}${
              item.song > 1 ? ` · Tune ${item.song}` : ""
            }</span>
            <button class="tune" data-plrm="${index}" title="Aus der Playlist entfernen">✕</button>
          </div>`
        )
        .join("");
      const names = (this._playlists || [])
        .map(
          (item) => `<button class="plname" data-plopen="${this._esc(item.name)}">
            ${this._esc(item.name)} <span class="badge">${item.count}</span>
          </button>`
        )
        .join("");
      this.shadowRoot.innerHTML = `
        <style>
          :host { display:block; }
          ha-card { padding: 12px 14px 14px; }
          .head { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
          .title { font-size:1.05rem; font-weight:600; flex:1; }
          .list { max-height: 300px; overflow-y:auto; }
          .row { display:flex; align-items:center; gap:8px; padding:6px 4px; border-radius:6px;
                 font-size:.92rem; }
          .row .name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
          .row .tune { font:inherit; font-size:.78rem; padding:1px 8px; border-radius:10px;
                       border:1px solid var(--divider-color,#444); background:transparent;
                       color:var(--primary-text-color,#eee); cursor:pointer; }
          .badge { font-size:.7rem; padding:1px 6px; border-radius:8px;
                   background:rgba(127,127,127,.22); }
          .plname { font:inherit; font-size:.82rem; padding:4px 10px; border-radius:14px;
                    border:1px solid var(--divider-color,#444); background:transparent;
                    color: var(--primary-text-color,#eee); cursor:pointer; margin:0 4px 4px 0; }
          .hint { font-size:.78rem; color: var(--secondary-text-color,#999); margin:8px 0; }
          .actions { display:flex; gap:8px; margin-top:10px; flex-wrap:wrap; }
          .actions button { font:inherit; font-size:.85rem; padding:6px 14px; border-radius:16px;
                            border:1px solid var(--divider-color,#444); background:transparent;
                            color: var(--primary-text-color,#eee); cursor:pointer; }
          .actions button.primary { background: var(--primary-color,#03a9f4);
                                    border-color:transparent; color:#fff; }
          .actions button:disabled { opacity:.45; cursor:default; }
          .msg { font-size:.8rem; margin-top:6px; }
          .msg.err { color: var(--error-color,#f44336); }
        </style>
        <ha-card>
          <div class="head">
            <div class="title">Playlists</div>
            <button class="tune" id="plBack">Zurück</button>
          </div>
          <div>${names || `<div class="hint">Noch keine Playlist. Tune spielen und „＋ Playlist“ drücken.</div>`}</div>
          ${
            list
              ? `<div class="path"><b>${this._esc(list.name)}</b> · ${items.length} Tune(s)</div>
                 <div class="list">${rows || `<div class="hint">Diese Playlist ist leer.</div>`}</div>
                 <div class="actions">
                   <button class="primary" id="plPlay" ${
                     items.length && !this._playlistBusy ? "" : "disabled"
                   }>▶ Playlist abspielen</button>
                   <button id="plShuffle" ${items.length ? "" : "disabled"}>🔀</button>
                   <button id="plDelete">Playlist löschen</button>
                 </div>`
              : `<div class="hint">Eine Playlist antippen, um sie zu sehen und abzuspielen.</div>`
          }
          ${this._error ? `<div class="msg err">${this._esc(this._error)}</div>` : ""}
        </ha-card>`;

      const root = this.shadowRoot;
      root.querySelector("#plBack").addEventListener("click", () => {
        this._playlistView = false;
        this._render();
      });
      root.querySelectorAll("[data-plopen]").forEach((el) =>
        el.addEventListener("click", () => this._openPlaylist(el.dataset.plopen))
      );
      root.querySelectorAll("[data-plrm]").forEach((el) =>
        el.addEventListener("click", () => this._playlistRemove(Number(el.dataset.plrm)))
      );
      root.querySelectorAll("[data-plplay]").forEach((el) =>
        el.addEventListener("click", () => {
          const item = items[Number(el.dataset.plplay)];
          if (item) {
            this._play(item.name, item.song || 1, item.source || "library", item.path);
          }
        })
      );
      const play = root.querySelector("#plPlay");
      if (play) play.addEventListener("click", () => this._playPlaylist(false));
      const shuffle = root.querySelector("#plShuffle");
      if (shuffle) shuffle.addEventListener("click", () => this._playPlaylist(true));
      const del = root.querySelector("#plDelete");
      if (del) del.addEventListener("click", () => this._playlistDelete());
      return;
    }

    if (this._import) {
      const imp = this._import;
      const rows = imp.entries
        .map(
          (entry) => `<div class="row dir" data-imp="${this._esc(entry.path)}">
            <span class="icon">📁</span><span class="name">${this._esc(entry.name)}</span>
          </div>`
        )
        .join("");
      const count =
        imp.sidCount === null || imp.sidCount === undefined
          ? ""
          : `<div class="hint">${imp.sidCount} SID-Datei(en) in diesem Ordner (Unterordner werden mit importiert)</div>`;
      this.shadowRoot.innerHTML = `
        <style>
          :host { display:block; }
          ha-card { padding: 12px 14px 14px; }
          .head { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
          .title { font-size:1.05rem; font-weight:600; flex:1; }
          .path { font-size:.78rem; color: var(--secondary-text-color,#999); margin-bottom:6px;
                  display:flex; align-items:center; gap:8px; word-break:break-all; }
          .list { max-height: 300px; overflow-y:auto; }
          .row { display:flex; align-items:center; gap:8px; padding:6px 4px; border-radius:6px;
                 cursor:pointer; font-size:.92rem; }
          .row:hover { background: rgba(127,127,127,.12); }
          .row .name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
          .hint { font-size:.78rem; color: var(--secondary-text-color,#999); margin:8px 0; }
          .actions { display:flex; gap:8px; margin-top:10px; }
          .actions button { font:inherit; font-size:.85rem; padding:6px 14px; border-radius:16px;
                            border:1px solid var(--divider-color,#444); background:transparent;
                            color: var(--primary-text-color,#eee); cursor:pointer; }
          .actions button.primary { background: var(--primary-color,#03a9f4);
                                    border-color:transparent; color:#fff; }
          .actions button:disabled { opacity:.45; cursor:default; }
          .msg { font-size:.8rem; margin-top:6px; }
          .msg.err { color: var(--error-color,#f44336); }
        </style>
        <ha-card>
          <div class="head"><div class="title">SIDs importieren</div></div>
          <div class="path">
            ${imp.parent !== null ? `<button class="up">↑</button>` : ""}
            <span>${this._esc(imp.path || "Ordner auf dem Home-Assistant-Rechner")}</span>
          </div>
          <div class="list">${rows || `<div class="hint">Keine Unterordner.</div>`}</div>
          ${count}
          <div class="actions">
            <button class="primary" id="impRun" ${imp.path && !imp.busy ? "" : "disabled"}>
              ${imp.busy ? "…" : "Diesen Ordner importieren"}
            </button>
            <button id="impCancel">Abbrechen</button>
          </div>
          ${this._error ? `<div class="msg err">${this._esc(this._error)}</div>` : ""}
        </ha-card>`;

      const root = this.shadowRoot;
      root.querySelectorAll("[data-imp]").forEach((el) =>
        el.addEventListener("click", () => this._importGo(el.dataset.imp))
      );
      const up = root.querySelector(".up");
      if (up) up.addEventListener("click", () => this._importGo(imp.parent || ""));
      root.querySelector("#impRun").addEventListener("click", () => this._importRun());
      root.querySelector("#impCancel").addEventListener("click", () => this._importClose());
      return;
    }

    const crumb = (view.path || "…").split("/").filter(Boolean).join(" / ");
    const current = cur.name
      ? `<div class="now">
           ${
             cur.source !== "device" && view.source !== "favorites"
               ? `<button id="fav" title="Zur aktuellen Datei in die Favoriten">★ Favorit</button>`
               : ""
           }
           ${
             view.source === "favorites" && cur.source === "favorites"
               ? `<button id="unfav" title="Aus den Favoriten entfernen">✕ Entfernen</button>`
               : ""
           }
           ${
             cur.source !== "device"
               ? `<button id="topl" title="Diesen Tune in eine Playlist legen">＋ Playlist</button>`
               : ""
           }
           <span class="nowText">▶ ${this._esc(cur.name)}${
             cur.song && cur.songs ? ` · Tune ${cur.song}/${cur.songs}` : ""
           }${cur.song_length ? ` · ${this._fmtLength(cur.song_length)}` : ""}</span>
         </div>`
      : "";

    const hvscBar = this._hvscBar();

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding: 12px 14px 14px; }
        .head { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
        .title { font-size:1.05rem; font-weight:600; flex:1; }
        .tabs { display:flex; gap:4px; }
        .tabs button, #fav, #unfav {
          font:inherit; font-size:.8rem; padding:4px 10px; border-radius:14px;
          border:1px solid var(--divider-color,#444); background:transparent;
          color: var(--primary-text-color,#eee); cursor:pointer;
        }
        .tabs button.on { background: var(--primary-color,#03a9f4); border-color:transparent; color:#fff; }
        .path { font-size:.78rem; color: var(--secondary-text-color,#999); margin-bottom:6px;
                display:flex; align-items:center; gap:8px; }
        .path .up { cursor:pointer; border:none; background:transparent; color:inherit; font:inherit; }
        .list { max-height: 340px; overflow-y:auto; }
        .row { display:flex; align-items:center; gap:8px; padding:6px 4px; border-radius:6px;
               cursor:pointer; font-size:.92rem; }
        .row:hover { background: rgba(127,127,127,.12); }
        .row.dir .icon { color:#ffb300; }
        .row .name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .badge { font-size:.7rem; padding:1px 6px; border-radius:8px;
                 background:rgba(127,127,127,.22); }
        .len { font-size:.75rem; color: var(--secondary-text-color,#999); }
        .row.busy { opacity:.5; }
        .tunes { display:flex; flex-wrap:wrap; gap:4px; padding:2px 4px 8px 26px; }
        .tunes .tune { font:inherit; font-size:.78rem; padding:3px 8px; border-radius:12px;
                       border:1px solid var(--divider-color,#444); background:transparent;
                       color:var(--primary-text-color,#eee); cursor:pointer; }
        .tunes .tune span { opacity:.6; margin-left:4px; }
        /* Haupttune des SID: blau vorbelegt. */
        .tunes .tune.main { border-color: var(--primary-color,#03a9f4); color:#fff;
                            background: color-mix(in srgb, var(--primary-color,#03a9f4) 45%, transparent); }
        /* Was gerade läuft: grün. */
        .tunes .tune.playing { border-color: var(--success-color,#4caf50); color:#fff;
                               background: color-mix(in srgb, var(--success-color,#4caf50) 60%, transparent); }
        .now { display:flex; align-items:center; gap:10px; margin-top:10px;
               padding-top:8px; border-top:1px solid var(--divider-color,#333);
               font-size:.82rem; color: var(--secondary-text-color,#bbb); }
        .nowText { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .msg { font-size:.8rem; margin-top:6px; }
        .msg.err { color: var(--error-color,#f44336); }
        .msg.ok { color: var(--success-color,#4caf50); }
        .empty { font-size:.85rem; color: var(--secondary-text-color,#888); padding:10px 4px; }
        .hvsc { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:8px;
                padding-top:8px; border-top:1px solid var(--divider-color,#333);
                font-size:.76rem; color: var(--secondary-text-color,#999); }
        .hvsc .grow { flex:1; }
        .hvsc button { font:inherit; font-size:.76rem; padding:3px 10px; border-radius:12px;
                       border:1px solid var(--divider-color,#444); background:transparent;
                       color: var(--primary-text-color,#eee); cursor:pointer; }
        .hvsc button.primary { background: var(--primary-color,#03a9f4);
                               border-color:transparent; color:#fff; }
        .hvsc button:disabled { opacity:.45; cursor:default; }
        .hvsc .warn { color:#ffb300; }
        #playFolder { font:inherit; font-size:.8rem; padding:4px 12px; border-radius:14px;
                      border:1px solid var(--divider-color,#444); background:transparent;
                      color: var(--primary-text-color,#eee); cursor:pointer; }
        #playFolder.primary { background: var(--primary-color,#03a9f4);
                              border-color:transparent; color:#fff; }
        #playFolder:disabled, #playShuffle:disabled { opacity:.45; cursor:default; }
        #playShuffle { font:inherit; font-size:.8rem; padding:4px 10px; border-radius:14px;
                       border:1px solid var(--divider-color,#444); background:transparent;
                       color: var(--primary-text-color,#eee); cursor:pointer; }
        .queue { display:flex; align-items:center; gap:8px; margin-top:10px; padding:8px 10px;
                 border-radius:10px; background:rgba(127,127,127,.12); font-size:.78rem; }
        .queue .qtext { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .queue .qbtns { display:flex; gap:4px; }
        .queue button { font:inherit; font-size:.8rem; padding:2px 8px; border-radius:12px;
                        border:1px solid var(--divider-color,#444); background:transparent;
                        color: var(--primary-text-color,#eee); cursor:pointer; }
        .queue button:disabled { opacity:.35; cursor:default; }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${this._esc(this._config.title)}</div>
          <div class="tabs">
            <button data-src="library" class="${view.source !== "favorites" ? "on" : ""}">HVSC</button>
            <button data-src="favorites" class="${view.source === "favorites" ? "on" : ""}">★ Favoriten</button>
            <button data-playlists="1" title="Playlists ansehen">Playlists${
              this._playlists && this._playlists.length ? ` (${this._playlists.length})` : ""
            }</button>
            <button data-import="1" title="SID-Ordner vom Home-Assistant-Rechner importieren">＋</button>
          </div>
        </div>
        <div class="path">
          ${view.path ? `<button class="up">↰</button>` : ""}<span>${this._esc(crumb)}</span>
        </div>
        <div class="path">
          <button id="playFolder" class="primary" ${
            this._folderBusy ? "disabled" : ""
          } title="Alle SIDs dieses Ordners nacheinander spielen">▶ Ordner abspielen</button>
          <button id="playShuffle" ${this._folderBusy ? "disabled" : ""} title="Zufällige Reihenfolge">🔀</button>
        </div>
        <div class="list">
          ${rows || `<div class="empty">Keine SID-Dateien hier.</div>`}
        </div>
        ${this._queueBar()}
        ${current}
        ${this._flash ? `<div class="msg ok">${this._esc(this._flash)}</div>` : ""}
        ${this._error ? `<div class="msg err">${this._esc(this._error)}</div>` : ""}
        ${hvscBar}
      </ha-card>`;

    const root = this.shadowRoot;
    root.querySelectorAll("[data-src]").forEach((el) =>
      el.addEventListener("click", () => this._switch(el.dataset.src))
    );
    root.querySelectorAll("[data-dir]").forEach((el) =>
      el.addEventListener("click", () => this._open({ name: el.dataset.dir, is_dir: true }))
    );
    root.querySelectorAll(".row.file").forEach((el) => {
      const name = el.dataset.play;
      const entry = this._entries.find((item) => item.name === name);
      el.addEventListener("click", (event) => {
        if (event.target.closest(".tune")) return;
        if (this._playing) return;
        this._open(entry);
      });
    });
    root.querySelectorAll(".tune").forEach((el) =>
      el.addEventListener("click", (event) => {
        event.stopPropagation();
        this._play(el.dataset.name, Number(el.dataset.song));
      })
    );
    const up = root.querySelector(".up");
    if (up) up.addEventListener("click", () => this._up());
    const fav = root.querySelector("#fav");
    if (fav) fav.addEventListener("click", () => this._favorite());
    const hvscGet = root.querySelector("#hvscGet");
    if (hvscGet) hvscGet.addEventListener("click", () => this._hvscDownload());
    const hvscCheck = root.querySelector("#hvscCheck");
    if (hvscCheck) hvscCheck.addEventListener("click", () => this._hvscStatus(true));
    const unfav = root.querySelector("#unfav");
    if (unfav) unfav.addEventListener("click", () => this._unfavorite());
    const imp = root.querySelector("[data-import]");
    if (imp) imp.addEventListener("click", () => this._openImport());
    const topl = root.querySelector("#topl");
    if (topl) topl.addEventListener("click", () => this._addToPlaylist());
    const plTab = root.querySelector("[data-playlists]");
    if (plTab)
      plTab.addEventListener("click", () => {
        this._playlistView = true;
        this._playlist = null;
        this._playlistsLoad();
        this._render();
      });
    const playFolder = root.querySelector("#playFolder");
    if (playFolder) playFolder.addEventListener("click", () => this._playFolder(false));
    const playShuffle = root.querySelector("#playShuffle");
    if (playShuffle) playShuffle.addEventListener("click", () => this._playFolder(true));
    const qPrev = root.querySelector("#qPrev");
    if (qPrev) qPrev.addEventListener("click", () => this._queueAction("previous"));
    const qNext = root.querySelector("#qNext");
    if (qNext) qNext.addEventListener("click", () => this._queueAction("next"));
    const qStop = root.querySelector("#qStop");
    if (qStop) qStop.addEventListener("click", () => this._queueAction("stop"));
    const qPause = root.querySelector("#qPause");
    if (qPause) qPause.addEventListener("click", () => this._queueAction("pause"));
    const qPlay = root.querySelector("#qPlay");
    if (qPlay) qPlay.addEventListener("click", () => this._queueAction("resume"));
  }

  _esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }
}

customElements.define("ultimatecontrol-panel", UltimateControlPanel);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "ultimatecontrol-panel",
  name: "UltimateControl SID-Auswahl",
  description: "HVSC durchsuchen, Tune wählen, auf dem C64 abspielen, Favoriten verwalten.",
});
