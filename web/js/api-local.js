// Serverlose Fassung der API: alles rechnet im Browser.
// Gleiche Schnittstelle wie api.js, damit app.js unveraendert damit arbeitet.
// Diese Datei wird in die eigenstaendige HTML-Fassung eingebunden.
import { Drawing, SCALES, SHEETS } from "./doc.js";
import * as SVG from "./export-svg.js";
import * as DXF from "./export-dxf.js";
import * as PDF from "./export-pdf.js";
import * as IMPDXF from "./import-dxf.js";
import * as SOLID from "./solid.js";
import * as VIEWS from "./views.js";

const STORE_PREFIX = "darocad:";

/** Zeichnung aus der Nutzlast als Drawing-Objekt aufbauen. */
function asDrawing(payload) {
  const data = payload && payload.document ? payload.document : payload;
  if (!data || typeof data !== "object") throw new Error("Zeichnungsdaten fehlen.");
  const d = new Drawing();
  d.load(data);
  return d;
}

const encoder = new TextEncoder();

function toBase64(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function fromBase64(b64) {
  const binary = atob(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

function stem(drawing) {
  const raw = `${drawing.meta.drawingNumber || ""}_${drawing.meta.title || "Zeichnung"}`
    .replace(/^_+|_+$/g, "");
  return raw.replace(/[^\w\-.]+/g, "_") || "Zeichnung";
}

// -- Ablage im Browser-Speicher ---------------------------------------------

function store() {
  try {
    // Manche Browser sperren localStorage bei file:// oder im privaten Fenster
    window.localStorage.setItem(STORE_PREFIX + "__test", "1");
    window.localStorage.removeItem(STORE_PREFIX + "__test");
    return window.localStorage;
  } catch (err) {
    return null;
  }
}

export async function status() {
  return {
    ok: true,
    freecad: { available: false, executable: null, module: false, version: null,
      formats: ["svg", "dxf", "pdf", "json"] },
    workspace: store() ? "Browser-Speicher dieses Rechners" : "nur Datei-Download",
    sheets: Object.keys(SHEETS),
    scales: SCALES,
    today: new Date().toLocaleDateString("de-DE"),
    version: "1.0 (eigenständig)",
    standalone: true,
  };
}

export async function listFiles() {
  const ls = store();
  const files = [];
  if (ls) {
    for (let i = 0; i < ls.length; i++) {
      const key = ls.key(i);
      if (!key || !key.startsWith(STORE_PREFIX)) continue;
      const raw = ls.getItem(key);
      let modified = Date.now() / 1000;
      try { modified = JSON.parse(raw).savedAt || modified; } catch (e) { /* egal */ }
      files.push({ name: key.slice(STORE_PREFIX.length), size: (raw || "").length, modified });
    }
  }
  files.sort((a, b) => a.name.localeCompare(b.name, "de"));
  return { ok: true, files, folder: ls ? "Browser-Speicher" : "nicht verfügbar" };
}

export async function load(name) {
  const ls = store();
  if (!ls) throw new Error("Der Browser-Speicher ist gesperrt. Bitte über „Import“ eine Datei laden.");
  const raw = ls.getItem(STORE_PREFIX + name);
  if (!raw) throw new Error(`„${name}“ wurde nicht gefunden.`);
  const data = JSON.parse(raw);
  return { ok: true, document: data.document || data };
}

export async function save(name, document) {
  const ls = store();
  if (!ls) throw new Error("Der Browser-Speicher ist gesperrt. Bitte „Export → DARO-CAD-Datei“ verwenden.");
  ls.setItem(STORE_PREFIX + name,
    JSON.stringify({ savedAt: Date.now() / 1000, document }));
  return { ok: true, name, path: `Browser-Speicher → ${name}` };
}

// -- 3D ----------------------------------------------------------------------

export async function solids(payload) {
  const drawing = asDrawing(payload);
  const ids = new Set(payload.ids || []);
  const entities = drawing.entities.filter((e) =>
    (!ids.size || ids.has(e.id)) &&
    ["line", "arc", "circle", "polyline"].includes(e.type));

  const loops = SOLID.buildLoops(entities, payload.tolerance ?? 0.05);
  if (!loops.length) {
    throw new Error("Keine geschlossene Kontur gefunden. " +
      "Die Umrisse müssen lückenlos aneinanderstoßen.");
  }
  const height = Number(payload.height ?? 10);
  const z0 = Number(payload.z0 ?? 0);
  const density = Number(payload.density ?? 7.85);

  const out = SOLID.classifyLoops(loops).map((profile, i) =>
    SOLID.extrude(profile.outer, profile.holes, height, z0,
      payload.name || `Körper ${i + 1}`));

  return {
    ok: true,
    solids: out,
    count: out.length,
    volume: out.reduce((s, x) => s + SOLID.volume(x), 0),
    mass: out.reduce((s, x) => s + SOLID.mass(x, density), 0),
    bbox: SOLID.bbox3(out),
  };
}

export async function views(payload) {
  const drawing = asDrawing(payload);
  let list = payload.solids;
  if (!list || !list.length) {
    list = (drawing.solids || []).filter((s) => s.profile).map((spec) =>
      SOLID.extrude(spec.profile.outer, spec.profile.holes || [],
        Number(spec.height ?? 10), Number(spec.z0 ?? 0), spec.name || "Körper"));
  }
  if (!list.length) throw new Error("Kein Körper vorhanden. Bitte zuerst ein Profil extrudieren.");

  const origin = payload.origin || [0, 0];
  const entities = VIEWS.derive(list, payload.views || ["front", "top", "left"], {
    origin: [Number(origin[0]) || 0, Number(origin[1]) || 0],
    gap: Number(payload.gap ?? 25),
    projection: drawing.meta.projection || "first",
    labels: payload.labels !== false,
    centerLines: payload.centerLines !== false,
  });
  return { ok: true, entities, count: entities.length };
}

// -- Import und Export -------------------------------------------------------

export async function importFile(filename, data) {
  const bytes = fromBase64(data);
  const lower = String(filename || "").toLowerCase();
  const text = new TextDecoder("utf-8").decode(bytes);

  if (lower.endsWith(".dxf")) {
    const doc = IMPDXF.parse(text);
    return { ok: true, document: doc, entities: doc.entities.length };
  }
  if (lower.endsWith(".json")) {
    const doc = JSON.parse(text);
    return { ok: true, document: doc, entities: (doc.entities || []).length };
  }
  if (lower.endsWith(".fcstd") || lower.endsWith(".step") || lower.endsWith(".stp")) {
    throw new Error("FCStd und STEP brauchen FreeCAD. Dafür bitte die Python-Fassung " +
      "verwenden (python3 -m daro_cad).");
  }
  throw new Error("Unterstützt werden DXF und DARO-CAD-Dateien (.json).");
}

export async function exportAs(format, payload) {
  const drawing = asDrawing(payload);
  const withSheet = payload.withSheet !== false;
  let bytes, mime, ext;

  switch (format) {
    case "svg":
      bytes = encoder.encode(SVG.render(drawing, withSheet));
      mime = "image/svg+xml"; ext = "svg"; break;
    case "dxf":
      bytes = encoder.encode(DXF.render(drawing, withSheet));
      mime = "application/dxf"; ext = "dxf"; break;
    case "pdf":
      bytes = PDF.render(drawing, withSheet);
      mime = "application/pdf"; ext = "pdf"; break;
    case "json": {
      const doc = drawing.toJSON();
      doc.solids = payload.solids && payload.solids.length
        ? payload.solids.map((s) => ({ name: s.name, height: s.height, z0: s.z0,
            profile: s.profile }))
        : doc.solids;
      bytes = encoder.encode(JSON.stringify(doc, null, 1));
      mime = "application/json"; ext = "darocad.json"; break;
    }
    case "fcstd": case "step": case "stl":
      throw new Error(`${format.toUpperCase()} braucht FreeCAD. Dafür bitte die ` +
        "Python-Fassung verwenden (python3 -m daro_cad).");
    default:
      throw new Error(`Unbekanntes Format: ${format}`);
  }

  return { ok: true, mime, filename: `${stem(drawing)}.${ext}`,
    data: toBase64(bytes), bytes: bytes.length };
}

// -- Dateien herausgeben -----------------------------------------------------

/**
 * Laeuft die App als veroeffentlichte Seite (Artifact)?
 *
 * Dort sind Blob-Downloads wirkungslos; Dateien gehen ueber die Plattform
 * heraus. Erkannt wird das an ``claude.use``, nicht an der Adresse -- die
 * Adresse sagt nichts darueber, ob der Weg offensteht.
 */
export function isHosted() {
  return typeof window !== "undefined" &&
    typeof window.claude === "object" && window.claude !== null &&
    typeof window.claude.use === "function";
}

// Endungen, die die Plattform beim Speichern annimmt (DXF ist nicht dabei).
const HOSTED_EXTENSIONS = new Set([
  "pdf", "svg", "json", "html", "txt", "md", "csv", "zip",
  "png", "jpg", "jpeg", "webp", "gif",
]);

const extensionOf = (filename) => String(filename).split(".").pop().toLowerCase();

function hostedMessage(code, filename) {
  switch (code) {
    case "rejected_extension":
    case "extension_not_enabled":
      return `${extensionOf(filename).toUpperCase()} lässt sich in der Online-Fassung ` +
        "nicht speichern. Bitte oben „App speichern“ anklicken – in der " +
        "heruntergeladenen Datei geht es.";
    case "too_large":
      return "Die Datei ist zu groß zum Speichern.";
    case "rate_limited":
      return "Es ist bereits eine Abfrage offen. Bitte kurz warten.";
    case "unavailable":
    case "not_granted":
    case "capability_disabled":
    case "capability_removed":
      return "Speichern ist in dieser Ansicht nicht möglich. Bitte oben " +
        "„App speichern“ anklicken und die Datei örtlich öffnen.";
    default:
      return "Die Datei konnte nicht gespeichert werden.";
  }
}

/** Eine Datei ueber die Plattform anbieten. */
async function saveHosted(filename, data) {
  const downloads = await window.claude.use("downloads");
  if (!downloads) {
    const err = new Error(hostedMessage("unavailable", filename));
    err.code = "unavailable";
    throw err;
  }
  if (!HOSTED_EXTENSIONS.has(extensionOf(filename))) {
    const err = new Error(hostedMessage("rejected_extension", filename));
    err.code = "rejected_extension";
    throw err;
  }
  try {
    await downloads.save({ filename, data });
    return { status: "saved" };
  } catch (err) {
    // Ein "Nein" des Nutzers ist kein Fehler -- nicht erneut nachfragen.
    if (err && err.code === "declined") return { status: "declined" };
    const out = new Error(hostedMessage(err && err.code, filename));
    out.code = (err && err.code) || "unavailable";
    throw out;
  }
}

/** Datei im Browser speichern -- oertlich per Blob, online ueber die Plattform. */
export async function download(filename, base64, mime) {
  const bytes = fromBase64(base64);
  if (isHosted()) {
    return saveHosted(filename, new Blob([bytes], { type: mime || "application/octet-stream" }));
  }
  const url = URL.createObjectURL(new Blob([bytes], { type: mime || "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return { status: "saved" };
}

/** Die App selbst als HTML-Datei herausgeben (nur in der Online-Fassung sinnvoll). */
export async function saveApp(html, filename = "DARO-CAD.html") {
  if (isHosted()) return saveHosted(filename, html);
  const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return { status: "saved" };
}

export function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result);
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.onerror = () => reject(new Error("Datei konnte nicht gelesen werden."));
    reader.readAsDataURL(file);
  });
}
