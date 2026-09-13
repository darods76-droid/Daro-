// Zugriff auf den Python-Kern (Export, Extrusion, Ansichten, FreeCAD).

async function call(path, body, method = "POST") {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined && method !== "GET") opts.body = JSON.stringify(body);
  let response;
  try {
    response = await fetch(path, opts);
  } catch (err) {
    throw new Error("Kein Kontakt zum DARO-CAD-Dienst. Laeuft 'python3 -m daro_cad'?");
  }
  let data;
  try {
    data = await response.json();
  } catch (err) {
    throw new Error(`Unerwartete Antwort (HTTP ${response.status}).`);
  }
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

export const status = () => call("/api/status", undefined, "GET");
export const listFiles = () => call("/api/files", undefined, "GET");
export const load = (name) => call(`/api/file?name=${encodeURIComponent(name)}`, undefined, "GET");
export const save = (name, document) => call("/api/file", { name, document });
export const solids = (payload) => call("/api/solids", payload);
export const views = (payload) => call("/api/views", payload);
export const importFile = (filename, data) => call("/api/import", { filename, data });
export const exportAs = (format, payload) => call(`/api/export/${format}`, payload);

/** Base64-Antwort als Datei im Browser speichern. */
export async function download(filename, base64, mime) {
  const bin = atob(base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
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
