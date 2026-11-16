# Exportiert die Ergebnisse aus Databricks als JSON für die statische Ergebnisseite (site/).
# Führt alle q*-Views, ein paar Kennzahl-Abfragen auf v_dataset_score und eine schlanke
# Datensatzliste über die Statement Execution API aus und schreibt site/data/*.json und
# site/data/meta.json. Es werden keine Personendaten exportiert (kein maintainer, keine E-Mail).
#
# Aufruf aus dem Repo-Root: python3 scripts/export_results.py
# Braucht: databricks CLI (angemeldet), Views aus sql/analysis/ (deploy_databricks.sh analysis).
# Warehouse: DATABRICKS_WAREHOUSE_ID, sonst das erste Warehouse im Workspace.
import json, os, subprocess, sys, time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data"
CATALOG, SCHEMA = "workspace", "opendata"

VIEWS = [
    "q1_data_age", "q2_time_conflicts", "q3a_series_fragmentation", "q3b_possibly_discontinued",
    "q4a_format_distribution", "q4b_machine_readable_by_source", "q4c_offers_machine_readable",
    "q5_completeness",
    "q6_link_reachability", "q6b_broken_hosts", "q7_harvested_vs_manual",
    "q8_publisher_ranking", "q8b_hvd_vs_rest", "q9_theme_ranking",
]

# Zusätzliche Abfragen; dieselben Ausdrücke wie die Kacheln im Dashboard (dashboard/build_dashboard.py)
QUERIES = {
    "kpis": """
SELECT COUNT(dataset_id)                          AS datasets,
       AVG(quality_score)                         AS avg_score,
       AVG(quality_score_without_links)           AS avg_score_without_links,
       AVG(has_machine_readable)                  AS machine_readable_share,
       SUM(links_broken) / SUM(links_checked)     AS broken_links_share,
       SUM(links_checked)                         AS links_checked,
       SUM(links_broken)                          AS links_broken,
       SUM(resource_count)                        AS resources,
       1 - AVG(has_date_updated)                  AS no_date_updated_share
FROM v_dataset_score""",
    "score_by_source": """
SELECT source_label, COUNT(*) AS dataset_count, AVG(quality_score) AS avg_score
FROM v_dataset_score
WHERE source_label <> 'unbekannt'
GROUP BY source_label
ORDER BY avg_score DESC""",
    # Zahlen für die "Wichtigsten Befunde"; Texte in site/texts.json (gleiche Texte im Dashboard)
    "findings": """
SELECT s.*, o.*
FROM (
  SELECT
    -- Stromnetz Berlin
    SUM(CASE WHEN source_system_id = 'harvest-stromnetzberlin' THEN 1 ELSE 0 END)            AS stromnetz_datasets,
    SUM(CASE WHEN source_system_id = 'harvest-stromnetzberlin' AND links_checked > 0
              AND links_broken = links_checked THEN 1 ELSE 0 END)                             AS stromnetz_all_links_broken,
    AVG(CASE WHEN source_system_id = 'harvest-stromnetzberlin' THEN completeness_points END) AS stromnetz_avg_completeness,
    AVG(completeness_points)                                                                  AS all_avg_completeness
  FROM v_dataset_score
) s
CROSS JOIN (
  -- Angebote (WMS/WFS-Zwillinge zusammengefasst), Q4c
  SELECT
    MAX(CASE WHEN dimension = 'HVD' AND group_name = 'High-Value-Angebot' THEN offer_count END)              AS hvd_offers,
    MAX(CASE WHEN dimension = 'HVD' AND group_name = 'High-Value-Angebot' THEN without_machine_readable END) AS hvd_offers_not_mr,
    MAX(CASE WHEN dimension = 'HVD' AND group_name = 'übrige' THEN offer_count END)                          AS rest_offers,
    MAX(CASE WHEN dimension = 'HVD' AND group_name = 'übrige' THEN without_machine_readable / offer_count END) AS rest_offers_not_mr_share,
    MAX(CASE WHEN dimension = 'Quelle' AND group_name = 'FIS-Broker' THEN multi_dataset_offers END)         AS fis_pairs,
    MAX(CASE WHEN dimension = 'Quelle' AND group_name = 'FIS-Broker' THEN offer_count END)                  AS fis_offers,
    MAX(CASE WHEN dimension = 'Quelle' AND group_name = 'FIS-Broker' THEN without_machine_readable END)     AS fis_offers_not_mr,
    MAX(CASE WHEN dimension = 'Quelle' AND group_name = 'FIS-Broker' THEN without_machine_readable / offer_count END) AS fis_offers_not_mr_share
  FROM q4c_offers_machine_readable
) o""",
    "stromnetz_http": """
SELECT l.http_status, COUNT(*) AS links
FROM v_latest_link_check l
JOIN resource r       ON r.resource_id = l.resource_id
JOIN v_dataset_base b ON b.dataset_id  = r.dataset_id
WHERE b.source_system_id = 'harvest-stromnetzberlin' AND NOT l.is_reachable
GROUP BY l.http_status
ORDER BY links DESC""",
    # Schlanke Datensatzliste: keine Personendaten, keine Langnamen von Bereitstellern
    "datasets": """
SELECT title, name, publisher_short, source_label,
       quality_score, quality_score_without_links,
       time_points, reach_points, machine_points, completeness_points, reasons
FROM v_dataset_score
ORDER BY quality_score ASC NULLS LAST, title""",
    "meta_run": """
SELECT h.snapshot_date, h.datasets_total AS entries_total, h.datasets_loaded AS datasets_total,
       h.resources_loaded AS resources_total,
       (SELECT MIN(checked_at) FROM link_check) AS link_check_from,
       (SELECT MAX(checked_at) FROM link_check) AS link_check_to,
       (SELECT COUNT(*) FROM v_latest_link_check) AS links_checked
FROM harvest_run h
ORDER BY h.harvest_run_id DESC
LIMIT 1""",
}


