// Mitgelieferte Symbolbibliothek.
//
// Jedes Symbol ist ein gewoehnlicher Block: eine Liste von Elementen im
// Blockraum, deren Nullpunkt beim Einfuegen auf den Zielpunkt wandert. Dadurch
// laesst sich alles hier Genannte auch nachtraeglich bearbeiten, auflösen oder
// exportieren -- es sind keine Bilder, sondern Geometrie.
//
// Masse nach den einschlaegigen Normen: Sechskant SW13 fuer M8 (DIN EN ISO
// 4014/4032), Passfeder nach DIN 6885 Form A, Schweisssinnbild nach ISO 2553.

const K = "Kontur", M = "Mittellinie", T = "Text";

const line = (a, b, layer = K) => ({ type: "line", a, b, layer });
const circle = (c, r, layer = K) => ({ type: "circle", c, r, layer });
const poly = (pts, layer = K, bulges = null) => ({ type: "polyline", pts,
  closed: true, layer, ...(bulges ? { bulges } : {}) });
const label = (p, h, text, align = "center", layer = T) =>
  ({ type: "text", p, h, text, align, layer });

/** Mittelkreuz nach DIN ISO 128-20 (Strichpunktlinie, ueberstehend). */
function cross(r) {
  const o = r * 1.4;
  return [line([-o, 0], [o, 0], M), line([0, -o], [0, o], M)];
}

/** Regelmaessiges Vieleck mit Umkreisradius r, erste Ecke bei `phase` Grad. */
function ngon(n, r, phase = 0) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const a = (phase + i * 360 / n) * Math.PI / 180;
    pts.push([+(r * Math.cos(a)).toFixed(4), +(r * Math.sin(a)).toFixed(4)]);
  }
  return pts;
}

// Umkreisradius aus der Schluesselweite: r = SW / (2 cos 30°)
const fromWidth = (sw) => +(sw / (2 * Math.cos(Math.PI / 6))).toFixed(4);

export const LIBRARY = {
  "Bohrung Ø10": [circle([0, 0], 5), ...cross(5)],

  "Senkung 90° Ø10": [
    circle([0, 0], 5), circle([0, 0], 10), ...cross(10),
  ],

  "Schraube M8 (SK)": [
    poly(ngon(6, fromWidth(13), 30)),
    circle([0, 0], 4),
    ...cross(fromWidth(13)),
  ],

  "Mutter M8 (SK)": [
    poly(ngon(6, fromWidth(13), 30)),
    circle([0, 0], 4),
    circle([0, 0], 3.4),
    ...cross(fromWidth(13)),
  ],

  "Passfeder A 8x7x25": [
    // Rundungen als Woelbung: 1,0 entspricht einem Halbkreis
    poly([[-8.5, -4], [8.5, -4], [8.5, 4], [-8.5, 4]], K, [0, 1, 0, 1]),
    line([-12.5, 0], [12.5, 0], M),
  ],

  "Kehlnaht a4 (ISO 2553)": [
    line([0, 0], [9, 9]),                       // Pfeillinie
    line([9, 9], [38, 9]),                      // Bezugslinie
    poly([[14, 9], [14, 16], [21, 9]]),         // Sinnbild Kehlnaht
    label([12, 10.5], 3.5, "a4", "right"),
  ],

  "Nordpfeil": [
    poly([[0, 12], [4, -6], [0, -2], [-4, -6]]),
    label([0, 15], 5, "N"),
  ],

  "Schnittpfeil A": [
    poly([[0, 0], [-3, -7], [3, -7]]),
    line([0, -7], [0, -16], K),
    label([0, 3], 5, "A"),
  ],
};

/** Die Bibliothek in eine Zeichnung uebernehmen, ohne Vorhandenes zu ersetzen. */
export function installLibrary(drawing) {
  let added = 0;
  for (const [name, entities] of Object.entries(LIBRARY)) {
    if (drawing.blocks[name]) continue;
    drawing.defineBlock(name, entities, [0, 0]);
    added += 1;
  }
  return added;
}
