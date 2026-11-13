#!/usr/bin/env bash
# Upload the transformed CSV tables to the Unity Catalog volume workspace.opendata.raw.
# Requires a configured Databricks CLI (databricks auth login) and an existing volume
# (created by scripts/deploy_databricks.sh setup or notebooks/01_load_tables.sql).
set -euo pipefail

cd "$(dirname "$0")/.."
TARGET="dbfs:/Volumes/workspace/opendata/raw/tables"

shopt -s nullglob
files=(data/tables/*.csv)
if [ ${#files[@]} -eq 0 ]; then
  echo "No CSV files in data/tables/ - run harvester/transform.py first." >&2
  exit 1
fi

# fs cp does not create missing directories inside a volume
databricks fs mkdir "$TARGET"

for file in "${files[@]}"; do
  echo "Uploading $file -> $TARGET/$(basename "$file")"
  databricks fs cp --overwrite "$file" "$TARGET/$(basename "$file")"
done
echo "Done: ${#files[@]} files uploaded."

# schema.sql as fallback for notebooks/01_load_tables.sql (if the repo is not a Git folder)
echo "Uploading sql/schema.sql -> dbfs:/Volumes/workspace/opendata/raw/schema.sql"
databricks fs cp --overwrite sql/schema.sql dbfs:/Volumes/workspace/opendata/raw/schema.sql
