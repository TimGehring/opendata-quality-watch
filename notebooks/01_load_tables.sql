-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 01 Tabellen laden
-- MAGIC Legt Schema und Volume an, baut die Tabellen aus `sql/schema.sql` neu auf und befüllt sie
-- MAGIC aus den CSV-Dateien unter `/Volumes/workspace/opendata/raw/tables/` (hochgeladen mit `scripts/upload.sh`).
-- MAGIC
-- MAGIC Reihenfolge: Volume anlegen → `upload.sh` → dieses Notebook komplett ausführen.

-- COMMAND ----------

CREATE SCHEMA IF NOT EXISTS workspace.opendata COMMENT 'Metadatenqualität datenregister.berlin.de';

-- COMMAND ----------

CREATE VOLUME IF NOT EXISTS workspace.opendata.raw COMMENT 'Rohdateien: CSV-Tabellen aus harvester/transform.py';

-- COMMAND ----------

USE CATALOG workspace;
USE SCHEMA opendata;

-- COMMAND ----------

-- MAGIC %python
-- MAGIC # Run sql/schema.sql: from the Git folder (repo cloned into the workspace) or,
-- MAGIC # as fallback, from the volume (scripts/upload.sh also uploads schema.sql).
-- MAGIC from pathlib import Path
-- MAGIC
-- MAGIC candidates = [Path.cwd().parent / "sql" / "schema.sql",
-- MAGIC               Path("/Volumes/workspace/opendata/raw/schema.sql")]
-- MAGIC schema_file = next((p for p in candidates if p.exists()), None)
-- MAGIC if schema_file is None:
-- MAGIC     raise FileNotFoundError(f"schema.sql not found in {candidates}")
-- MAGIC print(f"Using {schema_file}")
-- MAGIC
-- MAGIC spark.sql("USE CATALOG workspace")
-- MAGIC spark.sql("USE SCHEMA opendata")
-- MAGIC lines = [l for l in schema_file.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--")]
-- MAGIC statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
-- MAGIC for statement in statements:
-- MAGIC     spark.sql(statement)
-- MAGIC print(f"{len(statements)} statements executed")

-- COMMAND ----------

INSERT INTO harvest_run
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/harvest_run.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'harvest_run_id INT, snapshot_date DATE, snapshot_file STRING, source_api STRING, datasets_total INT, datasets_loaded INT, resources_loaded INT, transformed_at TIMESTAMP'
);

-- COMMAND ----------

INSERT INTO publisher
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/publisher.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'publisher_id INT, name STRING, name_normalized STRING, short_name STRING'
);

-- COMMAND ----------

INSERT INTO publisher_alias
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/publisher_alias.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'alias STRING, publisher_id INT'
);

-- COMMAND ----------

INSERT INTO source_system
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/source_system.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'source_system_id STRING, label STRING, short_label STRING, is_harvested BOOLEAN'
);

-- COMMAND ----------

INSERT INTO license
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/license.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'license_id STRING, title STRING, url STRING, is_open BOOLEAN'
);

-- COMMAND ----------

INSERT INTO hvd_category
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/hvd_category.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'hvd_code STRING, label STRING'
);

-- COMMAND ----------

INSERT INTO theme
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/theme.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'theme_id STRING, label STRING'
);

-- COMMAND ----------

INSERT INTO series
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/series.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'series_id INT, series_key STRING, dataset_count INT, first_period_year INT, last_period_year INT, manually_verified BOOLEAN'
);

-- COMMAND ----------

INSERT INTO format
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/format.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'format_code STRING, label STRING, machine_readable BOOLEAN, open_data_stars INT'
);

-- COMMAND ----------

INSERT INTO format_alias
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/format_alias.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'raw_format STRING, format_code STRING'
);

-- COMMAND ----------

INSERT INTO dataset
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/dataset.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'dataset_id STRING, harvest_run_id INT, name STRING, title STRING, publisher_id INT, ckan_organization STRING, source_system_id STRING, license_id STRING, hvd_code STRING, series_id INT, period_year INT, is_open BOOLEAN, notes_length INT, num_tags INT, num_resources INT, has_maintainer BOOLEAN, has_contact_email BOOLEAN, date_released DATE, date_updated DATE, temporal_coverage_from DATE, temporal_coverage_to DATE, temporal_granularity STRING, geographical_coverage STRING, geographical_granularity STRING, metadata_created TIMESTAMP, metadata_modified TIMESTAMP'
);

-- COMMAND ----------

INSERT INTO dataset_theme
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/dataset_theme.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'dataset_id STRING, theme_id STRING'
);

-- COMMAND ----------

INSERT INTO resource
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/resource.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'resource_id STRING, dataset_id STRING, position INT, name STRING, url STRING, format_raw STRING, format_code STRING, mimetype STRING, size_bytes BIGINT, last_modified TIMESTAMP, created TIMESTAMP, has_mimetype BOOLEAN, has_size BOOLEAN, has_last_modified BOOLEAN'
);

-- COMMAND ----------

-- link_check.csv entsteht mit harvester/check_links.py.
INSERT INTO link_check
SELECT * FROM read_files(
  '/Volumes/workspace/opendata/raw/tables/link_check.csv',
  format => 'csv', header => true, multiLine => true, escape => '"',
  timestampFormat => 'yyyy-MM-dd HH:mm:ss', mode => 'FAILFAST',
  schema => 'link_check_id BIGINT, resource_id STRING, harvest_run_id INT, checked_at TIMESTAMP, http_status INT, is_reachable BOOLEAN, response_time_ms INT, content_type STRING, error_message STRING'
);

-- COMMAND ----------

SELECT 'harvest_run' AS table_name, count(*) AS row_count FROM harvest_run
UNION ALL SELECT 'publisher' AS table_name, count(*) AS row_count FROM publisher
UNION ALL SELECT 'publisher_alias' AS table_name, count(*) AS row_count FROM publisher_alias
UNION ALL SELECT 'source_system' AS table_name, count(*) AS row_count FROM source_system
UNION ALL SELECT 'license' AS table_name, count(*) AS row_count FROM license
UNION ALL SELECT 'hvd_category' AS table_name, count(*) AS row_count FROM hvd_category
UNION ALL SELECT 'theme' AS table_name, count(*) AS row_count FROM theme
UNION ALL SELECT 'series' AS table_name, count(*) AS row_count FROM series
UNION ALL SELECT 'format' AS table_name, count(*) AS row_count FROM format
UNION ALL SELECT 'format_alias' AS table_name, count(*) AS row_count FROM format_alias
UNION ALL SELECT 'dataset' AS table_name, count(*) AS row_count FROM dataset
UNION ALL SELECT 'dataset_theme' AS table_name, count(*) AS row_count FROM dataset_theme
UNION ALL SELECT 'resource' AS table_name, count(*) AS row_count FROM resource
UNION ALL SELECT 'link_check' AS table_name, count(*) AS row_count FROM link_check;
