-- Schema opendata-quality-watch (Databricks SQL, Delta, Unity Catalog)
-- Zielschema: workspace.opendata (wird in notebooks/01_load_tables.sql per USE gesetzt).
-- PK/FK sind informational (nicht erzwungen); NOT NULL wird von Delta erzwungen.
-- Vollständiger Neuaufbau: Tabellen werden in umgekehrter Abhängigkeitsreihenfolge gelöscht.
-- Hinweis: keine Semikolons in Kommentaren/Strings – das Notebook trennt Anweisungen an ';'.

DROP TABLE IF EXISTS link_check;
DROP TABLE IF EXISTS resource;
DROP TABLE IF EXISTS dataset_theme;
DROP TABLE IF EXISTS dataset;
DROP TABLE IF EXISTS format_alias;
DROP TABLE IF EXISTS format;
DROP TABLE IF EXISTS series;
DROP TABLE IF EXISTS theme;
DROP TABLE IF EXISTS hvd_category;
DROP TABLE IF EXISTS license;
DROP TABLE IF EXISTS source_system;
DROP TABLE IF EXISTS publisher_alias;
DROP TABLE IF EXISTS publisher;
DROP TABLE IF EXISTS harvest_run;

CREATE TABLE harvest_run (
  harvest_run_id      INT        NOT NULL COMMENT 'Snapshot-Datum als JJJJMMTT',
  snapshot_date       DATE       NOT NULL,
  snapshot_file       STRING     NOT NULL,
  source_api          STRING     NOT NULL,
  datasets_total      INT        NOT NULL COMMENT 'Alle Einträge im Snapshot (alle berlin_type)',
  datasets_loaded     INT        NOT NULL COMMENT 'Davon geladen (berlin_type = datensatz)',
  resources_loaded    INT        NOT NULL,
  transformed_at      TIMESTAMP  NOT NULL,
  CONSTRAINT pk_harvest_run PRIMARY KEY (harvest_run_id)
) COMMENT 'Ein Harvest-Lauf bzw. Snapshot der CKAN-API von datenregister.berlin.de';

CREATE TABLE publisher (
  publisher_id        INT        NOT NULL,
  name                STRING     NOT NULL COMMENT 'canonical_name aus publisher_merge.csv, sonst häufigste Schreibweise unter den Aliasen',
  name_normalized     STRING     NOT NULL COMMENT 'trim + lower + Mehrfach-Leerzeichen entfernt',
  short_name          STRING              COMMENT 'Kurzname fürs Dashboard aus seeds/publisher_short.csv (nur Bereitsteller mit >= 10 Datensätzen)',
  CONSTRAINT pk_publisher PRIMARY KEY (publisher_id)
) COMMENT 'Veröffentlichende Stelle (aus CKAN-Feld author), zusammengeführt bei identischem normalisierten Namen und nach seeds/publisher_merge.csv';

CREATE TABLE publisher_alias (
  alias               STRING     NOT NULL COMMENT 'author-Wert exakt wie im Portal',
  publisher_id        INT        NOT NULL,
  CONSTRAINT pk_publisher_alias PRIMARY KEY (alias),
  CONSTRAINT fk_publisher_alias_publisher FOREIGN KEY (publisher_id) REFERENCES publisher (publisher_id)
) COMMENT 'Zuordnung der Rohschreibweisen des Feldes author zu einem Publisher';

CREATE TABLE source_system (
  source_system_id    STRING     NOT NULL COMMENT 'CKAN-Feld berlin_source, unbekannt = Feld im Portal leer',
  label               STRING     NOT NULL,
  is_harvested        BOOLEAN    NOT NULL COMMENT 'Automatisch aus einem Fremdsystem geharvestet',
  CONSTRAINT pk_source_system PRIMARY KEY (source_system_id)
) COMMENT 'Erfassungsweg der Metadaten (Harvester, Webformular, API)';

