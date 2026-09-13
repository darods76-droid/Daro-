// Griffe: ausgewaehlte Elemente an ihren Punkten direkt ziehen.
//
// In jedem ernsthaften CAD-Programm ist das die meistgenutzte Aenderung --
// anklicken, Punkt fassen, verschieben. Die Griffpunkte selbst liefert
// render.js (gripPoints); hier kommt dazu, welchen Griff der Zeiger trifft und
// was ein Zug an diesem Griff mit der Entitaet macht.
import * as G from "./geom.js";
import { gripPoints } from "./render.js";
import { transformEntity } from "./doc.js";

export { gripPoints };

/**
 * Welchen Griff trifft der Punkt?
 * @returns {number} Index in gripPoints(), oder -1
 */
export function gripAt(entity, point, tol) {
  const pts = gripPoints(entity);
  let best = -1, bestD = tol;
  pts.forEach((g, i) => {
    const d = G.dist(g, point);
    if (d <= bestD) { bestD = d; best = i; }
  });
  return best;
}

/** Ersten Treffer in einer Auswahl suchen. */
export function findGrip(entities, point, tol) {
  for (const e of entities) {
    const index = gripAt(e, point, tol);
    if (index >= 0) return { entity: e, index, start: gripPoints(e)[index] };
  }
  return null;
}

/**
 * Einen Griff auf eine neue Lage ziehen.
 * Liefert eine geaenderte Kopie; das Original bleibt unangetastet, damit der
 * Rueckgaengig-Speicher sauber bleibt.
 */
export function applyGrip(entity, index, point) {
  const e = JSON.parse(JSON.stringify(entity));
  switch (e.type) {
    case "line":
      if (index === 0) e.a = point;
      else if (index === 2) e.b = point;
      else return moveWhole(entity, G.lerp(e.a, e.b, 0.5), point);  // Mittelgriff
      return e;

    case "circle":
      if (index === 0) { e.c = point; return e; }
      e.r = Math.max(1e-6, G.dist(e.c, point));      // Quadrantengriff = Radius
      return e;

    case "ellipse":
      if (index === 0) { e.c = point; return e; }
      if (index === 1 || index === 3) {
        // Hauptachse: Laenge und Drehung folgen dem Zeiger
        e.rx = Math.max(1e-6, G.dist(e.c, point));
        e.rot = G.angleOf(G.sub(point, e.c)) - (index === 3 ? 180 : 0);
      } else {
        e.ry = Math.max(1e-6, G.dist(e.c, point));
      }
      return e;

    case "arc": {
      if (index === 0) { e.c = point; return e; }
      const angle = G.angleOf(G.sub(point, e.c));
      const radius = Math.max(1e-6, G.dist(e.c, point));
      if (index === 1) { e.start = angle; } else { e.end = angle; }
      e.r = radius;
      return e;
    }

    case "polyline":
    case "hatch":
      if (index >= 0 && index < e.pts.length) e.pts[index] = point;
      return e;

    case "text":
    case "point":
    case "insert":
      e.p = point;
      return e;

    case "dim":
      if (index === 0) e.p1 = point;
      else if (index === 1) e.p2 = point;
      else e.pos = point;
      return e;

    case "leader":
      if (index === 0) e.p1 = point;       // Pfeilspitze
      else e.p2 = point;                   // Textlage
      return e;

    case "surface":
    case "fcf":
    case "insert":
      e.p = point;                         // Einfuegepunkt = ganzer Block
      return e;

    default:
      return e;
  }
}

/** Ganze Entitaet um die Differenz verschieben. */
function moveWhole(entity, from, to) {
  const v = G.sub(to, from);
  return transformEntity(entity, (p) => G.add(p, v));
}

/** Kurzer Hinweis, was der gefasste Griff tut. */
export function gripHint(entity, index) {
  switch (entity.type) {
    case "line": return index === 1 ? "Linie verschieben" : "Endpunkt";
    case "circle": return index === 0 ? "Mittelpunkt" : "Radius";
    case "ellipse": return index === 0 ? "Mittelpunkt"
      : (index === 1 || index === 3 ? "Hauptachse" : "Nebenachse");
    case "arc": return index === 0 ? "Mittelpunkt" : "Bogenende";
    case "polyline": case "hatch": return "Eckpunkt";
    case "dim": return index === 2 ? "Lage der Maßlinie" : "Messpunkt";
    case "leader": return index === 0 ? "Pfeilspitze" : "Textlage";
    case "insert": return "Block verschieben";
    default: return "Punkt";
  }
}
