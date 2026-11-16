# Prüft die Zahlen der Ergebnisseite (site/) gegen die Views in Databricks.
#  1. Jede JSON-Datei in site/data/ muss dem aktuellen Inhalt ihrer View bzw. Abfrage entsprechen
#     (d. h. der Export ist nicht veraltet).
#  2. Die Seite wird in headless Chrome gerendert. Alle Elemente mit data-check werden mit Werten
#     verglichen, die dieses Skript unabhängig von der Seite direkt aus den Views berechnet.
#     Die Befundtexte (site/texts.json) werden mit diesen Werten gefüllt und verglichen; zusätzlich wird
#     geprüft, ob die Worte im Text ("Alle", "fast jedes zweite", ...) noch zu den Zahlen passen.
#  3. Ankerwerte, die auch im Dashboard und in der Präsentation stehen (2.595 Datensätze, Ø 74,8, 8,4 % tote Links,
#     Angebote: 54,3 % / 84,6 %, 318 von 982).
#
# Aufruf aus dem Repo-Root: python3 scripts/check_site.py   (Exit-Code 1 bei Abweichungen)
# Braucht: databricks CLI (angemeldet), Node >= 22 und Google Chrome (Pfad über CHROME überschreibbar).
# Die Seite wird über scripts/render_dom.mjs (DevTools-Protokoll) gerendert, weil --dump-dom nicht auf fetch() wartet.
import functools, http.server, json, os, re, subprocess, sys, threading
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_results import QUERIES, VIEWS, run  # noqa: E402
from texts import de, fmt, load_texts, placeholders  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
NBSP = " "
problems = []


def pct(value_in_percent, places=1):
    return de(value_in_percent, places) + NBSP + "%"


def report(ok, label, detail=""):
    print(f"  {'OK    ' if ok else 'FEHLER'} {label}{(' ' + detail) if detail else ''}")
    if not ok:
        problems.append(label)


# ---------------------------------------------------------------- 1. JSON == View
def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(a - b) < 1e-9
    return a == b


def rows_equal(json_rows, view_rows):
    key = lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False)
    a, b = sorted(json_rows, key=key), sorted(view_rows, key=key)
    return len(a) == len(b) and all(r1.keys() == r2.keys() and all(same(r1[k], r2[k]) for k in r1) for r1, r2 in zip(a, b))


print("1. JSON-Dateien gegen aktuelle Views")
for view in VIEWS:
    data = json.loads((SITE / "data" / f"{view}.json").read_text(encoding="utf-8"))
    report(rows_equal(data, run(f"SELECT * FROM {view}")), f"{view}.json", f"({len(data)} Zeilen)")
for name in ("score_by_source", "stromnetz_http", "datasets", "kpis", "findings"):
    data = json.loads((SITE / "data" / f"{name}.json").read_text(encoding="utf-8"))
    fresh = run(QUERIES[name])
    report(rows_equal(data if isinstance(data, list) else [data], fresh), f"{name}.json")

# ---------------------------------------------------------------- 2. Erwartete Werte direkt aus den Views
print("2. Erwartete Werte aus den Views")
e = run("""
SELECT
  (SELECT COUNT(*) FROM v_dataset_score)                                     AS datasets,
  (SELECT ROUND(AVG(quality_score), 1) FROM v_dataset_score)                 AS avg_score,
  (SELECT ROUND(100 * AVG(has_machine_readable), 1) FROM v_dataset_score)    AS mr_pct,
  (SELECT ROUND(100 * (1 - AVG(has_date_updated)), 1) FROM v_dataset_score)  AS nodate_pct,
  (SELECT SUM(checked_resources) FROM q6_link_reachability)                  AS links_checked,
  (SELECT SUM(broken) FROM q6_link_reachability)                             AS links_broken,
  (SELECT ROUND(100.0 * SUM(broken) / SUM(checked_resources), 1) FROM q6_link_reachability) AS broken_pct,
  (SELECT COUNT(*) FROM v_dataset_score WHERE source_system_id = 'harvest-stromnetzberlin')     AS strom_n,
  (SELECT COUNT(*) FROM v_dataset_score WHERE source_system_id = 'harvest-stromnetzberlin'
          AND links_checked > 0 AND links_broken = links_checked)                              AS strom_dead,
  (SELECT AVG(completeness_points) FROM v_dataset_score
          WHERE source_system_id = 'harvest-stromnetzberlin')                                  AS strom_compl,
  (SELECT AVG(completeness_points) FROM v_dataset_score)                                       AS all_compl,
  (SELECT COUNT(*) FROM v_dataset_score WHERE source_system_id = 'harvest-fisbroker')           AS fis_datasets
""")[0]
print("  " + ", ".join(f"{k}={v}" for k, v in e.items()))

# Angebote (Q4c) direkt aus dem View
o = {(r["dimension"], r["group_name"]): r for r in run("SELECT * FROM q4c_offers_machine_readable")}
hvd, rest, fis = o[("HVD", "High-Value-Angebot")], o[("HVD", "übrige")], o[("Quelle", "FIS-Broker")]
print(f"  Angebote: HVD {hvd['with_machine_readable']}/{hvd['offer_count']} ({hvd['machine_readable_pct']}), "
      f"übrige {rest['with_machine_readable']}/{rest['offer_count']} ({rest['machine_readable_pct']}), "
      f"FIS {fis['with_machine_readable']}/{fis['offer_count']}, FIS-Paare {fis['multi_dataset_offers']}")
