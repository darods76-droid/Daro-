// KI-Helfer: aus einer Beschreibung Zeichnungselemente erzeugen.
//
// Getragen von der `sample`-Faehigkeit der Plattform; ohne sie (etwa in der
// Datei-Fassung) bleibt der Reiter verborgen und die App vollstaendig nutzbar.
//
// Wichtig: die Antwort ist **Daten, kein Programm**. Es wird nichts ausgewertet
// oder ausgefuehrt; jedes Element wird Feld fuer Feld geprueft und nur
// uebernommen, wenn Art, Zahlen und Layer stimmen. Alles andere wird verworfen
// und dem Nutzer gemeldet.

const ALLOWED = {
  line: ["a", "b"],
  circle: ["c", "r"],
  arc: ["c", "r", "start", "end"],
  ellipse: ["c", "rx", "ry", "rot"],
  polyline: ["pts", "closed"],
  text: ["p", "h", "text", "rot", "align"],
  point: ["p"],
  hatch: ["pts", "angle", "spacing"],
  dim: ["kind", "p1", "p2", "pos", "center", "axis", "h", "decimals", "text"],
  leader: ["p1", "p2", "text", "h"],
};

const MAX_ENTITIES = 400;
const MAX_COORD = 1e5;

const SCHEMA = `Du hilfst in einem CAD-Programm für technische Zeichnungen.
Antworte AUSSCHLIESSLICH mit JSON dieser Form:
{"entities":[ ... ], "note":"kurze Erklärung auf Deutsch"}

Erlaubte Elemente (Koordinaten in Millimetern, Y zeigt nach oben,
Winkel in Grad gegen den Uhrzeigersinn):
{"type":"line","a":[x,y],"b":[x,y]}
{"type":"circle","c":[x,y],"r":Zahl}
{"type":"arc","c":[x,y],"r":Zahl,"start":Grad,"end":Grad}
{"type":"ellipse","c":[x,y],"rx":Zahl,"ry":Zahl,"rot":Grad}
{"type":"polyline","pts":[[x,y],...],"closed":true|false}
{"type":"text","p":[x,y],"h":3.5,"text":"..."}
{"type":"hatch","pts":[[x,y],...],"angle":45,"spacing":3}
{"type":"dim","kind":"linear","p1":[x,y],"p2":[x,y],"pos":[x,y]}
{"type":"leader","p1":[x,y],"p2":[x,y],"text":"..."}

Jedes Element darf zusätzlich "layer" haben, erlaubt sind nur: LAYERS.
Regeln: Außenkonturen auf "Kontur", Maße auf "Bemassung", Mittellinien auf
"Mittellinie", Beschriftung auf "Text". Runde Ecken als Polylinie mit mehreren
Punkten annähern. Keine weiteren Felder, keine Kommentare, kein Text außerhalb
des JSON.`;

/** Ist der Helfer in dieser Ansicht verfuegbar? */
export async function available() {
  if (typeof window === "undefined" || !window.claude ||
      typeof window.claude.use !== "function") return null;
  try {
    return await window.claude.use("sample");
  } catch (err) {
    return null;
  }
}

const finite = (v) => typeof v === "number" && Number.isFinite(v) && Math.abs(v) <= MAX_COORD;
const isPoint = (v) => Array.isArray(v) && v.length === 2 && finite(v[0]) && finite(v[1]);

/**
 * Ein vorgeschlagenes Element pruefen.
 * @returns {object|null} bereinigtes Element oder null samt Grund in `reasons`
 */
