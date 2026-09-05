// Kleine 3D-Vorschau der extrudierten Koerper (eigener Software-Renderer).
const LIGHT = normalize([0.4, -0.7, 0.6]);

function normalize(v) {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

export class View3D {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.solids = [];
    this.rotX = -62;
    this.rotZ = -35;
    this.zoom = 1;
    this.shaded = true;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.center = [0, 0, 0];
    this.radius = 50;
    this.bindEvents();
  }

  bindEvents() {
    let dragging = false, last = null;
    this.canvas.addEventListener("pointerdown", (e) => {
      dragging = true; last = [e.clientX, e.clientY];
      this.canvas.setPointerCapture(e.pointerId);
    });
    this.canvas.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      this.rotZ += (e.clientX - last[0]) * 0.6;
      this.rotX += (e.clientY - last[1]) * 0.6;
      this.rotX = Math.max(-179, Math.min(1, this.rotX));
      last = [e.clientX, e.clientY];
      this.draw();
    });
    const stop = () => { dragging = false; };
    this.canvas.addEventListener("pointerup", stop);
    this.canvas.addEventListener("pointercancel", stop);
    this.canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.zoom = Math.max(0.15, Math.min(12, this.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
      this.draw();
    }, { passive: false });
  }

  setSolids(solids) {
    this.solids = solids || [];
    const pts = this.solids.flatMap((s) => s.verts || []);
    if (pts.length) {
      const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
      for (const p of pts) {
        for (let i = 0; i < 3; i++) {
          if (p[i] < min[i]) min[i] = p[i];
          if (p[i] > max[i]) max[i] = p[i];
        }
      }
      this.center = [0, 1, 2].map((i) => (min[i] + max[i]) / 2);
      this.radius = Math.max(1, Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]) / 2);
    }
    this.draw();
  }

  rotatePoint(p) {
    const rx = this.rotX * Math.PI / 180, rz = this.rotZ * Math.PI / 180;
    let [x, y, z] = [p[0] - this.center[0], p[1] - this.center[1], p[2] - this.center[2]];
    let nx = x * Math.cos(rz) - y * Math.sin(rz);
    let ny = x * Math.sin(rz) + y * Math.cos(rz);
    const ny2 = ny * Math.cos(rx) - z * Math.sin(rx);
    const nz2 = ny * Math.sin(rx) + z * Math.cos(rx);
    return [nx, ny2, nz2];
  }

  draw() {
    const rect = this.canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    this.canvas.width = Math.round(rect.width * this.dpr);
    this.canvas.height = Math.round(rect.height * this.dpr);
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.fillStyle = "#eef1f5";
    ctx.fillRect(0, 0, rect.width, rect.height);

    if (!this.solids.length) {
      ctx.fillStyle = "#8894a8";
      ctx.font = "13px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Noch kein Körper – Profil wählen und extrudieren", rect.width / 2, rect.height / 2);
      return;
    }

    const scale = Math.min(rect.width, rect.height) / (this.radius * 2.6) * this.zoom;
    const project = (p) => {
      const r = this.rotatePoint(p);
      return [rect.width / 2 + r[0] * scale, rect.height / 2 - r[2] * scale, r[1]];
    };

    const faces = [];
    for (const sol of this.solids) {
      const verts = sol.verts.map(project);
      for (const face of sol.faces) {
        const loop = face.loops[0];
        if (!loop || loop.length < 3) continue;
        const pts = loop.map((i) => verts[i]);
        const depth = pts.reduce((a, p) => a + p[2], 0) / pts.length;
        const n = this.rotatePoint([
          face.normal[0] + this.center[0], face.normal[1] + this.center[1],
          face.normal[2] + this.center[2]]);
        faces.push({ pts, depth, normal: normalize(n),
          holes: face.loops.slice(1).map((l) => l.map((i) => verts[i])) });
      }
    }
    faces.sort((a, b) => b.depth - a.depth);

    if (this.shaded) {
      for (const f of faces) {
        const lambert = Math.abs(f.normal[0] * LIGHT[0] + f.normal[1] * LIGHT[1] +
          f.normal[2] * LIGHT[2]);
        const shade = Math.round(120 + lambert * 110);
        ctx.fillStyle = `rgb(${shade},${Math.round(shade * 0.98)},${Math.round(shade * 0.92)})`;
        ctx.beginPath();
        f.pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
        ctx.closePath();
        for (const hole of f.holes) {
          hole.slice().reverse().forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
          ctx.closePath();
        }
        ctx.fill("evenodd");
      }
    }

    ctx.strokeStyle = "rgba(30,41,59,0.75)";
    ctx.lineWidth = 1;
    for (const sol of this.solids) {
      const verts = sol.verts.map(project);
      ctx.beginPath();
      for (const edge of sol.edges) {
        const a = verts[edge.a], b = verts[edge.b];
        if (edge.faces && edge.faces.length === 2) {
          const n1 = sol.faces[edge.faces[0]].normal, n2 = sol.faces[edge.faces[1]].normal;
          const cos = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2];
          if (cos > 0.94) continue;         // weiche Kanten der Tessellierung
        }
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
      }
      ctx.stroke();
    }
  }
}
