# Prüft jede Widget-Abfrage des Dashboards einzeln über die Statement Execution API:
# Felder und Aggregation wie im Widget, GROUP BY über die nicht aggregierten Felder,
# Dataset-Parameter mit ihrem Standardwert. Meldet Fehler und leere Ergebnisse.
# Aufruf aus dem Repo-Root: python3 dashboard/check_widgets.py   (Exit-Code 1 bei Problemen)
# Warehouse: DATABRICKS_WAREHOUSE_ID, sonst das erste Warehouse im Workspace.
import json, os, re, subprocess, sys
from pathlib import Path

DASH = json.loads(Path(__file__).with_name("opendata_quality.lvdash.json").read_text(encoding="utf-8"))
DATASETS = {d["name"]: d for d in DASH["datasets"]}

def cli(*args, body=None):
    cmd = ["databricks", *args, "-o", "json"]
    if body is not None:
        cmd += ["--json", json.dumps(body)]
    return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)

WAREHOUSE = os.environ.get("DATABRICKS_WAREHOUSE_ID") or cli("warehouses", "list")[0]["id"]

def dataset_sql(name):
    ds = DATASETS[name]
    sql = "".join(ds["queryLines"])
    for p in ds.get("parameters", []):
        value = p["defaultSelection"]["values"]["values"][0]["value"].replace("'", "''")
        sql = re.sub(rf":{p['keyword']}\b", f"'{value}'", sql)
    return sql

def widget_sql(q):
    fields = q.get("fields", [])
    if not fields:  # reine Parameter-Abfrage eines Filters: Dataset selbst prüfen
        return f"SELECT * FROM ({dataset_sql(q['datasetName'])}) t"
    exprs, dims = [], []
    for f in fields:
        # Filter-Hilfsspalte gibt es nur im Dashboard, hier durch COUNT(*) ersetzen
        e = f["expression"].replace("COUNT_IF(`associative_filter_predicate_group`)", "COUNT(*)")
        exprs.append(f"{e} AS `{f['name']}`")
        if re.fullmatch(r"`[^`]+`", e):
            dims.append(e)
    sql = f"SELECT {', '.join(exprs)} FROM ({dataset_sql(q['datasetName'])}) t"
    if not q.get("disaggregated", False) and dims and len(dims) < len(fields):
        sql += " GROUP BY " + ", ".join(dims)
    return sql

def run(sql):
    r = cli("api", "post", "/api/2.0/sql/statements",
            body={"statement": sql, "warehouse_id": WAREHOUSE, "wait_timeout": "50s"})
    if r["status"]["state"] != "SUCCEEDED":
        return None, r["status"].get("error", {}).get("message", r["status"]["state"])[:200]
    return r.get("result", {}).get("data_array", []), None

problems = 0
for page in DASH["pages"]:
    for item in page["layout"]:
        w = item["widget"]
        if "queries" not in w:
            continue
        title = w.get("spec", {}).get("frame", {}).get("title", w["name"])
        for q in w["queries"]:
            rows, err = run(widget_sql(q["query"]))
            status = f"FEHLER: {err}" if err else ("LEER" if not rows else f"{len(rows)} Zeilen")
            if err or not rows:
                problems += 1
            sample = "" if err or not rows else f"  z. B. {rows[0][:4]}"
            print(f"[{page['displayName']}] {title} ({q['query']['datasetName']}): {status}{sample}")
# Ankerwerte (Snapshot 13.11.2026), auch auf der Ergebnisseite und in der Präsentation
print("\nAnkerwerte")
def anchor(label, ok, detail):
    global problems
    problems += not ok
    print(f"  {'OK    ' if ok else 'FEHLER'} {label} {detail}")
rows, err = run(f"SELECT group_name, machine_readable_pct FROM ({dataset_sql('ds_q4c')}) t")
q4c = {} if err else {g: float(v) for g, v in rows}
anchor("Q4c High-Value-Angebote 54,3 %", q4c.get("High-Value-Angebot") == 54.3, f"(Widget: {q4c or err})")
anchor("Q4c übrige Angebote 84,6 %", q4c.get("übrige") == 84.6, f"(Widget: {q4c or err})")
rows, err = run("SELECT without_machine_readable, offer_count FROM workspace.opendata.q4c_offers_machine_readable "
                "WHERE dimension = 'Quelle' AND group_name = 'FIS-Broker'")
anchor("Q4c FIS-Broker 318 von 982 ohne maschinenlesbare Variante", rows == [["318", "982"]], f"(View: {rows or err})")
befunde = "".join(l for page in DASH["pages"] for item in page["layout"]
                  for l in item["widget"].get("multilineTextboxSpec", {}).get("lines", []))
for text in ("(95 von 208)", "(15,4\u00a0%)", "Bei 32\u00a0% der Geodaten-Angebote (318 von 982)"):
    anchor(f"Befundtext enthält {text!r}", text in befunde, "")

print(f"\n{problems} Problem(e)")
sys.exit(1 if problems else 0)