stromnetz_status = [r["http_status"] for r in run(QUERIES["stromnetz_http"])]

# Werte für die Platzhalter in site/texts.json, unabhängig von findings.json berechnet
values = {
    "stromnetz_datasets": e["strom_n"],
    "stromnetz_avg_completeness": e["strom_compl"],
    "all_avg_completeness": e["all_compl"],
    "hvd_offers": hvd["offer_count"],
    "hvd_offers_not_mr": hvd["without_machine_readable"],
    "rest_offers_not_mr_share": rest["without_machine_readable"] / rest["offer_count"],
    "fis_pairs": fis["multi_dataset_offers"],
    "fis_offers": fis["offer_count"],
    "fis_offers_not_mr": fis["without_machine_readable"],
    "fis_offers_not_mr_share": fis["without_machine_readable"] / fis["offer_count"],
}
texts = load_texts()
used = [(k, kind) for f in texts["findings"] for k, kind in placeholders(f["text"])]
for key in sorted({k for k, _ in used} - set(values)):
    report(False, f"texts.json: {{{key}}}", "ohne Prüfwert im Skript")

# Passen die Worte im Text noch zu den Zahlen?
words = " ".join(f["text"] for f in texts["findings"])
hvd_share = hvd["without_machine_readable"] / hvd["offer_count"]
rest_share = values["rest_offers_not_mr_share"]
for phrase, ok, detail in (
    ("Alle {stromnetz_datasets|int}", e["strom_dead"] == e["strom_n"], f"({e['strom_dead']} von {e['strom_n']} nur tote Links)"),
    ("(HTTP 404)", stromnetz_status == [404], f"(Status: {stromnetz_status})"),
    ("überdurchschnittlich", e["strom_compl"] > e["all_compl"], f"({e['strom_compl']:.2f} > {e['all_compl']:.2f})"),
    ("Fast jedes zweite", 0.4 <= hvd_share < 0.5, f"(Anteil {hvd_share:.3f})"),
    ("etwa jedes siebte", min(range(2, 20), key=lambda n: abs(rest_share - 1 / n)) == 7, f"(Anteil {rest_share:.3f}, 1/7 = 0,143)"),
    ("meist als zwei getrennte Datensätze", 2 * fis["multi_dataset_offers"] > e["fis_datasets"] / 2,
     f"({2 * fis['multi_dataset_offers']} von {e['fis_datasets']} FIS-Datensätzen in Paaren)"),
):
    report(phrase in words and ok, f"Befundtext {phrase!r} passt", detail)

expected = {
    "meta-datasets": de(e["datasets"]),
    "kpi-datasets": de(e["datasets"]),
    "kpi-score": de(e["avg_score"], 1),
    "kpi-mr": pct(e["mr_pct"]),
    "kpi-broken": pct(e["broken_pct"]),
    "kpi-nodate": pct(e["nodate_pct"]),
    "links-share": pct(e["broken_pct"]),
    "links-checked": de(e["links_checked"]),
    "links-broken": de(e["links_broken"]),
    "ds-count": de(e["datasets"]),
    "q4c-hvd-pct": pct(hvd["machine_readable_pct"]),
    "q4c-rest-pct": pct(rest["machine_readable_pct"]),
    **{f"f:{k}": fmt(values[k], kind) for k, kind in used},
}

# ---------------------------------------------------------------- 3. Seite rendern
print("3. Seite in headless Chrome")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
dom = subprocess.run(["node", str(ROOT / "scripts" / "render_dom.mjs"), url], capture_output=True, text=True,
                     timeout=120, env={**os.environ, "CHROME": CHROME}).stdout
server.shutdown()
report('data-ready="true"' in dom, "Seite vollständig geladen (body[data-ready])")


class Checks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values, self.stack = {}, []

    def handle_starttag(self, tag, attrs):
        key = dict(attrs).get("data-check")
        if tag == "span":
            self.stack.append(key)
            if key:
                self.values.setdefault(key, [])
                self.values[key].append("")

    def handle_endtag(self, tag):
        if tag == "span" and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        for key in filter(None, self.stack):
            self.values[key][-1] += data


p = Checks()
p.feed(dom)
found = {k: [re.sub(r"\s+", " ", v.replace(NBSP, " ")).strip() for v in vs] for k, vs in p.values.items()}
for key, want in expected.items():
    got = found.get(key)
    want_n = want.replace(NBSP, " ")
    report(got is not None and all(g == want_n for g in got), f"{key}", f"Seite={got} erwartet={want_n!r}")
for key in sorted(set(found) - set(expected)):
    report(False, f"{key}", "auf der Seite, aber ohne Prüfwert im Skript")

# ---------------------------------------------------------------- 4. Anker
print("4. Ankerwerte (Dashboard/Präsentation)")
for key, want in (("kpi-datasets", "2.595"), ("kpi-score", "74,8"), ("kpi-broken", "8,4 %"),
                  ("q4c-hvd-pct", "54,3 %"), ("q4c-rest-pct", "84,6 %"),
                  ("f:fis_offers_not_mr", "318"), ("f:fis_offers", "982")):
    report(found.get(key, [None])[0] == want, f"{key} = {want}", f"(Seite: {found.get(key)})")

print(f"\n{len(problems)} Abweichung(en)")
sys.exit(1 if problems else 0)
