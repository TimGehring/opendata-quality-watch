#!/usr/bin/env bash
# Deploy opendata-quality-watch to Databricks (Free Edition, serverless) via the Databricks CLI.
#
#   1. setup   create schema workspace.opendata and volume raw (idempotent)
#   2. upload  copy data/tables/*.csv and sql/schema.sql into the volume (scripts/upload.sh)
#   3. load    rebuild all tables (sql/schema.sql) and load them (notebooks/01_load_tables.sql)
#   4. verify  compare row counts in Databricks with the local CSV files
#   5. analysis  create/replace all views from sql/analysis/*.sql
#   6. dashboard build dashboard/opendata_quality.lvdash.json and create or update the
#                AI/BI dashboard (ID in dashboard/dashboard_id.txt), then publish it
#
# Usage:   ./scripts/deploy_databricks.sh [all|setup|upload|load|verify|analysis|dashboard]   (default: all)
# Needs:   databricks CLI (logged in via `databricks auth login`), jq, python3,
#          data/tables/*.csv (harvester/transform.py).
# Options: DATABRICKS_WAREHOUSE_ID  SQL warehouse to use (default: first warehouse in the workspace)
#          DATABRICKS_CONFIG_PROFILE  CLI profile (standard CLI variable)
#
# SQL statements run one per request through the Statement Execution API. The script stops
# at the first statement that does not finish with SUCCEEDED and prints the error.
set -euo pipefail

cd "$(dirname "$0")/.."

CATALOG="workspace"
SCHEMA="opendata"
TABLES=(harvest_run publisher publisher_alias source_system license hvd_category theme
        series format format_alias dataset dataset_theme resource link_check)

WAREHOUSE_ID="${DATABRICKS_WAREHOUSE_ID:-}"
if [ -z "$WAREHOUSE_ID" ]; then
  WAREHOUSE_ID=$(databricks warehouses list -o json | jq -r '.[0].id // empty')
  [ -n "$WAREHOUSE_ID" ] || { echo "No SQL warehouse found." >&2; exit 1; }
fi

# run_sql <statement> -> prints the result rows as JSON array (data_array), exits on failure
run_sql() {
  local statement="$1" body response state id
  body=$(jq -n --arg s "$statement" --arg w "$WAREHOUSE_ID" --arg c "$CATALOG" --arg d "$SCHEMA" \
    '{statement: $s, warehouse_id: $w, catalog: $c, schema: $d,
      wait_timeout: "50s", on_wait_timeout: "CONTINUE"}')
  response=$(databricks api post /api/2.0/sql/statements --json "$body")
  id=$(jq -r '.statement_id' <<<"$response")
  state=$(jq -r '.status.state' <<<"$response")
  while [ "$state" = "PENDING" ] || [ "$state" = "RUNNING" ]; do
    sleep 5
    response=$(databricks api get "/api/2.0/sql/statements/$id")
    state=$(jq -r '.status.state' <<<"$response")
  done
  if [ "$state" != "SUCCEEDED" ]; then
    echo "FAILED ($state): $(head -c 200 <<<"$statement" | tr '\n' ' ')..." >&2
    jq -r '.status.error | "\(.error_code): \(.message)"' <<<"$response" >&2
    exit 1
  fi
  jq -c '.result.data_array // []' <<<"$response"
}

# run_sql_file <file>: drop comment lines (incl. Databricks MAGIC cells), split on ';',
# skip USE statements (catalog/schema are set per request) and run the rest in order.
run_sql_file() {
  local file="$1" count=0 statement
  echo "== $file"
  while IFS= read -r -d '' statement; do
    count=$((count + 1))
    printf '  [%02d] %s\n' "$count" "$(head -n 1 <<<"$statement" | cut -c 1-70)"
    run_sql "$statement" >/dev/null
  done < <(python3 - "$file" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8").read()
lines = [l for l in text.splitlines() if not l.strip().startswith("--")]
for s in "\n".join(lines).split(";"):
    s = s.strip()
    if s and not s.upper().startswith("USE "):
        sys.stdout.write(s + "\0")
PY
)
  echo "  $count statements OK"
}