export function checkEntity(raw, layers, reasons) {
  if (!raw || typeof raw !== "object") { reasons.push("kein Objekt"); return null; }
  const fields = ALLOWED[raw.type];
  if (!fields) { reasons.push(`unbekannte Art „${raw.type}“`); return null; }

  const out = { type: raw.type };
  for (const key of fields) {
    if (raw[key] === undefined) continue;
    const v = raw[key];
    if (key === "pts") {
      if (!Array.isArray(v) || v.length < 2 || v.length > 2000 || !v.every(isPoint)) {
        reasons.push(`${raw.type}: Punktliste ungültig`); return null;
      }
      out.pts = v.map((p) => [p[0], p[1]]);
    } else if (["a", "b", "c", "p", "p1", "p2", "pos", "center"].includes(key)) {
      if (!isPoint(v)) { reasons.push(`${raw.type}.${key}: kein Punkt`); return null; }
      out[key] = [v[0], v[1]];
    } else if (["r", "rx", "ry", "rot", "start", "end", "h", "angle", "spacing",
                "decimals"].includes(key)) {
      if (!finite(v)) { reasons.push(`${raw.type}.${key}: keine Zahl`); return null; }
      out[key] = v;
    } else if (key === "closed") {
      out.closed = !!v;
    } else if (key === "text" || key === "kind" || key === "axis" || key === "align") {
      if (typeof v !== "string" || v.length > 200) {
        reasons.push(`${raw.type}.${key}: kein kurzer Text`); return null;
      }
      out[key] = v;
    }
  }

  // Pflichtfelder je Art
  const needed = { line: ["a", "b"], circle: ["c", "r"], arc: ["c", "r"],
    ellipse: ["c", "rx", "ry"], polyline: ["pts"], text: ["p", "text"],
    point: ["p"], hatch: ["pts"], dim: ["p1", "p2", "pos"], leader: ["p1", "p2"] };
  for (const key of needed[raw.type] || []) {
    if (out[key] === undefined) { reasons.push(`${raw.type}: ${key} fehlt`); return null; }
  }
  if ((out.r !== undefined && out.r <= 0) ||
      (out.rx !== undefined && out.rx <= 0) || (out.ry !== undefined && out.ry <= 0)) {
    reasons.push(`${raw.type}: Halbmesser muss größer als null sein`); return null;
  }

  const layer = typeof raw.layer === "string" ? raw.layer : "";
  out.layer = layers.includes(layer) ? layer : layers[0];
  return out;
}

/** Antwort des Helfers pruefen; liefert die uebernehmbaren Elemente. */
export function checkAnswer(data, layers) {
  const reasons = [];
  const list = data && Array.isArray(data.entities) ? data.entities : [];
  if (!list.length) return { entities: [], note: "", reasons: ["keine Elemente enthalten"] };
  const entities = [];
  for (const raw of list.slice(0, MAX_ENTITIES)) {
    const ok = checkEntity(raw, layers, reasons);
    if (ok) entities.push(ok);
  }
  const note = typeof data.note === "string" ? data.note.slice(0, 800) : "";
  return { entities, note, reasons };
}

/** Kurzfassung der Zeichnung als Zusammenhang fuer den Helfer. */
export function summarise(drawing) {
  const counts = {};
  for (const e of drawing.entities) counts[e.type] = (counts[e.type] || 0) + 1;
  const box = drawing.bbox();
  const parts = [
    `Blatt ${drawing.meta.sheet}, Maßstab ${drawing.meta.scale}`,
    `Benennung: ${drawing.meta.title || "-"}`,
    `Werkstoff: ${drawing.meta.material || "-"}`,
    `Elemente: ${Object.entries(counts).map(([k, v]) => `${v}x ${k}`).join(", ") || "keine"}`,
  ];
  if (box) {
    parts.push(`Belegter Bereich: X ${box[0].toFixed(0)}…${box[2].toFixed(0)}, ` +
      `Y ${box[1].toFixed(0)}…${box[3].toFixed(0)} mm`);
  }
  return parts.join("\n");
}

/** Geometrie erzeugen lassen. */
export async function draw(sample, wunsch, drawing) {
  const layers = drawing.layers.map((l) => l.name);
  const anweisung = SCHEMA.replace("LAYERS", layers.join(", "));
  const data = await sample.json([
    { role: "user", content: `${anweisung}\n\nStand der Zeichnung:\n${summarise(drawing)}\n\n` +
        `Aufgabe: ${wunsch}` },
  ], { modelTier: "default" });
  return checkAnswer(data, layers);
}

/** Frage zur Zeichnung oder zur Norm beantworten lassen. */
export async function ask(sample, frage, drawing, onText) {
  const res = await sample([
    { role: "user", content:
        "Du bist Zeichnungsprüfer für technische Zeichnungen nach DIN/ISO. " +
        "Antworte kurz und auf Deutsch.\n\n" +
        `Stand der Zeichnung:\n${summarise(drawing)}\n\nFrage: ${frage}` },
  ], { modelTier: "default", onText });
  return res.text;
}
