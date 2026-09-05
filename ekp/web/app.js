'use strict';

const state = { assessments: [], filter: 'ALLE', showPast: false, board: null };

const $ = (sel) => document.querySelector(sel);
const pct = (v) => `${Math.round((v || 0) * 100)}%`;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

const SHORT = {
  BESTAETIGT: 'Prognose bestätigt',
  WIDERLEGT_HOEHER: 'widerlegt – höher',
  WIDERLEGT_NIEDRIGER: 'widerlegt – tiefer',
  UNBESTAETIGT: 'unbestätigt',
};

function fmtValue(value, unit) {
  if (value === null || value === undefined) return '–';
  const num = Number(value);
  const text = Number.isFinite(num) ? String(Number(num.toFixed(4))) : String(value);
  if (unit === '%') return `${text}%`;
  return unit ? `${text} ${unit}` : text;
}

function fmtWhen(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16);
  return d.toLocaleString('de-DE', {
    weekday: 'short', day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

function setStatus(text, busy = false) {
  $('#status').textContent = text;
  $('#scan').disabled = busy;
  $('#scan').textContent = busy ? 'Scanne …' : 'Jetzt scannen';
}

// ── Rendern ──────────────────────────────────────────────────────────────────
function renderStats() {
  const rows = state.assessments;
  const count = (v) => rows.filter((r) => r.verdict === v).length;
  const board = state.board || {};
  const hit = board.hit_rate === null || board.hit_rate === undefined
    ? '–' : pct(board.hit_rate);
  const cards = [
    ['Termine im Blick', rows.length],
    ['Prognose bestätigt', count('BESTAETIGT')],
    ['widerlegt (höher)', count('WIDERLEGT_HOEHER')],
    ['widerlegt (tiefer)', count('WIDERLEGT_NIEDRIGER')],
    ['Trefferquote bisher', hit],
    ['Nachrichten gescannt', (board.counts && board.counts.news) || 0],
  ];
  $('#stats').innerHTML = cards
    .map(([label, value]) => `<div class="stat"><b>${esc(value)}</b><span>${esc(label)}</span></div>`)
    .join('');
}

function evidenceHtml(list) {
  if (!list || !list.length) {
    return '<p class="note">Keine thematisch passenden Meldungen im Zeitfenster.</p>';
  }
  return list.map((e) => {
    const up = e.direction > 0;
    const link = e.url
      ? `<a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.headline)}</a>`
      : esc(e.headline);
    return `<div class="ev">
      <span class="dir ${up ? 'up' : 'down'}">${up ? '▲' : '▼'} ${e.strength.toFixed(2)}</span>
      <span>${link}
        <div class="src">${esc(e.source)} · ${fmtWhen(e.published)} ·
          <span class="sig">${esc((e.signals || []).join(', '))}</span></div>
      </span>
    </div>`;
  }).join('');
}

function cardHtml(row) {
  const ev = row.event;
  const unit = ev.unit || '';
  const a = row.p_above, cf = row.p_confirm, b = row.p_below;

  let verif = '';
  if (row.verification) {
    const v = row.verification;
    const cls = v.hit === 1 ? 'hit' : (v.hit === 0 ? 'miss' : '');
    const mark = v.hit === 1 ? '✔ Treffer' : (v.hit === 0 ? '✘ daneben' : '– nicht wertbar');
    verif = `<div class="verif ${cls}">Veröffentlicht: <b>${fmtValue(ev.actual, unit)}</b>
      gegenüber Prognose ${fmtValue(ev.forecast, unit)}
      (${v.z >= 0 ? '+' : ''}${Number(v.z).toFixed(2)} σ) — ${mark}</div>`;
  }

  const notes = (row.notes || []).length
    ? `<p class="note">${esc(row.notes.join(' '))}</p>` : '';

  return `<article class="card v-${esc(row.verdict)}">
    <div class="card-head">
      <div>
        <div class="when">${fmtWhen(ev.when)}</div>
        <h2 class="title">${esc(ev.title)}</h2>
        <div class="tags">
          <span class="tag">${esc(ev.country || '–')}</span>
          <span class="tag">${'★'.repeat(ev.importance || 0) || '–'}</span>
          <span class="tag">${esc(row.family)}</span>
          <span class="tag">${row.evidence_count === 1 ? "1 Beleg" : row.evidence_count + " Belege"}</span>
        </div>
      </div>
      <div class="verdict">
        <div class="label">${esc(SHORT[row.verdict] || row.verdict)}</div>
        <div class="prob">${pct(row.headline_probability)}</div>
        <div class="conf">Konfidenz ${pct(row.confidence)} ·
          erwartet ${row.expected_surprise >= 0 ? '+' : ''}${Number(row.expected_surprise).toFixed(2)} σ</div>
      </div>
    </div>

    <div class="values">
      <span>Prognose <b>${fmtValue(ev.forecast, unit)}</b></span>
      <span>Vorwert <b>${fmtValue(ev.previous, unit)}</b></span>
      <span>Ist <b>${fmtValue(ev.actual, unit)}</b></span>
    </div>

    <div class="dist" role="img" aria-label="Wahrscheinlichkeitsverteilung">
      <i class="a" style="width:${a * 100}%"></i>
      <i class="c" style="width:${cf * 100}%"></i>
      <i class="b" style="width:${b * 100}%"></i>
    </div>
    <div class="dist-legend">
      <span>▲ höher ${pct(a)}</span>
      <span>✔ trifft zu ${pct(cf)}</span>
      <span>▼ tiefer ${pct(b)}</span>
    </div>

    ${notes}${verif}

    <details>
      <summary>Belegende Nachrichten anzeigen (${row.evidence_count})</summary>
      ${evidenceHtml(row.evidence)}
    </details>
  </article>`;
}

function render() {
  renderStats();
  const rows = state.filter === 'ALLE'
    ? state.assessments
    : state.assessments.filter((r) => r.verdict === state.filter);
  $('#cards').innerHTML = rows.map(cardHtml).join('');
  $('#empty').classList.toggle('hidden', rows.length > 0);
  if (!rows.length) {
    $('#empty').textContent = state.assessments.length
      ? 'Kein Termin passt zu diesem Filter.'
      : 'Noch keine Bewertungen. Klicken Sie auf „Jetzt scannen“.';
  }
}

// ── Daten ────────────────────────────────────────────────────────────────────
async function load() {
  const upcoming = state.showPast ? '0' : '1';
  const [assess, board] = await Promise.all([
    fetch(`/api/assessments?upcoming=${upcoming}`).then((r) => r.json()),
    fetch('/api/scoreboard').then((r) => r.json()),
  ]);
  state.assessments = assess.assessments || [];
  state.board = board;
  const c = board.counts || {};
  $('#meta').textContent =
    `${c.events || 0} Termine · ${c.news || 0} Nachrichten · ${c.assessments || 0} Bewertungen · `
    + `${c.verifications || 0} überprüft`;
  render();
}

async function runScan() {
  setStatus('Kalender und Nachrichten werden gescannt …', true);
  try {
    const res = await fetch('/api/scan', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    const s = data.summary;
    const warn = (s.warnings || []).length ? ` · ${s.warnings.length} Warnung(en)` : '';
    setStatus(`${s.events_kept} Termine · ${s.news_pool} Nachrichten im Pool${warn}`);
    if ((s.warnings || []).length) console.warn('Scan-Warnungen:', s.warnings);
    await load();
  } catch (err) {
    setStatus(`Fehler: ${err.message}`);
  } finally {
    $('#scan').disabled = false;
    $('#scan').textContent = 'Jetzt scannen';
  }
}

// ── Ereignisse ───────────────────────────────────────────────────────────────
$('#scan').addEventListener('click', runScan);
$('#filters').addEventListener('click', (e) => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  document.querySelectorAll('.chip').forEach((el) => el.classList.remove('active'));
  chip.classList.add('active');
  state.filter = chip.dataset.verdict;
  render();
});
$('#showPast').addEventListener('change', (e) => {
  state.showPast = e.target.checked;
  load();
});

load().catch((err) => setStatus(`Laden fehlgeschlagen: ${err.message}`));