step_setup() {
  echo "== Schema $CATALOG.$SCHEMA and volume raw (warehouse $WAREHOUSE_ID)"
  run_sql "CREATE SCHEMA IF NOT EXISTS $CATALOG.$SCHEMA COMMENT 'Metadatenqualität datenregister.berlin.de'" >/dev/null
  run_sql "CREATE VOLUME IF NOT EXISTS $CATALOG.$SCHEMA.raw COMMENT 'Rohdateien: CSV-Tabellen aus harvester/transform.py'" >/dev/null
  echo "  OK"
}

step_upload() {
  ./scripts/upload.sh
}

step_load() {
  run_sql_file sql/schema.sql
  run_sql_file notebooks/01_load_tables.sql
}

step_verify() {
  local query="" table remote local_counts diff=0
  for table in "${TABLES[@]}"; do
    [ -n "$query" ] && query+=" UNION ALL "
    query+="SELECT '$table', count(*) FROM $table"
  done
  remote=$(run_sql "$query")
  local_counts=$(python3 - "${TABLES[@]}" <<'PY'
import csv, json, sys
from pathlib import Path
counts = {}
for table in sys.argv[1:]:
    path = Path("data/tables") / f"{table}.csv"
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            counts[table] = sum(1 for _ in csv.reader(f)) - 1
    else:
        counts[table] = 0  # e.g. link_check, not produced by transform.py
print(json.dumps(counts))
PY
)
  echo "== Row counts (local CSV vs. Databricks)"
  printf '  %-16s %8s %10s\n' table local databricks
  for table in "${TABLES[@]}"; do
    local l r mark=""
    l=$(jq -r --arg t "$table" '.[$t]' <<<"$local_counts")
    r=$(jq -r --arg t "$table" 'map(select(.[0] == $t))[0][1]' <<<"$remote")
    [ "$l" = "$r" ] || { mark="  <-- DIFF"; diff=1; }
    printf '  %-16s %8s %10s%s\n' "$table" "$l" "$r" "$mark"
  done
  if [ "$diff" -ne 0 ]; then
    echo "Row counts differ." >&2
    exit 1
  fi
  echo "  All row counts match."
}

step_analysis() {
  local file
  for file in sql/analysis/*.sql; do
    run_sql_file "$file"
  done
}

DASHBOARD_NAME="Open Data Berlin – Metadatenqualität"
DASHBOARD_FILE="dashboard/opendata_quality.lvdash.json"
DASHBOARD_ID_FILE="dashboard/dashboard_id.txt"

step_dashboard() {
  local body id
  python3 dashboard/build_dashboard.py
  body=$(jq -n --arg n "$DASHBOARD_NAME" --arg w "$WAREHOUSE_ID" --rawfile s "$DASHBOARD_FILE" \
    '{display_name: $n, warehouse_id: $w, serialized_dashboard: $s}')
  if [ -s "$DASHBOARD_ID_FILE" ]; then
    id=$(cat "$DASHBOARD_ID_FILE")
    echo "== Dashboard update $id"
    databricks lakeview update "$id" --json "$body" -o json >/dev/null
  else
    echo "== Dashboard create"
    id=$(databricks lakeview create --json "$body" -o json | jq -r '.dashboard_id')
    echo "$id" > "$DASHBOARD_ID_FILE"
  fi
  # embed_credentials: viewers see the data with the publisher's permissions
  databricks lakeview publish "$id" --embed-credentials --warehouse-id "$WAREHOUSE_ID" -o json >/dev/null
  echo "  published: $(databricks auth describe -o json 2>/dev/null | jq -r '.details.host // empty')/dashboardsv3/$id/published"
}

case "${1:-all}" in
  all)    step_setup; step_upload; step_load; step_verify; step_analysis ;;
  analysis) step_analysis ;;
  setup)  step_setup ;;
  upload) step_upload ;;
  load)   step_load ;;
  verify) step_verify ;;
  dashboard) step_dashboard ;;
  *) echo "Usage: $0 [all|setup|upload|load|verify|analysis|dashboard]" >&2; exit 2 ;;
esac
