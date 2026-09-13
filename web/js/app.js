// DARO-CAD -- Zusammenspiel von Zeichenflaeche, Werkzeugen und Python-Kern.
import * as G from "./geom.js";
import * as API from "./api.js";
import { Drawing, SCALES, SHEETS, entityBBox, distanceTo } from "./doc.js";
import { Renderer } from "./render.js";
import { Session, TOOLS, TOOL_GROUPS, parsePoint, applyOrtho } from "./tools.js";
import { findSnap, DEFAULT_SNAPS } from "./snap.js";
import { View3D } from "./view3d.js";
import * as P from "./prims.js";

// Kopie der unveraenderten Seite, solange die App das DOM noch nicht angefasst
// hat. Daraus entsteht spaeter die Datei hinter "App speichern".
const APP_HTML = typeof document !== "undefined"
  ? "<!DOCTYPE html>\n" + document.documentElement.outerHTML : "";

const ICONS = {
  select: "▹", line: "╱", polyline: "⌇", rect: "▭", circle: "◯", arc: "◜",
  point: "·", text: "T", hatch: "▨", dimlinear: "↔", dimaligned: "⤢",
  dimangular: "∠", dimradius: "⌀", measure: "⟺", move: "✥", copy: "⧉",
  rotate: "↻", mirror: "⇄", scale: "⤡", offset: "⇉", trim: "✂", extend: "⇥",
  fillet: "◟", chamfer: "◺", explode: "⁂", erase: "␡",
};

const COMMANDS = {
  linie: "line", l: "line", polylinie: "polyline", pl: "polyline", p: "polyline",
  rechteck: "rect", re: "rect", r: "rect", kreis: "circle", k: "circle",
  bogen: "arc", b: "arc", text: "text", t: "text", punkt: "point",
  schraffur: "hatch", h: "hatch", mass: "dimlinear", m: "dimlinear",
  massausgerichtet: "dimaligned", winkelmass: "dimangular", radiusmass: "dimradius",
  messen: "measure", verschieben: "move", v: "move", kopieren: "copy", c: "copy",
  drehen: "rotate", d: "rotate", spiegeln: "mirror", sp: "mirror",
  skalieren: "scale", versatz: "offset", o: "offset", stutzen: "trim", s: "trim",
  dehnen: "extend", e: "extend", runden: "fillet", f: "fillet", fasen: "chamfer",
  auswahl: "select", esc: "select", aufloesen: "explode", "auflösen": "explode",
  loeschen: "erase", "löschen": "erase",
};

class App {
  constructor() {
    this.drawing = new Drawing();
    this.canvas = document.getElementById("canvas");
    this.renderer = new Renderer(this.canvas, this.drawing);
    this.session = new Session(this);
    this.view3d = new View3D(document.getElementById("view3d"));
    this.selection = new Set();
    this.snaps = { ...DEFAULT_SNAPS };
    this.snapEnabled = true;
    this.orthoMode = "off";           // off | ortho | polar
    this.solids = [];
    this.cursor = [0, 0];
    this.dirty = true;
    this.freecad = { available: false };

    // Zeicheneinstellungen (aus der Seitenleiste)
    this.textHeight = 3.5;
    this.dimDecimals = 1;
    this.offsetDistance = 5;
    this.filletRadius = 5;
    this.chamferSize = 2;
    this.hatchAngle = 45;
    this.hatchSpacing = 3;
    this.gridSnapStep = 10;
    this.diameterInput = false;

    this.buildTools();
    this.buildSelects();
    this.bindCanvas();
    this.bindUI();
    this.bindKeys();

    this.drawing.addEventListener("change", () => {
      this.renderer.cache.clear();
      this.invalidate();
      this.renderLayers();
      this.renderProps();
    });

    window.addEventListener("resize", () => { this.renderer.resize(); this.invalidate(); });
    this.renderer.resize();
    this.startDrawing();
    this.loop();
    this.checkStatus();
    this.renderLayers();
    this.syncMeta();
    this.setPrompt("");
    this.setupWelcome();
  }

  // -- Startbildschirm -----------------------------------------------------

  /** Eingebettete Beispielzeichnung, falls die Fassung eine mitbringt. */
  exampleDrawing() {
    const tag = document.getElementById("beispielZeichnung");
    if (!tag) return null;
    try {
      return JSON.parse(tag.textContent);
    } catch (err) {
      return null;
    }
  }

