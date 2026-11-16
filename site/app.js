// Ergebnisseite opendata-quality-watch. Alle Zahlen kommen aus data/*.json
// (erzeugt von scripts/export_results.py). Elemente mit data-check prüft scripts/check_site.py.
// Befund- und Methodiktexte stehen in texts.json (dieselben Texte nutzt das Dashboard).
"use strict";

const FILES = ["meta", "kpis", "findings", "stromnetz_http", "score_by_source", "q1_data_age",
  "q2_time_conflicts", "q3a_series_fragmentation", "q3b_possibly_discontinued", "q4a_format_distribution",
  "q4b_machine_readable_by_source", "q4c_offers_machine_readable", "q6_link_reachability", "q6b_broken_hosts", "q7_harvested_vs_manual",
  "q8_publisher_ranking", "q8b_hvd_vs_rest", "q9_theme_ranking", "datasets"];

// Farben: Referenzpalette (dataviz), feste Reihenfolge
const C = { blue: "#2a78d6", orange: "#eb6834", aqua: "#1baf7a", yellow: "#eda100", gray: "#8a8985",
  lightgray: "#c8c7c1", blue550: "#1c5cab", blue400: "#3987e5", blue300: "#6da7ec", blue250: "#86b6ef" };

// ------------------------------------------------------------ Formatierung (de-DE)
const NBSP = " ";
const nf = {};
function fmt(v, d = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  nf[d] ??= new Intl.NumberFormat("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
  return nf[d].format(v);
}
const pct = (share, d = 1) => fmt(share * 100, d) + NBSP + "%";   // Anteil 0..1
const pctv = (value, d = 1) => fmt(value, d) + NBSP + "%";        // Wert schon in Prozent
function fmtDate(iso) {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}
function fmtDateTime(iso) {
  return new Date(iso).toLocaleString("de-DE", { timeZone: "Europe/Berlin", dateStyle: "medium", timeStyle: "short" }) + " Uhr";
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const chk = (key, html) => `<span data-check="${key}">${html}</span>`;
const $ = (sel) => document.querySelector(sel);

// ------------------------------------------------------------ Texte aus texts.json
// {schluessel|format} wie in scripts/texts.py; jeder Wert wird mit data-check="f:<schluessel>" geprüft.
const FORMATS = { int: (v) => fmt(v), dec1: (v) => fmt(v, 1), pct0: (v) => pct(v, 0), pct1: (v) => pct(v, 1) };
function md(text) {   // nur **fett** und [Text](https://…)
  return esc(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https:\/\/[^)\s]+)\)/g, '<a href="$2">$1</a>');
}
function fill(template, values) {
  return md(template).replace(/\{(\w+)\|(int|dec1|pct0|pct1)\}/g, (_, key, kind) => {
    if (!(key in values)) throw new Error(`texts.json: Wert ${key} fehlt in findings.json`);
    return chk(`f:${key}`, FORMATS[kind](values[key]));
  });
}