CREATE TABLE license (
  license_id          STRING     NOT NULL,
  title               STRING     NOT NULL,
  url                 STRING,
  is_open             BOOLEAN    NOT NULL COMMENT 'CKAN-Feld isopen',
  CONSTRAINT pk_license PRIMARY KEY (license_id)
) COMMENT 'Lizenzen laut CKAN-Lizenzliste';

CREATE TABLE hvd_category (
  hvd_code            STRING     NOT NULL COMMENT 'Code aus dem EU-Vokabular High-Value Datasets',
  label               STRING              COMMENT 'Bewusst leer, wird manuell gepflegt',
  CONSTRAINT pk_hvd_category PRIMARY KEY (hvd_code)
) COMMENT 'Kategorien hochwertiger Datensätze (EU-Durchführungsverordnung 2023/138)';

CREATE TABLE theme (
  theme_id            STRING     NOT NULL COMMENT 'CKAN-Gruppenname',
  label               STRING     NOT NULL,
  CONSTRAINT pk_theme PRIMARY KEY (theme_id)
) COMMENT 'Themenkategorien (CKAN-Gruppen)';

CREATE TABLE series (
  series_id           INT        NOT NULL,
  series_key          STRING     NOT NULL COMMENT 'Name ohne Jahreszahlen, Stichtage und angehängte IDs',
  dataset_count       INT        NOT NULL,
  first_period_year   INT,
  last_period_year    INT,
  manually_verified   BOOLEAN    NOT NULL COMMENT 'Von Hand als echte Reihe geprüft (seeds/series_override.csv)',
  CONSTRAINT pk_series PRIMARY KEY (series_id)
) COMMENT 'Heuristisch erkannte Datensatzreihen (mindestens 2 Datensätze mit gleichem series_key, Korrekturen aus seeds/series_override.csv)';

CREATE TABLE format (
  format_code         STRING     NOT NULL,
  label               STRING     NOT NULL,
  machine_readable    BOOLEAN    NOT NULL,
  open_data_stars     INT                 COMMENT '5-Sterne-Modell nach Berners-Lee, NULL = nicht bewertbar',
  CONSTRAINT pk_format PRIMARY KEY (format_code)
) COMMENT 'Bereinigte Dateiformate mit Maschinenlesbarkeit und Open-Data-Sternen';

CREATE TABLE format_alias (
  raw_format          STRING     NOT NULL COMMENT 'Formatangabe exakt wie im Portal (leerer Wert nicht enthalten)',
  format_code         STRING     NOT NULL,
  CONSTRAINT pk_format_alias PRIMARY KEY (raw_format),
  CONSTRAINT fk_format_alias_format FOREIGN KEY (format_code) REFERENCES format (format_code)
) COMMENT 'Zuordnung der Rohformatangaben zu bereinigten Formaten';