def cli(*args, body=None):
    cmd = ["databricks", *args, "-o", "json"]
    if body is not None:
        cmd += ["--json", json.dumps(body)]
    return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)


WAREHOUSE = os.environ.get("DATABRICKS_WAREHOUSE_ID") or cli("warehouses", "list")[0]["id"]

NUMERIC = {"INT", "BIGINT", "SMALLINT", "TINYINT", "LONG", "SHORT", "BYTE"}
DECIMAL = {"DECIMAL", "DOUBLE", "FLOAT"}


def convert(value, type_name):
    if value is None:
        return None
    if type_name in NUMERIC:
        return int(value)
    if type_name in DECIMAL:
        return float(Decimal(value))
    if type_name == "BOOLEAN":
        return value == "true"
    return value


def run(sql):
    """Führt eine Abfrage aus und liefert eine Liste von Dicts (alle Ergebnis-Chunks)."""
    r = cli("api", "post", "/api/2.0/sql/statements",
            body={"statement": sql, "warehouse_id": WAREHOUSE, "catalog": CATALOG, "schema": SCHEMA,
                  "wait_timeout": "50s", "on_wait_timeout": "CONTINUE",
                  "disposition": "INLINE", "format": "JSON_ARRAY"})
    sid = r["statement_id"]
    while r["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(3)
        r = cli("api", "get", f"/api/2.0/sql/statements/{sid}")
    if r["status"]["state"] != "SUCCEEDED":
        sys.exit(f"FEHLER: {r['status'].get('error', {}).get('message', r['status']['state'])}\n{sql}")
    cols = [(c["name"], c["type_name"]) for c in r["manifest"]["schema"]["columns"]]
    rows = list(r.get("result", {}).get("data_array", []))
    chunk = r.get("result", {}).get("next_chunk_index")
    while chunk is not None:
        part = cli("api", "get", f"/api/2.0/sql/statements/{sid}/result/chunks/{chunk}")
        rows += part.get("data_array", [])
        chunk = part.get("next_chunk_index")
    return [{n: convert(v, t) for (n, t), v in zip(cols, row)} for row in rows]


def write(name, data):
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    n = len(data) if isinstance(data, list) else 1
    print(f"  {path.relative_to(ROOT)}: {n} Zeile(n)")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Export nach {OUT.relative_to(ROOT)} (Warehouse {WAREHOUSE})")
    for view in VIEWS:
        write(view, run(f"SELECT * FROM {view}"))
    results = {name: run(sql) for name, sql in QUERIES.items()}
    for name in ("score_by_source", "stromnetz_http", "datasets"):
        write(name, results[name])
    write("kpis", results["kpis"][0])
    write("findings", results["findings"][0])

    m = results["meta_run"][0]
    meta = {
        "snapshot_date": m["snapshot_date"],
        "entries_total": m["entries_total"],
        "datasets_total": m["datasets_total"],
        "resources_total": m["resources_total"],
        "link_check_from": m["link_check_from"],
        "link_check_to": m["link_check_to"],
        "links_checked": m["links_checked"],
        "link_check_coverage": m["links_checked"] / m["resources_total"],
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Berlin Open Data (datenregister.berlin.de)",
        "repository": "https://github.com/TimGehring/opendata-quality-watch",
    }
    write("meta", meta)


if __name__ == "__main__":
    main()