  setupWelcome() {
    const overlay = document.getElementById("welcome");
    if (!overlay) return;

    const hasExample = !!this.exampleDrawing();
    const exampleBtn = document.getElementById("welcomeExample");
    if (exampleBtn && !hasExample) exampleBtn.hidden = true;

    for (const btn of overlay.querySelectorAll("[data-start]")) {
      btn.addEventListener("click", () => this.startWith(btn.dataset.start));
    }
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) this.hideWelcome();
    });

    let seen = false;
    try { seen = window.localStorage.getItem("darocad:welcomeSeen") === "1"; }
    catch (err) { /* gesperrter Speicher: dann eben jedes Mal zeigen */ }
    if (!seen) this.showWelcome();
  }

  showWelcome() {
    const overlay = document.getElementById("welcome");
    if (!overlay) return;
    const again = document.getElementById("welcomeAgain");
    if (again) {
      // Standard: nach der ersten Auswahl nicht mehr zeigen. Nur wer das
      // Haekchen setzt, bekommt den Startbildschirm jedes Mal wieder.
      try { again.checked = window.localStorage.getItem("darocad:welcomeSeen") === "0"; }
      catch (err) { again.checked = false; }
    }
    overlay.hidden = false;
  }

  hideWelcome() {
    const overlay = document.getElementById("welcome");
    if (overlay) overlay.hidden = true;
    const again = document.getElementById("welcomeAgain");
    try {
      window.localStorage.setItem("darocad:welcomeSeen", again && again.checked ? "0" : "1");
    } catch (err) { /* ohne Speicher erscheint der Startbildschirm wieder */ }
  }

  startWith(choice) {
    this.hideWelcome();
    if (choice === "help") {
      document.getElementById("helpDialog").showModal();
      return;
    }
    if (choice === "example") {
      const data = this.exampleDrawing();
      if (!data) { this.toast("Diese Fassung bringt kein Beispiel mit."); return; }
      this.drawing.load(data);
      this.selection.clear();
      this.solids = [];
      this.view3d.setSolids([]);
      this.syncMeta();
      this.renderLayers();
      this.renderer.zoomSheet();
      this.invalidate();
      this.toast("Beispiel geladen. Mausrad zoomt, mittlere Taste verschiebt.", 6000);
      return;
    }
    this.canvas.focus();
  }

  /** Die App selbst als Datei herausgeben (nur in der Online-Fassung angeboten). */
  async saveApp() {
    if (typeof API.saveApp !== "function") return;
    try {
      const res = await API.saveApp(APP_HTML, "DARO-CAD.html");
      if (res && res.status === "saved") {
        this.toast("DARO-CAD.html gespeichert. Die Datei doppelklicken – " +
          "dort läuft die App auch ohne Internet und kann zusätzlich DXF.", 9000);
      }
    } catch (err) { this.toast(err.message, 9000); }
  }

  // -- Aufbau --------------------------------------------------------------

  buildTools() {
    const host = document.getElementById("tools");
    host.innerHTML = "";
    for (const group of TOOL_GROUPS) {
      const names = Object.keys(TOOLS).filter((n) => TOOLS[n].group === group);
      if (!names.length) continue;
      const title = document.createElement("h5");
      title.textContent = group === "Aendern" ? "Ändern"
        : group === "Bemassung" ? "Bemaßung" : group;
      host.appendChild(title);
      for (const name of names) {
        const btn = document.createElement("button");
        btn.className = "tool";
        btn.dataset.tool = name;
        btn.innerHTML = `<span class="ico">${ICONS[name] || "•"}</span>` +
          `<span>${TOOLS[name].label}</span>`;
        btn.addEventListener("click", () => this.startTool(name));
        host.appendChild(btn);
      }
    }
  }

  buildSelects() {
    const sheet = document.getElementById("metaSheet");
    sheet.innerHTML = Object.keys(SHEETS)
      .map((s) => `<option value="${s}">${s === "A4L" ? "A4 quer" : s}</option>`).join("");
    const scale = document.getElementById("metaScale");
    scale.innerHTML = SCALES.map((s) => `<option value="${s}">${s}</option>`).join("");
  }

  // -- Zeichenschleife -----------------------------------------------------

  invalidate() { this.dirty = true; }

  loop() {
    const step = () => {
      if (this.dirty) {
        this.renderer.selection = this.selection;
        this.renderer.draw();
        this.dirty = false;
      }
      requestAnimationFrame(step);
    };
    step();
  }

  startDrawing() {
    this.renderer.zoomSheet();
    this.invalidate();
  }

  // -- Zeigereingaben ------------------------------------------------------

  bindCanvas() {
    const c = this.canvas;
    let panning = false, panLast = null, windowStart = null, downPoint = null;

    const modelAt = (evt) => {
      const rect = c.getBoundingClientRect();
      return this.renderer.toModel([evt.clientX - rect.left, evt.clientY - rect.top]);
    };

    c.addEventListener("contextmenu", (e) => e.preventDefault());

    c.addEventListener("pointerdown", (e) => {
      c.focus();
      if (e.button === 1) {
        panning = true; panLast = [e.clientX, e.clientY];
        c.setPointerCapture(e.pointerId); e.preventDefault(); return;
      }
      const raw = modelAt(e);
      const p = this.resolvePoint(raw);
      if (e.button === 2) { this.session.finish(); this.invalidate(); return; }
      downPoint = p;
      if (this.session.phase === "select" || this.session.name === "select") {
        windowStart = p;
      }
    });

    c.addEventListener("pointermove", (e) => {
      if (panning) {
        this.renderer.pan(e.clientX - panLast[0], e.clientY - panLast[1]);
        panLast = [e.clientX, e.clientY];
        this.invalidate();
        return;
      }
      const raw = modelAt(e);
      const p = this.resolvePoint(raw);
      this.cursor = p;
      document.getElementById("coords").textContent =
        `${p[0].toFixed(2)}, ${p[1].toFixed(2)}`;

      if (windowStart && G.dist(windowStart, p) > this.renderer.px(4)) {
        this.renderer.preview = { entities: [], hints: [{ k: "rect",
          box: [Math.min(windowStart[0], p[0]), Math.min(windowStart[1], p[1]),
            Math.max(windowStart[0], p[0]), Math.max(windowStart[1], p[1])],
          crossing: p[0] < windowStart[0] }] };
      } else {
        this.session.move(p);
        if (this.session.name === "select" || this.session.phase === "select" ||
            this.session.phase === "entities") {
          const hit = this.pick(p);
          this.renderer.hover = hit ? hit.id : null;
        }
      }
      // Solange ein Werkzeug laeuft, den naechsten Schritt am Zeiger mitfuehren
      this.renderer.cursorHint = this.session.name === "select"
        ? null : { k: "label", p, text: this.session.hint };
      this.invalidate();
    });

    c.addEventListener("pointerup", (e) => {
      if (panning && e.button === 1) { panning = false; return; }
      if (e.button !== 0) return;
      const raw = modelAt(e);
      const p = this.resolvePoint(raw);

      if (windowStart && G.dist(windowStart, p) > this.renderer.px(4)) {
        this.selectWindow(windowStart, p, e.shiftKey);
        windowStart = null;
        this.renderer.preview = null;
        this.invalidate();
        return;
      }
      windowStart = null;

      if (this.session.phase === "entities") {
        const hit = this.pick(p);
        if (hit) this.session.pickEntity(hit, p);
        this.invalidate();
        return;
      }
      if (this.session.name === "select" || this.session.phase === "select") {
        const hit = this.pick(p);
        if (hit) {
          if (e.shiftKey) {
            this.selection.has(hit.id) ? this.selection.delete(hit.id) : this.selection.add(hit.id);
          } else if (!this.selection.has(hit.id)) {
            this.selection.clear(); this.selection.add(hit.id);
          }
        } else if (!e.shiftKey) {
          this.selection.clear();
        }
        this.renderProps();
        this.invalidate();
        return;
      }
      this.session.point(p);
      this.invalidate();
    });

    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = c.getBoundingClientRect();
      this.renderer.zoomAt([e.clientX - rect.left, e.clientY - rect.top],
        e.deltaY < 0 ? 1.15 : 1 / 1.15);
      this.invalidate();
    }, { passive: false });

    c.addEventListener("dblclick", (e) => {
      if (e.button === 0 && this.session.name === "select") {
        this.renderer.zoomExtents(); this.invalidate();
      }
    });
  }

  /** Fang und Ortho auf einen Rohpunkt anwenden. */
  resolvePoint(raw) {
    const tol = this.renderer.px(12);
    let p = raw;
    const last = this.session.pts[this.session.pts.length - 1];
    if (this.orthoMode !== "off" && last) p = applyOrtho(last, p, this.orthoMode);

    const snap = this.snapEnabled
      ? findSnap(this.drawing.visible(), p, {
        tolerance: tol, snaps: this.snaps, from: last,
        gridStep: this.gridSnapStep, enabled: this.snapEnabled })
      : null;
    this.renderer.snapMarker = snap;
    return snap ? snap.p : p;
  }

  pick(p) {
    const tol = this.renderer.px(7);
    let best = null, bestD = Infinity;
    for (const e of this.drawing.selectable()) {
      const box = entityBBox(e);
      if (box && (p[0] < box[0] - tol || p[0] > box[2] + tol ||
                  p[1] < box[1] - tol || p[1] > box[3] + tol)) continue;
      const d = distanceTo(e, p);
      if (d <= tol && d < bestD) { bestD = d; best = e; }
    }
    return best;
  }

  selectWindow(a, b, additive) {
    const box = [Math.min(a[0], b[0]), Math.min(a[1], b[1]),
      Math.max(a[0], b[0]), Math.max(a[1], b[1])];
    const crossing = b[0] < a[0];
    if (!additive) this.selection.clear();
    for (const e of this.drawing.selectable()) {
      const eb = entityBBox(e);
      if (!eb) continue;
      const hit = crossing ? G.bboxOverlap(eb, box) : G.bboxInside(eb, box);
      if (hit) this.selection.add(e.id);
    }
    this.renderProps();
  }

  // -- Werkzeuge und Befehle ----------------------------------------------

  startTool(name) {
    if (!TOOLS[name]) return;
    this.renderer.cursorHint = null;
    this.session.start(name);
    this.refreshUI();
    this.invalidate();
  }

  refreshUI() {
    for (const btn of document.querySelectorAll(".tool")) {
      btn.classList.toggle("active", btn.dataset.tool === this.session.name);
    }
    document.getElementById("prompt").textContent = this.session.hint || "Befehl";
  }

  setPrompt(text) {
    document.getElementById("prompt").textContent = text || "Befehl";
  }

  toast(message, ms = 3200) {
    const el = document.getElementById("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { el.hidden = true; }, ms);
  }

  askText(question, fallback = "") {
    const value = window.prompt(question, fallback);
    return value === null ? "" : value;
  }

  runCommand(text) {
    const raw = text.trim();
    if (!raw) { this.session.finish(); this.invalidate(); return; }
    const lower = raw.toLowerCase();

    if (lower === "zoom" || lower === "z") { this.renderer.zoomExtents(); this.invalidate(); return; }
    if (lower === "blatt") { this.renderer.zoomSheet(); this.invalidate(); return; }
    if (COMMANDS[lower]) { this.startTool(COMMANDS[lower]); return; }
    if (lower === "loeschen" || lower === "löschen" || lower === "entf") {
      this.deleteSelection(); return;
    }

    const last = this.session.pts[this.session.pts.length - 1];
    const point = parsePoint(raw, last);
    if (point) {
      this.session.point(point);
      this.invalidate();
      return;
    }
    const value = parseFloat(raw.replace(",", "."));
    if (isFinite(value) && this.session.number(value, this.cursor)) {
      this.invalidate();
      return;
    }
    this.toast(`Unbekannter Befehl: ${raw}`);
  }

  deleteSelection() {
    if (!this.selection.size) return;
    this.drawing.remove([...this.selection]);
    this.selection.clear();
    this.drawing.commit("Löschen");
    this.renderProps();
    this.invalidate();
  }

  // -- Tastatur ------------------------------------------------------------

  bindKeys() {
    const cmd = document.getElementById("cmd");
    cmd.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { this.runCommand(cmd.value); cmd.value = ""; e.preventDefault(); }
      if (e.key === "Escape") { cmd.value = ""; this.session.cancel(); this.invalidate(); }
    });

    window.addEventListener("keydown", (e) => {
      const inField = e.target.matches("input, select, textarea") && e.target.id !== "cmd";
      if (e.key === "F1") { e.preventDefault(); document.getElementById("helpDialog").showModal(); return; }
      if (e.key === "F3") { e.preventDefault(); this.toggle("tglSnap"); return; }
      if (e.key === "F7") { e.preventDefault(); this.toggle("tglGrid"); return; }
      if (e.key === "F8") { e.preventDefault(); this.toggle("tglOrtho"); return; }
      if (e.key === "F10") { e.preventDefault(); this.toggle("tglPolar"); return; }
      if (inField) return;

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        (e.shiftKey ? this.drawing.redo() : this.drawing.undo());
        this.selection.clear(); this.invalidate(); return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault(); this.drawing.redo(); this.invalidate(); return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
        e.preventDefault();
        this.selection = new Set(this.drawing.selectable().map((x) => x.id));
        this.renderProps(); this.invalidate(); return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault(); this.saveDrawing(); return;
      }
      if ((e.ctrlKey || e.metaKey)) return;

      if (e.target === cmd) return;
      switch (e.key) {
        case "Escape": this.session.cancel(); this.selection.clear(); this.invalidate(); break;
        case "Enter": this.session.finish(); this.invalidate(); break;
        case "Delete": case "Backspace": this.deleteSelection(); break;
        case "l": case "L": this.startTool("line"); break;
        case "p": case "P": this.startTool("polyline"); break;
        case "r": case "R": this.startTool("rect"); break;
        case "k": case "K": this.startTool("circle"); break;
        case "b": case "B": this.startTool("arc"); break;
        case "t": case "T": this.startTool("text"); break;
        case "h": case "H": this.startTool("hatch"); break;
        case "m": case "M": this.startTool("dimlinear"); break;
        case "v": case "V": this.startTool("move"); break;
        case "c": case "C": this.startTool("copy"); break;
        case "d": case "D": this.startTool("rotate"); break;
        case "s": case "S":
          if (this.session.name === "polyline") { this.session.finish(true); }
          else this.startTool("trim");
          this.invalidate(); break;
        case "e": case "E": this.startTool("extend"); break;
        case "f": case "F": this.startTool("fillet"); break;
        case " ": e.preventDefault(); cmd.focus(); break;
        default: break;
      }
    });
  }

  toggle(id) { document.getElementById(id).click(); }

  // -- Seitenleiste --------------------------------------------------------

  bindUI() {
    for (const tab of document.querySelectorAll(".tabs button")) {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-body > section").forEach((s) => s.classList.remove("active"));
        tab.classList.add("active");
        document.querySelector(`[data-panel="${tab.dataset.tab}"]`).classList.add("active");
        if (tab.dataset.tab === "model") this.view3d.draw();
      });
    }

    const bindNumber = (id, key) => {
      const el = document.getElementById(id);
      el.addEventListener("change", () => {
        const v = parseFloat(el.value.replace(",", "."));
        if (isFinite(v)) { this[key] = v; this.invalidate(); }
      });
    };
    bindNumber("optTextHeight", "textHeight");
    bindNumber("optDecimals", "dimDecimals");
    bindNumber("optOffset", "offsetDistance");
    bindNumber("optFillet", "filletRadius");
    bindNumber("optChamfer", "chamferSize");
    bindNumber("optGrid", "gridSnapStep");
    bindNumber("optHatchAngle", "hatchAngle");
    bindNumber("optHatchSpacing", "hatchSpacing");

    document.getElementById("activeLayer").addEventListener("change", (e) => {
      this.drawing.activeLayer = e.target.value;
      this.renderLayers();
    });
    document.getElementById("btnAddLayer").addEventListener("click", () => {
      const input = document.getElementById("newLayerName");
      const name = input.value.trim();
      if (!name || this.drawing.layers.some((l) => l.name === name)) return;
      this.drawing.layers.push({ name, color: "#111111", lineweight: 0.25,
        linetype: "continuous", visible: true, locked: false, printable: true });
      input.value = "";
      this.drawing.commit("Layer");
      this.renderLayers();
    });

    for (const input of document.querySelectorAll("[data-meta]")) {
      const key = input.dataset.meta;
      const handler = () => {
        this.drawing.meta[key] = input.type === "checkbox" ? input.checked : input.value;
        this.renderer.cache.clear();
        this.invalidate();
      };
      input.addEventListener("input", handler);
      input.addEventListener("change", handler);
    }

    document.getElementById("btnZoomExtents").onclick = () => { this.renderer.zoomExtents(); this.invalidate(); };
    document.getElementById("btnZoomSheet").onclick = () => { this.renderer.zoomSheet(); this.invalidate(); };
    document.getElementById("btnZoomIn").onclick = () => {
      this.renderer.zoomAt([this.renderer.width / 2, this.renderer.height / 2], 1.25); this.invalidate(); };
    document.getElementById("btnZoomOut").onclick = () => {
      this.renderer.zoomAt([this.renderer.width / 2, this.renderer.height / 2], 0.8); this.invalidate(); };

    const tglSnap = document.getElementById("tglSnap");
    tglSnap.onclick = () => { this.snapEnabled = !this.snapEnabled;
      tglSnap.classList.toggle("active", this.snapEnabled); };
    const tglOrtho = document.getElementById("tglOrtho");
    const tglPolar = document.getElementById("tglPolar");
    tglOrtho.onclick = () => {
      this.orthoMode = this.orthoMode === "ortho" ? "off" : "ortho";
      tglOrtho.classList.toggle("active", this.orthoMode === "ortho");
      tglPolar.classList.remove("active");
    };
    tglPolar.onclick = () => {
      this.orthoMode = this.orthoMode === "polar" ? "off" : "polar";
      tglPolar.classList.toggle("active", this.orthoMode === "polar");
      tglOrtho.classList.remove("active");
    };
    const tglGrid = document.getElementById("tglGrid");
    tglGrid.onclick = () => { this.renderer.showGrid = !this.renderer.showGrid;
      tglGrid.classList.toggle("active", this.renderer.showGrid); this.invalidate(); };
    const tglLw = document.getElementById("tglLw");
    tglLw.onclick = () => { this.renderer.showLineweights = !this.renderer.showLineweights;
      tglLw.classList.toggle("active", this.renderer.showLineweights); this.invalidate(); };

    document.getElementById("btnUndo").onclick = () => { this.drawing.undo(); this.selection.clear(); this.invalidate(); };
    document.getElementById("btnRedo").onclick = () => { this.drawing.redo(); this.invalidate(); };
    document.getElementById("btnNew").onclick = () => this.newDrawing();
    document.getElementById("btnSave").onclick = () => this.saveDrawing();
    document.getElementById("btnOpen").onclick = () => this.openDialog();
    document.getElementById("btnImport").onclick = () => document.getElementById("fileInput").click();
    document.getElementById("fileInput").addEventListener("change", (e) => this.importFile(e));
    document.getElementById("btnCloseOpen").onclick = () => document.getElementById("openDialog").close();
    document.getElementById("btnCloseHelp").onclick = () => document.getElementById("helpDialog").close();

    const menu = document.getElementById("exportMenu");
    document.getElementById("btnExport").onclick = (e) => { e.stopPropagation(); menu.classList.toggle("open"); };
    document.addEventListener("click", () => menu.classList.remove("open"));
    menu.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (btn && !btn.disabled) this.exportAs(btn.dataset.format);
    });

    document.getElementById("btnExtrude").onclick = () => this.extrude();
    document.getElementById("btnViews").onclick = () => this.deriveViews();

    const btnWelcome = document.getElementById("btnWelcome");
    if (btnWelcome) btnWelcome.onclick = () => this.showWelcome();

    const btnSaveApp = document.getElementById("btnSaveApp");
    if (btnSaveApp) {
      // Nur sinnvoll, wenn die App als veroeffentlichte Seite laeuft; oertlich
      // hat der Nutzer die Datei ja bereits.
      const hosted = typeof API.isHosted === "function" && API.isHosted();
      btnSaveApp.hidden = !hosted;
      btnSaveApp.onclick = () => this.saveApp();
    }
  }

  renderLayers() {
    const select = document.getElementById("activeLayer");
    select.innerHTML = this.drawing.layers
      .map((l) => `<option value="${l.name}">${l.name}</option>`).join("");
    select.value = this.drawing.activeLayer;

    const host = document.getElementById("layerList");
    host.innerHTML = "";
    for (const layer of this.drawing.layers) {
      const row = document.createElement("div");
      row.className = "layer-row" + (layer.name === this.drawing.activeLayer ? " active" : "");
      row.innerHTML =
        `<button class="eye${layer.visible ? "" : " off"}" title="Sichtbarkeit">👁</button>` +
        `<span class="swatch" style="background:${layer.color}"></span>` +
        `<span class="name" title="${layer.linetype} · ${layer.lineweight} mm">${layer.name}</span>` +
        `<span class="muted small">${layer.lineweight}</span>`;
      row.addEventListener("click", (e) => {
        if (e.target.classList.contains("eye")) {
          layer.visible = !layer.visible;
          this.renderLayers();
          this.invalidate();
          return;
        }
        this.drawing.activeLayer = layer.name;
        this.renderLayers();
      });
      host.appendChild(row);
    }
  }

  renderProps() {
    const host = document.getElementById("propsBody");
    const ids = [...this.selection];
    if (!ids.length) {
      host.innerHTML = '<p class="muted">Kein Element ausgewählt.</p>';
      return;
    }
    if (ids.length > 1) {
      host.innerHTML = `<p><b>${ids.length}</b> Elemente ausgewählt.</p>` +
        '<div class="row"><span>Layer</span><select id="propLayer"></select></div>';
      this.fillLayerSelect(ids);
      return;
    }
    const e = this.drawing.byId(ids[0]);
    if (!e) { host.innerHTML = '<p class="muted">Kein Element ausgewählt.</p>'; return; }

    const rows = [`<div class="row"><span>Typ</span><b>${typeLabel(e.type)}</b></div>`,
      '<div class="row"><span>Layer</span><select id="propLayer"></select></div>'];
    const num = (label, key, value, step = 1) =>
      `<div class="row"><span>${label}</span><input type="number" step="${step}" ` +
      `data-prop="${key}" value="${Number(value).toFixed(3)}"></div>`;

    if (e.type === "line") {
      rows.push(num("X 1", "a.0", e.a[0]), num("Y 1", "a.1", e.a[1]),
        num("X 2", "b.0", e.b[0]), num("Y 2", "b.1", e.b[1]),
        `<div class="row"><span>Länge</span><b>${G.dist(e.a, e.b).toFixed(2)} mm</b></div>`,
        `<div class="row"><span>Winkel</span><b>${G.angleOf(G.sub(e.b, e.a)).toFixed(2)}°</b></div>`);
    } else if (e.type === "circle") {
      rows.push(num("Mitte X", "c.0", e.c[0]), num("Mitte Y", "c.1", e.c[1]),
        num("Radius", "r", e.r, 0.5),
        `<div class="row"><span>Durchmesser</span><b>${(e.r * 2).toFixed(2)} mm</b></div>`);
    } else if (e.type === "arc") {
      rows.push(num("Mitte X", "c.0", e.c[0]), num("Mitte Y", "c.1", e.c[1]),
        num("Radius", "r", e.r, 0.5), num("Startwinkel", "start", e.start),
        num("Endwinkel", "end", e.end));
    } else if (e.type === "text") {
      rows.push(`<div class="row"><span>Inhalt</span><input data-prop="text" value="${
        escapeHtml(e.text)}"></div>`, num("Höhe", "h", e.h, 0.5), num("Drehung", "rot", e.rot));
    } else if (e.type === "dim") {
      rows.push(`<div class="row"><span>Maß</span><b>${P.dimText(e)}</b></div>`,
        `<div class="row"><span>Text ersetzen</span><input data-prop="text" value="${
          escapeHtml(e.text || "")}" placeholder="automatisch"></div>`,
        num("Texthöhe", "h", e.h, 0.5),
        `<div class="row"><span>Stellen</span><input type="number" min="0" max="3" ` +
        `data-prop="decimals" value="${e.decimals ?? 1}"></div>`);
    } else if (e.type === "hatch") {
      rows.push(num("Winkel", "angle", e.angle ?? 45, 15),
        num("Abstand", "spacing", e.spacing ?? 3, 0.5));
    } else if (e.type === "polyline") {
      rows.push(`<div class="row"><span>Punkte</span><b>${e.pts.length}</b></div>`,
        `<div class="row"><span>Geschlossen</span><input type="checkbox" data-prop="closed"${
          e.closed ? " checked" : ""}></div>`);
    }
    host.innerHTML = rows.join("");
    this.fillLayerSelect(ids);

    for (const input of host.querySelectorAll("[data-prop]")) {
      input.addEventListener("change", () => {
        const key = input.dataset.prop;
        const value = input.type === "checkbox" ? input.checked
          : (input.type === "number" ? parseFloat(input.value.replace(",", ".")) : input.value);
        applyProp(e, key, value);
        this.drawing.commit("Eigenschaft");
        this.renderProps();
        this.invalidate();
      });
    }
  }

  fillLayerSelect(ids) {
    const select = document.getElementById("propLayer");
    if (!select) return;
    select.innerHTML = this.drawing.layers
      .map((l) => `<option value="${l.name}">${l.name}</option>`).join("");
    const first = this.drawing.byId(ids[0]);
    if (first) select.value = first.layer;
    select.addEventListener("change", () => {
      for (const id of ids) {
        const e = this.drawing.byId(id);
        if (e) e.layer = select.value;
      }
      this.drawing.commit("Layer wechseln");
      this.invalidate();
    });
  }

  syncMeta() {
    for (const input of document.querySelectorAll("[data-meta]")) {
      const key = input.dataset.meta;
      const value = this.drawing.meta[key];
      if (input.type === "checkbox") input.checked = value !== false;
      else input.value = value ?? "";
    }
  }

  // -- Dateien und Export --------------------------------------------------

  async checkStatus() {
    const badge = document.getElementById("freecadBadge");
    try {
      const info = await API.status();
      this.freecad = info.freecad;
      if (!this.drawing.meta.date) {
        this.drawing.meta.date = info.today;
        this.syncMeta();
        this.renderer.cache.clear();
        this.invalidate();
      }
      if (info.standalone) {
        // Eigenständige HTML-Fassung: rechnet vollständig im Browser
        badge.textContent = "Eigenständige Fassung";
        badge.className = "freecad-badge ok";
        badge.title = "Läuft ohne Installation. PDF, SVG, DXF, Extrusion und " +
          "Ansichtsableitung stehen zur Verfügung. FCStd, STEP und STL brauchen " +
          "FreeCAD und die Python-Fassung.";
      } else {
        badge.textContent = info.freecad.available
          ? `FreeCAD verbunden${info.freecad.version ? " · " + String(info.freecad.version).slice(0, 22) : ""}`
          : "FreeCAD nicht gefunden";
        badge.className = "freecad-badge " + (info.freecad.available ? "ok" : "off");
        badge.title = info.freecad.available
          ? `${info.freecad.executable || "FreeCAD-Modul"} — FCStd, STEP und STL verfügbar`
          : "Ohne FreeCAD stehen PDF, SVG, DXF und die eigene Ansichtsableitung zur Verfügung.";
      }
      for (const btn of document.querySelectorAll("#exportMenu [data-freecad]")) {
        btn.disabled = !info.freecad.available;
        btn.title = info.freecad.available ? "" : "FreeCAD ist nicht installiert.";
      }
    } catch (err) {
      badge.textContent = "Dienst offline";
      badge.className = "freecad-badge off";
      this.toast(err.message, 6000);
    }
  }

  newDrawing() {
    if (this.drawing.entities.length &&
        !confirm("Neue Zeichnung beginnen? Nicht gespeicherte Änderungen gehen verloren.")) return;
    this.drawing.load({ meta: {}, layers: null, entities: [] });
    this.selection.clear();
    this.solids = [];
    this.view3d.setSolids([]);
    this.syncMeta();
    this.renderLayers();
    this.renderer.zoomSheet();
    this.invalidate();
    this.checkStatus();
  }

  async saveDrawing() {
    const name = window.prompt("Name der Zeichnung:",
      this.drawing.meta.drawingNumber + "_" + this.drawing.meta.title);
    if (!name) return;
    try {
      const res = await API.save(name, this.drawing.toJSON());
      this.toast(`Gespeichert: ${res.path}`);
    } catch (err) { this.toast(err.message, 6000); }
  }

  async openDialog() {
    const dialog = document.getElementById("openDialog");
    const host = document.getElementById("fileList");
    host.innerHTML = '<div class="file-row muted">Lade …</div>';
    dialog.showModal();
    try {
      const res = await API.listFiles();
      if (!res.files.length) {
        host.innerHTML = `<div class="file-row muted">Noch nichts gespeichert (${res.folder}).</div>`;
        return;
      }
      host.innerHTML = "";
      for (const file of res.files) {
        const row = document.createElement("div");
        row.className = "file-row";
        row.innerHTML = `<span>📄</span><span>${file.name}</span>` +
          `<span class="meta">${new Date(file.modified * 1000).toLocaleString("de-DE")}</span>`;
        row.onclick = async () => {
          try {
            const data = await API.load(file.name);
            this.drawing.load(data.document);
            this.selection.clear();
            this.syncMeta();
            this.renderLayers();
            this.renderer.zoomExtents();
            this.invalidate();
            dialog.close();
            this.toast(`Geöffnet: ${file.name}`);
          } catch (err) { this.toast(err.message, 6000); }
        };
        host.appendChild(row);
      }
    } catch (err) {
      host.innerHTML = `<div class="file-row muted">${err.message}</div>`;
    }
  }

  async importFile(event) {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    this.toast(`Lese ${file.name} …`, 9000);
    try {
      const base64 = await API.readFileAsBase64(file);
      const res = await API.importFile(file.name, base64);
      this.drawing.load(res.document);
      this.selection.clear();
      this.syncMeta();
      this.renderLayers();
      this.renderer.zoomExtents();
      this.invalidate();
      this.toast(`${res.entities} Elemente aus ${file.name} übernommen.`);
    } catch (err) { this.toast(err.message, 8000); }
  }

  async exportAs(format) {
    if (!format) return;
    this.toast(`Erzeuge ${format.toUpperCase()} …`, 12000);
    try {
      const res = await API.exportAs(format, {
        document: this.drawing.toJSON(), solids: this.solids, withSheet: true });
      const saved = await API.download(res.filename, res.data, res.mime);
      if (saved && saved.status === "declined") {
        // Nutzer hat das Speichern abgelehnt -- nicht erneut nachfragen,
        // aber auch die "Erzeuge ..."-Meldung nicht stehen lassen.
        this.toast("Speichern abgebrochen.", 2500);
        return;
      }
      this.toast(`${res.filename} (${Math.round(res.bytes / 1024)} kB) gespeichert.`);
    } catch (err) { this.toast(err.message, 9000); }
  }

  // -- 3D ------------------------------------------------------------------

  async extrude() {
    const ids = [...this.selection];
    if (!ids.length) { this.toast("Bitte zuerst die Umrisse der Kontur auswählen."); return; }
    const height = parseFloat(document.getElementById("extrudeHeight").value.replace(",", ".")) || 10;
    const density = parseFloat(document.getElementById("density").value.replace(",", ".")) || 7.85;
    try {
      const res = await API.solids({ document: this.drawing.toJSON(), ids, height, density });
      this.solids = res.solids;
      this.drawing.solids = res.solids.map((s) => ({
        name: s.name, height: s.height, z0: s.z0, profile: s.profile }));
      this.view3d.setSolids(res.solids);
      const box = res.bbox;
      document.getElementById("solidStats").innerHTML =
        `<b>${res.count}</b> Körper · Höhe <b>${height} mm</b><br>` +
        `Volumen <b>${(res.volume / 1000).toFixed(2)} cm³</b><br>` +
        `Masse <b>${res.mass.toFixed(3)} kg</b> (bei ${density} kg/dm³)<br>` +
        `Maße ${(box[3] - box[0]).toFixed(1)} × ${(box[4] - box[1]).toFixed(1)} × ` +
        `${(box[5] - box[2]).toFixed(1)} mm`;
      this.toast(`${res.count} Körper erzeugt.`);
      for (const btn of document.querySelectorAll("#exportMenu [data-freecad]")) {
        btn.disabled = !this.freecad.available;
      }
    } catch (err) { this.toast(err.message, 8000); }
  }

  async deriveViews() {
    if (!this.solids.length) { this.toast("Erst extrudieren, dann Ansichten ableiten."); return; }
    const views = [];
    if (document.getElementById("viewFront").checked) views.push("front");
    if (document.getElementById("viewTop").checked) views.push("top");
    if (document.getElementById("viewLeft").checked) views.push("left");
    if (!views.length) { this.toast("Mindestens eine Ansicht auswählen."); return; }
    const origin = (document.getElementById("viewOrigin").value || "0,0")
      .split(",").map((v) => parseFloat(v.replace(",", ".")) || 0);
    const gap = parseFloat(document.getElementById("viewGap").value) || 25;
    try {
      const res = await API.views({
        document: this.drawing.toJSON(), solids: this.solids, views,
        origin: [origin[0] || 0, origin[1] || 0], gap,
        labels: document.getElementById("viewLabels").checked });
      for (const e of res.entities) this.drawing.add(e, e.layer);
      this.drawing.commit("Ansichten");
      this.selection.clear();
      this.renderer.zoomExtents();
      this.invalidate();
      this.toast(`${res.count} Elemente als Ansichten eingefügt.`);
    } catch (err) { this.toast(err.message, 8000); }
  }
}

// -- Hilfsfunktionen ---------------------------------------------------------

function typeLabel(type) {
  return { line: "Linie", circle: "Kreis", arc: "Bogen", polyline: "Polylinie",
    text: "Text", dim: "Bemaßung", hatch: "Schraffur", point: "Punkt" }[type] || type;
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function applyProp(entity, key, value) {
  if (key.includes(".")) {
    const [field, index] = key.split(".");
    entity[field][Number(index)] = value;
  } else {
    entity[key] = value;
  }
  if (key === "text" && value === "") delete entity.text;
}

window.addEventListener("DOMContentLoaded", () => {
  window.daroCad = new App();
});