// ------------------------------------------------------------ Tabellen
// cols: [feld, Überschrift, formatter?, numerisch?]
function table(target, caption, rows, cols, opts = {}) {
  const head = cols.map(([, h, , n]) => `<th scope="col"${n ? ' class="num"' : ""}>${h}</th>`).join("");
  const body = rows.map((r) => "<tr>" + cols.map(([f, , format, n], i) => {
    const v = format ? format(r[f], r) : esc(r[f]);
    const tag = i === 0 && opts.rowHeader !== false ? 'th scope="row"' : "td";
    return `<${tag}${n ? ' class="num"' : ""}>${v}</${tag.split(" ")[0]}>`;
  }).join("") + "</tr>").join("");
  $(target).innerHTML = `<div class="table-scroll"><table class="data"><caption${opts.visibleCaption ? "" : ' class="sr-only"'}>${esc(caption)}</caption>
    <thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// ------------------------------------------------------------ Diagramme
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.font.size = 13;
Chart.defaults.color = "#4a4945";
Chart.defaults.borderColor = "#e4e3de";
Chart.defaults.animation = false;
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.plugins.tooltip.callbacks.label = (ctx) => {
  const v = ctx.parsed[ctx.chart.options.indexAxis === "y" ? "x" : "y"];
  const unit = ctx.chart.$unit || "";
  return `${ctx.dataset.label ? ctx.dataset.label + ": " : ""}${fmt(v, ctx.chart.$decimals ?? 1)}${unit}`;
};

function chart(id, { labels, datasets, horizontal = false, stacked = false, max, unit = "", decimals = 1,
  legend, aria }) {
  const canvas = document.getElementById(id);
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", aria);
  canvas.textContent = aria;
  const valueAxis = { beginAtZero: true, stacked, max, grid: { color: "#e4e3de" },
    ticks: { callback: (v) => fmt(v, 0) + unit } };
  const catAxis = { stacked, grid: { display: false }, ticks: { autoSkip: false } };
  const c = new Chart(canvas, {
    type: "bar",
    data: { labels, datasets: datasets.map((d) => ({ borderRadius: 3, borderSkipped: false, maxBarThickness: 34,
      borderColor: "#ffffff", borderWidth: stacked ? { top: 0, bottom: 0, left: 0, right: 2 } : 0, ...d })) },
    options: {
      indexAxis: horizontal ? "y" : "x",
      scales: horizontal ? { x: valueAxis, y: catAxis } : { x: catAxis, y: valueAxis },
      plugins: { legend: { display: legend ?? datasets.length > 1, position: "bottom",
        labels: { boxWidth: 12, boxHeight: 12 } } },
    },
  });
  c.$unit = unit;
  c.$decimals = decimals;
  return c;
}

// ------------------------------------------------------------ Abschnitte
function renderMeta(m) {
  const values = {
    snapshot_date: fmtDate(m.snapshot_date),
    datasets_total: fmt(m.datasets_total),
    entries_total: fmt(m.entries_total),
    resources_total: fmt(m.resources_total),
    links_checked: fmt(m.links_checked),
    link_check_coverage: pct(m.link_check_coverage, 1),
    link_check_date: fmtDate(m.link_check_from) + (m.link_check_to.slice(0, 10) !== m.link_check_from.slice(0, 10)
      ? "–" + fmtDate(m.link_check_to) : ""),
    exported_at: fmtDateTime(m.exported_at),
  };
  document.querySelectorAll("[data-bind]").forEach((el) => { el.textContent = values[el.dataset.bind] ?? "–"; });
  document.querySelectorAll("[data-bind-href]").forEach((el) => { el.href = m[el.dataset.bindHref]; });
}

function renderFindings(texts, f) {
  $("#findings-list").innerHTML = texts.findings
    .map((x) => `<li><strong>${esc(x.label)}:</strong> ${fill(x.text, f)}</li>`).join("");
}

function renderMethodTexts(texts) {
  $("#q2-note").innerHTML = `<strong>${esc(texts.q2_note.label)}:</strong> ${md(texts.q2_note.text)}`;
  $("#q2-hint").innerHTML = `${md(texts.q2_note.text)} Siehe <a href="#methodik">Methodik</a>.`;
  $("#q4c-note").textContent = texts.q4c_note;
  const st = texts.stichprobe;
  $("#stichprobe").innerHTML = `<p>${md(st.intro)}</p>
    <ol>${st.cases.map((c) => `<li>${md(c)}</li>`).join("")}</ol>
    <p>Daraus folgten zwei Korrekturen:</p>
    <ul>${st.corrections.map((c) => `<li>${md(c)}</li>`).join("")}</ul>`;
}

function kpiTiles(target, tiles) {
  $(target).innerHTML = tiles.map(([label, key, value, sub]) =>
    `<div><dt>${label}</dt><dd>${chk(key, value)}${sub ? `<small>${sub}</small>` : ""}</dd></div>`).join("");
}

function renderKpis(k) {
  kpiTiles("#kpis", [
    ["Datensätze", "kpi-datasets", fmt(k.datasets)],
    ["Ø Qualitätsscore (mit Links)", "kpi-score", fmt(k.avg_score, 1), `ohne Links: ${fmt(k.avg_score_without_links, 1)}`],
    ["maschinenlesbar", "kpi-mr", pct(k.machine_readable_share), "≥ 1 maschinenlesbare Ressource"],
    ["tote Links", "kpi-broken", pct(k.broken_links_share), `Anteil an geprüften Links (${fmt(k.links_checked)} von ${fmt(k.resources)})`],
    ["ohne Aktualisierungsdatum", "kpi-nodate", pct(k.no_date_updated_share), "Feld date_updated leer"],
  ]);
}

function renderScoreBySource(rows) {
  chart("c-score-source", { labels: rows.map((r) => r.source_label), horizontal: true, max: 100,
    datasets: [{ label: "Ø Score", data: rows.map((r) => r.avg_score), backgroundColor: C.blue }],
    aria: "Balkendiagramm Ø Qualitätsscore je Quelle: " + rows.map((r) => `${r.source_label} ${fmt(r.avg_score, 1)}`).join(", ") });
  table("#t-score-source", "Ø Qualitätsscore je Quelle", rows, [
    ["source_label", "Quelle"], ["dataset_count", "Datensätze", (v) => fmt(v), true],
    ["avg_score", "Ø Score (mit Links)", (v) => fmt(v, 1), true]]);
}

function renderQ7(rows) {
  const parts = [["avg_time", "Zeitangaben", C.blue], ["avg_reach", "Erreichbarkeit", C.orange],
    ["avg_machine", "Maschinenlesbarkeit", C.aqua], ["avg_completeness", "Vollständigkeit", C.yellow]];
  chart("c-q7", { labels: rows.map((r) => r.origin), horizontal: true, stacked: true, max: 100,
    datasets: parts.map(([f, label, color]) => ({ label, data: rows.map((r) => r[f]), backgroundColor: color })),
    aria: "Gestapeltes Balkendiagramm Ø Teilpunkte: " + rows.map((r) =>
      `${r.origin}: ` + parts.map(([f, l]) => `${l} ${fmt(r[f], 1)}`).join(", ")).join("; ") });
  table("#t-q7", "Ø Teilpunkte nach Herkunft", rows, [["origin", "Herkunft"], ["dataset_count", "Datensätze", (v) => fmt(v), true],
    ...parts.map(([f, l]) => [f, l, (v) => fmt(v, 1), true]), ["avg_score", "Ø Score", (v) => fmt(v, 1), true]]);
}

function renderFormats(rows) {
  // wie im Dashboard: Top 12 nach Anzahl Ressourcen, Rest als "übrige Formate"
  const sorted = [...rows].sort((a, b) => b.resource_count - a.resource_count);
  const lesbar = (r) => r.machine_readable === true ? "maschinenlesbar"
    : r.machine_readable === false ? "nicht maschinenlesbar" : "ohne Formatangabe";
  const top = sorted.slice(0, 12).map((r) => ({ format: r.format, cat: lesbar(r), n: r.resource_count }));
  const rest = sorted.slice(12).reduce((s, r) => s + r.resource_count, 0);
  if (rest) top.push({ format: "übrige Formate", cat: "gemischt (übrige)", n: rest });
  top.sort((a, b) => b.n - a.n);
  const cats = [["maschinenlesbar", C.blue], ["nicht maschinenlesbar", C.orange], ["ohne Formatangabe", C.gray],
    ["gemischt (übrige)", C.lightgray]].filter(([c]) => top.some((t) => t.cat === c));
  chart("c-formats", { labels: top.map((t) => t.format.length > 38 ? t.format.slice(0, 36) + "…" : t.format),
    horizontal: true, stacked: true, decimals: 0,
    datasets: cats.map(([c, color]) => ({ label: c, backgroundColor: color, data: top.map((t) => (t.cat === c ? t.n : null)) })),
    aria: "Balkendiagramm Ressourcen je Format: " + top.map((t) => `${t.format} ${fmt(t.n)} (${t.cat})`).join(", ") });
  table("#t-formats", "Ressourcen je Format", sorted, [["format", "Format"],
    ["machine_readable", "maschinenlesbar", (v) => (v === true ? "ja" : v === false ? "nein" : "–")],
    ["resource_count", "Ressourcen", (v) => fmt(v), true], ["share_pct", "Anteil", (v) => pctv(v), true]]);
}

function renderHvd(rows) {
  const order = ["High-Value-Datensatz", "übrige"];
  rows = order.map((g) => rows.find((r) => r.group_name === g)).filter(Boolean);
  chart("c-hvd", { labels: ["Ø Score ohne Links", "% mit maschinenlesbarer Ressource"], max: 100,
    datasets: rows.map((r, i) => ({ label: r.group_name, backgroundColor: [C.blue, C.orange][i],
      data: [r.avg_score_without_links, r.machine_readable_pct] })),
    aria: "Balkendiagramm High-Value-Datensätze vs. übrige: " + rows.map((r) =>
      `${r.group_name} Ø Score ohne Links ${fmt(r.avg_score_without_links, 1)}, maschinenlesbar ${pctv(r.machine_readable_pct)}`).join("; ") });
  table("#t-hvd", "High-Value-Datensätze vs. übrige", rows, [["group_name", "Gruppe"], ["dataset_count", "Datensätze", (v) => fmt(v), true],
    ["avg_score_without_links", "Ø Score ohne Links", (v) => fmt(v, 1), true],
    ["machine_readable_pct", "maschinenlesbar", (v) => pctv(v), true]]);
}

function renderQ4c(rows) {
  const hvd = ["High-Value-Angebot", "übrige"].map((g) => rows.find((r) => r.dimension === "HVD" && r.group_name === g));
  const all = rows.find((r) => r.dimension === "gesamt");
  chart("c-q4c", { labels: hvd.map((r) => r.group_name), max: 100, unit: NBSP + "%", stacked: true,
    datasets: [
      { label: "mit maschinenlesbarer Variante", backgroundColor: C.blue, data: hvd.map((r) => r.machine_readable_pct) },
      { label: "ohne", backgroundColor: C.orange, data: hvd.map((r) => 100 - r.machine_readable_pct) }],
    aria: "Gestapeltes Balkendiagramm Angebote mit maschinenlesbarer Variante: " + hvd.map((r) =>
      `${r.group_name} ${pctv(r.machine_readable_pct)} (${fmt(r.with_machine_readable)} von ${fmt(r.offer_count)})`).join("; ") });
  const keys = { "High-Value-Angebot": "q4c-hvd-pct", "übrige": "q4c-rest-pct" };
  table("#t-q4c", "Angebote mit maschinenlesbarer Variante, High-Value vs. übrige", [...hvd, all], [
    ["group_name", "Gruppe"], ["offer_count", "Angebote", (v) => fmt(v), true],
    ["dataset_count", "Datensätze", (v) => fmt(v), true],
    ["with_machine_readable", "maschinenlesbar", (v) => fmt(v), true],
    ["without_machine_readable", "ohne", (v) => fmt(v), true],
    ["machine_readable_pct", "Anteil", (v, r) => (keys[r.group_name] ? chk(keys[r.group_name], pctv(v)) : pctv(v)), true]]);
}

function renderQ4b(rows) {
  rows = [...rows].sort((a, b) => b.dataset_count - a.dataset_count);
  table("#t-q4b", "Maschinenlesbare Datensätze je Quelle", rows, [["source_label", "Quelle"],
    ["dataset_count", "Datensätze", (v) => fmt(v), true], ["with_machine_readable", "maschinenlesbar", (v) => fmt(v), true],
    ["machine_readable_pct", "Anteil", (v) => pctv(v), true]]);
}

function renderQ1(rows) {
  const buckets = [...new Set(rows.map((r) => r.age_bucket))].sort();
  const colors = { "1": C.orange, "2": C.blue550, "3": C.blue400, "4": C.blue300, "5": C.blue250 };
  const sources = [...new Set(rows.map((r) => r.source_label))]
    .sort((a, b) => sum(rows, b) - sum(rows, a));
  function sum(rs, s) { return rs.filter((r) => r.source_label === s).reduce((t, r) => t + r.dataset_count, 0); }
  const label = (b) => b.replace(/^\d /, "") === "fehlt" ? "Datum fehlt" : b.replace(/^\d /, "");
  const val = (s, b) => rows.find((r) => r.source_label === s && r.age_bucket === b)?.share_in_source_pct ?? null;
  chart("c-q1", { labels: sources, horizontal: true, stacked: true, max: 100, unit: NBSP + "%",
    datasets: buckets.map((b) => ({ label: label(b), backgroundColor: colors[b[0]] || C.gray, data: sources.map((s) => val(s, b)) })),
    aria: "Gestapeltes Balkendiagramm Datenstand je Quelle in Prozent: " + sources.map((s) =>
      `${s}: ` + buckets.filter((b) => val(s, b) !== null).map((b) => `${label(b)} ${fmt(val(s, b), 1)} %`).join(", ")).join("; ") });
  table("#t-q1", "Datenstand je Quelle", rows.map((r) => ({ ...r, age_bucket: label(r.age_bucket) })),
    [["source_label", "Quelle"], ["age_bucket", "Datenstand"], ["dataset_count", "Datensätze", (v) => fmt(v), true],
      ["share_in_source_pct", "Anteil in der Quelle", (v) => pctv(v), true]]);
}

function renderQ2(rows) {
  table("#t-q2", "Widersprüchliche Zeitangaben je Regel und Quelle", rows, [["rule", "Regel"], ["source_label", "Quelle"],
    ["dataset_count", "Datensätze", (v) => fmt(v), true]]);
}

function renderQ3(rowsA, rowsB) {
  rowsA = [...rowsA].sort((a, b) => b.in_series_pct - a.in_series_pct);
  chart("c-q3a", { labels: rowsA.map((r) => r.source_label), max: 100, unit: NBSP + "%",
    datasets: [{ label: "Anteil in Zeitreihen", data: rowsA.map((r) => r.in_series_pct), backgroundColor: C.blue }],
    aria: "Balkendiagramm Anteil Datensätze in Zeitreihen je Quelle: " + rowsA.map((r) => `${r.source_label} ${fmt(r.in_series_pct, 1)} %`).join(", ") });
  table("#t-q3a", "Anteil Datensätze in Zeitreihen je Quelle", rowsA, [["source_label", "Quelle"],
    ["dataset_count", "Datensätze", (v) => fmt(v), true], ["in_series", "in Zeitreihen", (v) => fmt(v), true],
    ["in_series_pct", "Anteil", (v) => pctv(v), true], ["series_count", "Reihen", (v) => fmt(v), true]]);
  table("#t-q3b", "Geprüfte Reihen, die womöglich eingestellt sind", rowsB, [["series_key", "Reihe"],
    ["datasets", "Jahrgänge", (v) => fmt(v), true], ["first_year", "erster Jahrgang", (v) => String(v), true],
    ["last_year", "letzter Jahrgang", (v) => String(v), true]]);
}

function renderLinks(rows, hosts) {
  const checked = rows.reduce((s, r) => s + r.checked_resources, 0);
  const broken = rows.reduce((s, r) => s + r.broken, 0);
  kpiTiles("#kpis-links", [
    ["tote Links (alle geprüften Ressourcen)", "links-share", pct(broken / checked)],
    ["geprüfte Links", "links-checked", fmt(checked)],
    ["davon tot", "links-broken", fmt(broken)],
  ]);
  rows = rows.map((r) => ({ ...r, share: (100 * r.broken) / r.checked_resources })).sort((a, b) => b.share - a.share);
  chart("c-q6", { labels: rows.map((r) => r.source_label), unit: NBSP + "%", max: 100,
    datasets: [{ label: "tote Links", data: rows.map((r) => r.share), backgroundColor: C.orange }],
    aria: "Balkendiagramm Anteil toter Links je Quelle: " + rows.map((r) => `${r.source_label} ${fmt(r.share, 1)} %`).join(", ") });
  table("#t-q6", "Anteil toter Links je Quelle", rows, [["source_label", "Quelle"],
    ["checked_resources", "geprüft", (v) => fmt(v), true], ["reachable", "erreichbar", (v) => fmt(v), true],
    ["broken", "tot", (v) => fmt(v), true], ["broken_pct", "Anteil tot", (v) => pctv(v), true]]);
  hosts = [...hosts].sort((a, b) => b.broken - a.broken || b.checked_links - a.checked_links);
  table("#t-q6b", "Hosts mit den meisten defekten Links", hosts, [["host", "Host"],
    ["checked_links", "geprüfte Links", (v) => fmt(v), true], ["broken", "defekt", (v) => fmt(v), true],
    ["broken_pct", "Anteil defekt", (v) => pctv(v), true]]);
}

function renderPublishers(rows, themes) {
  rows = [...rows].sort((a, b) => (a.avg_score ?? 999) - (b.avg_score ?? 999));
  table("#t-q8", "Bereitsteller mit mindestens 10 Datensätzen", rows, [
    ["publisher_short", "Bereitsteller", (v, r) => `<abbr title="${esc(r.publisher_name)}">${esc(v)}</abbr>`],
    ["dataset_count", "n", (v) => fmt(v), true], ["avg_score", "Ø Score", (v) => fmt(v, 1), true],
    ["avg_time", "Ø Zeit", (v) => fmt(v, 1), true], ["avg_reach", "Ø Erreichb.", (v) => fmt(v, 1), true],
    ["avg_machine", "Ø Maschinenl.", (v) => fmt(v, 1), true], ["avg_completeness", "Ø Vollst.", (v) => fmt(v, 1), true]]);
  themes = [...themes].sort((a, b) => a.avg_score - b.avg_score);
  chart("c-q9", { labels: themes.map((t) => t.theme), horizontal: true, max: 100,
    datasets: [{ label: "Ø Score", data: themes.map((t) => t.avg_score), backgroundColor: C.blue }],
    aria: "Balkendiagramm Ø Qualitätsscore je Thema: " + themes.map((t) => `${t.theme} ${fmt(t.avg_score, 1)}`).join(", ") });
  table("#t-q9", "Ø Qualitätsscore je Thema", themes, [["theme", "Thema"], ["dataset_count", "Datensätze", (v) => fmt(v), true],
    ["avg_score", "Ø Score (mit Links)", (v) => fmt(v, 1), true], ["avg_score_without_links", "Ø Score ohne Links", (v) => fmt(v, 1), true]]);
}

// ------------------------------------------------------------ Datensatz-Tabelle
const PAGE = 100;
function setupDatasets(rows) {
  const fill = (sel, values) => { $(sel).insertAdjacentHTML("beforeend",
    values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("")); };
  const uniq = (f) => [...new Set(rows.map((r) => r[f]).filter(Boolean))].sort((a, b) => a.localeCompare(b, "de"));
  fill("#f-source", uniq("source_label"));
  fill("#f-publisher", uniq("publisher_short"));
  let shown = PAGE, filtered = rows;
  const tbody = $("#ds-table tbody");

  function row(r) {
    const score = r.quality_score === null
      ? `<span title="Links nicht geprüft">–</span><br><small>ohne Links ${fmt(r.quality_score_without_links, 1)}</small>`
      : fmt(r.quality_score, 1);
    return `<tr><td class="num">${score}</td>
      <td><a href="https://daten.berlin.de/datensaetze/${encodeURIComponent(r.name)}">${esc(r.title)}</a></td>
      <td>${esc(r.publisher_short)}</td><td>${esc(r.source_label)}</td>
      <td class="num">${fmt(r.time_points, 0)}</td><td class="num">${fmt(r.reach_points, 1)}</td>
      <td class="num">${fmt(r.machine_points, 0)}</td><td class="num">${fmt(r.completeness_points, 0)}</td>
      <td>${esc(r.reasons ?? "–")}</td></tr>`;
  }
  function render() {
    tbody.innerHTML = filtered.slice(0, shown).map(row).join("");
    $("#ds-count").innerHTML = `${chk("ds-count", fmt(filtered.length))} von ${fmt(rows.length)} Datensätzen`
      + (filtered.length > shown ? `, die ersten ${fmt(shown)} werden angezeigt` : "");
    $("#ds-more").hidden = filtered.length <= shown;
  }
  function apply() {
    const q = $("#f-text").value.trim().toLowerCase();
    const src = $("#f-source").value, pub = $("#f-publisher").value;
    filtered = rows.filter((r) => (!src || r.source_label === src) && (!pub || r.publisher_short === pub)
      && (!q || r.title.toLowerCase().includes(q) || r.name.includes(q)));
    shown = PAGE;
    render();
  }
  ["#f-text", "#f-source", "#f-publisher"].forEach((s) => $(s).addEventListener("input", apply));
  $("#ds-more").addEventListener("click", () => { shown += PAGE; render(); });
  render();
}

// ------------------------------------------------------------ Start
async function main() {
  const load = async (path) => {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
  };
  const entries = await Promise.all(FILES.map(async (f) => [f, await load(`data/${f}.json`)]));
  const d = Object.fromEntries(entries);
  const texts = await load("texts.json");
  renderMeta(d.meta);
  renderFindings(texts, d.findings);
  renderMethodTexts(texts);
  renderKpis(d.kpis);
  renderScoreBySource(d.score_by_source);
  renderQ7(d.q7_harvested_vs_manual);
  renderFormats(d.q4a_format_distribution);
  renderHvd(d.q8b_hvd_vs_rest);
  renderQ4c(d.q4c_offers_machine_readable);
  renderQ4b(d.q4b_machine_readable_by_source);
  renderQ1(d.q1_data_age);
  renderQ2(d.q2_time_conflicts);
  renderQ3(d.q3a_series_fragmentation, d.q3b_possibly_discontinued);
  renderLinks(d.q6_link_reachability, d.q6b_broken_hosts);
  renderPublishers(d.q8_publisher_ranking, d.q9_theme_ranking);
  setupDatasets(d.datasets);
  document.body.dataset.ready = "true";
}

main().catch((e) => {
  const el = $("#ladefehler");
  el.hidden = false;
  el.textContent = "Die Daten konnten nicht geladen werden: " + e.message;
  console.error(e);
});
