/**
 * UltimateControl – SID-Auswahl für das Dashboard.
 *
 * Ablage: /config/www/ultimatecontrol-panel.js
 * Ressource: /local/ultimatecontrol-panel.js  (JavaScript-Modul)
 *
 * type: custom:ultimatecontrol-panel
 * entry_id: <ID des Geräts>          (siehe Einstellungen → Geräte)
 * title: Ultimate 2 Cartridge        (optional)
 */
const DOMAIN = "ultimatecontrol";

class UltimateControlPanel extends HTMLElement {
  setConfig(config) {
    if (!config.entry_id) {
      throw new Error("ultimatecontrol-panel: 'entry_id' fehlt (Einstellungen → Geräte → Ultimate)");
    }
    this._config = { source: "library", path: "", title: "SID-Auswahl", ...config };
    this._hass = null;
    this._view = { source: this._config.source, path: this._config.path };
    this._entries = [];
    this._error = null;
    this._current = {};
    this._lastDir = {};
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._firstLoad();
    }
  }

  getCardSize() {
    return 8;
  }

  /* -------------------------------------------------- Laden */
  async _firstLoad() {
    await this._load();
    await this._refreshCurrent();
  }

  async _ws(type, payload = {}) {
    return this._hass.connection.sendMessagePromise({
      type: `${DOMAIN}/${type}`,
      entry_id: this._config.entry_id,
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

  async _play(name, song) {
    const path = this._view.path ? `${this._view.path}/${name}` : name;
    this._playing = path;
    this._render();
    try {
      this._current = await this._ws("play", {
        source: this._view.source,
        path,
        song,
      });
      this._error = null;
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._playing = null;
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

  /* -------------------------------------------------- Darstellung */
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
          let html = "";
          for (let i = 1; i <= Math.min(this._detail.songs, 64); i += 1) {
            html += `<button class="tune" data-song="${i}" data-name="${this._esc(entry.name)}">
              <b>${i}</b>${lengths[i - 1] ? `<span>${this._fmtLength(lengths[i - 1])}</span>` : ""}
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

    const crumb = (view.path || "…").split("/").filter(Boolean).join(" / ");
    const current = cur.name
      ? `<div class="now">
           ${cur.source !== "device" ? `<button id="fav" title="Zur aktuellen Datei in die Favoriten">★ Favorit</button>` : ""}
           <span class="nowText">▶ ${this._esc(cur.name)}${
             cur.song && cur.songs ? ` · Tune ${cur.song}/${cur.songs}` : ""
           }${cur.song_length ? ` · ${this._fmtLength(cur.song_length)}` : ""}</span>
         </div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding: 12px 14px 14px; }
        .head { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
        .title { font-size:1.05rem; font-weight:600; flex:1; }
        .tabs { display:flex; gap:4px; }
        .tabs button, #fav {
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
        .now { display:flex; align-items:center; gap:10px; margin-top:10px;
               padding-top:8px; border-top:1px solid var(--divider-color,#333);
               font-size:.82rem; color: var(--secondary-text-color,#bbb); }
        .nowText { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .msg { font-size:.8rem; margin-top:6px; }
        .msg.err { color: var(--error-color,#f44336); }
        .msg.ok { color: var(--success-color,#4caf50); }
        .empty { font-size:.85rem; color: var(--secondary-text-color,#888); padding:10px 4px; }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${this._esc(this._config.title)}</div>
          <div class="tabs">
            <button data-src="library" class="${view.source !== "favorites" ? "on" : ""}">HVSC</button>
            <button data-src="favorites" class="${view.source === "favorites" ? "on" : ""}">★ Favoriten</button>
          </div>
        </div>
        <div class="path">
          ${view.path ? `<button class="up">↰</button>` : ""}<span>${this._esc(crumb)}</span>
        </div>
        <div class="list">
          ${rows || `<div class="empty">Keine SID-Dateien hier.</div>`}
        </div>
        ${current}
        ${this._flash ? `<div class="msg ok">${this._esc(this._flash)}</div>` : ""}
        ${this._error ? `<div class="msg err">${this._esc(this._error)}</div>` : ""}
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