CREATE TABLE dataset (
  dataset_id                STRING     NOT NULL COMMENT 'CKAN-UUID',
  harvest_run_id            INT        NOT NULL,
  name                      STRING     NOT NULL COMMENT 'CKAN-Slug',
  title                     STRING     NOT NULL,
  publisher_id              INT,
  ckan_organization         STRING              COMMENT 'CKAN-Organisation (Portal-Konto, nicht die Datenquelle)',
  source_system_id          STRING,
  license_id                STRING     NOT NULL,
  hvd_code                  STRING,
  series_id                 INT,
  period_year               INT                 COMMENT 'Höchste Jahreszahl aus Name, sonst aus temporal_coverage_to (< 2030)',
  is_open                   BOOLEAN    NOT NULL,
  notes_length              INT        NOT NULL COMMENT 'Länge der Beschreibung in Zeichen',
  num_tags                  INT        NOT NULL,
  num_resources             INT        NOT NULL,
  has_maintainer            BOOLEAN    NOT NULL COMMENT 'maintainer gefüllt (Platzhalter zählen als leer)',
  -- has_contact_email ist im Snapshot vom 13.11.2026 bei allen Datensätzen true und
  -- unterscheidet dort nicht. Die Spalte bleibt für spätere Snapshots erhalten.
  has_contact_email         BOOLEAN    NOT NULL COMMENT 'maintainer_email oder author_email gefüllt',
  date_released             DATE,
  date_updated              DATE,
  temporal_coverage_from    DATE,
  temporal_coverage_to      DATE,
  temporal_granularity      STRING,
  geographical_coverage     STRING,
  geographical_granularity  STRING,
  metadata_created          TIMESTAMP,
  metadata_modified         TIMESTAMP,
  CONSTRAINT pk_dataset PRIMARY KEY (dataset_id),
  CONSTRAINT fk_dataset_harvest_run FOREIGN KEY (harvest_run_id) REFERENCES harvest_run (harvest_run_id),
  CONSTRAINT fk_dataset_publisher FOREIGN KEY (publisher_id) REFERENCES publisher (publisher_id),
  CONSTRAINT fk_dataset_source_system FOREIGN KEY (source_system_id) REFERENCES source_system (source_system_id),
  CONSTRAINT fk_dataset_license FOREIGN KEY (license_id) REFERENCES license (license_id),
  CONSTRAINT fk_dataset_hvd_category FOREIGN KEY (hvd_code) REFERENCES hvd_category (hvd_code),
  CONSTRAINT fk_dataset_series FOREIGN KEY (series_id) REFERENCES series (series_id)
) COMMENT 'Datensätze (nur berlin_type = datensatz), ohne Personendaten';

CREATE TABLE dataset_theme (
  dataset_id          STRING     NOT NULL,
  theme_id            STRING     NOT NULL,
  CONSTRAINT pk_dataset_theme PRIMARY KEY (dataset_id, theme_id),
  CONSTRAINT fk_dataset_theme_dataset FOREIGN KEY (dataset_id) REFERENCES dataset (dataset_id),
  CONSTRAINT fk_dataset_theme_theme FOREIGN KEY (theme_id) REFERENCES theme (theme_id)
) COMMENT 'Zuordnung Datensatz zu Thema (n:m)';

CREATE TABLE resource (
  resource_id         STRING     NOT NULL COMMENT 'CKAN-UUID',
  dataset_id          STRING     NOT NULL,
  position            INT        NOT NULL,
  name                STRING,
  url                 STRING,
  format_raw          STRING              COMMENT 'Formatangabe exakt wie im Portal',
  format_code         STRING              COMMENT 'NULL = keine Formatangabe',
  mimetype            STRING,
  size_bytes          BIGINT,
  last_modified       TIMESTAMP,
  created             TIMESTAMP,
  has_mimetype        BOOLEAN    NOT NULL,
  has_size            BOOLEAN    NOT NULL COMMENT 'size > 0',
  has_last_modified   BOOLEAN    NOT NULL,
  CONSTRAINT pk_resource PRIMARY KEY (resource_id),
  CONSTRAINT fk_resource_dataset FOREIGN KEY (dataset_id) REFERENCES dataset (dataset_id),
  CONSTRAINT fk_resource_format FOREIGN KEY (format_code) REFERENCES format (format_code)
) COMMENT 'Ressourcen (Dateien, Dienste, Links) eines Datensatzes';

CREATE TABLE link_check (
  link_check_id       BIGINT     NOT NULL,
  resource_id         STRING     NOT NULL,
  harvest_run_id      INT        NOT NULL,
  checked_at          TIMESTAMP  NOT NULL,
  http_status         INT,
  is_reachable        BOOLEAN    NOT NULL,
  response_time_ms    INT,
  content_type        STRING,
  error_message       STRING,
  CONSTRAINT pk_link_check PRIMARY KEY (link_check_id),
  CONSTRAINT fk_link_check_resource FOREIGN KEY (resource_id) REFERENCES resource (resource_id),
  CONSTRAINT fk_link_check_harvest_run FOREIGN KEY (harvest_run_id) REFERENCES harvest_run (harvest_run_id)
) COMMENT 'Ergebnisse der Erreichbarkeitsprüfung von Ressourcen-URLs (wird später befüllt)';
