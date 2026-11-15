-- Basis-View: ein Datensatz pro Zeile mit allen Merkmalen, die die Analysen Q1–Q9 brauchen.
-- Verbindet dataset mit Quelle (source_system), Bereitsteller (publisher) und fasst die
-- Ressourcen je Datensatz zusammen (Unterabfrage res). Alle Prüf-Flags entstehen hier einmal,
-- damit jede Analyse dieselbe Definition benutzt.
CREATE OR REPLACE VIEW v_dataset_base AS
SELECT
  d.dataset_id,
  d.name,
  d.title,
  'https://daten.berlin.de/datensaetze/' || d.name     AS portal_url,
  COALESCE(d.source_system_id, 'unbekannt')            AS source_system_id,
  s.label                                              AS source_label,
  s.is_harvested,
  p.name                                               AS publisher_name,
  d.series_id,
  d.period_year,
  d.hvd_code,
  d.is_open,
  d.notes_length,
  d.num_tags,
  d.date_released,
  d.date_updated,
  d.temporal_coverage_from,
  d.temporal_coverage_to,
  -- Zeitangaben
  CASE WHEN d.date_updated IS NOT NULL THEN 1 ELSE 0 END                       AS has_date_updated,
  CASE WHEN d.temporal_coverage_from IS NOT NULL
         OR d.temporal_coverage_to   IS NOT NULL THEN 1 ELSE 0 END             AS has_coverage,
  CASE WHEN d.date_updated < d.date_released THEN 1 ELSE 0 END                 AS conflict_updated_before_released,
  CASE WHEN d.temporal_coverage_from > d.temporal_coverage_to THEN 1 ELSE 0 END AS conflict_coverage_reversed,
  CASE WHEN d.temporal_coverage_to >= '2030-01-01' THEN 1 ELSE 0 END           AS conflict_coverage_placeholder,
  -- Ressourcen (aus Unterabfrage)
  COALESCE(res.resource_count, 0)          AS resource_count,
  COALESCE(res.with_format, 0)             AS resources_with_format,
  COALESCE(res.machine_readable_count, 0)  AS resources_machine_readable,
  CASE WHEN COALESCE(res.machine_readable_count, 0) > 0 THEN 1 ELSE 0 END AS has_machine_readable,
  COALESCE(res.map_image_count, 0)         AS resources_map_image,
  res.max_stars,
  COALESCE(res.with_mimetype, 0)           AS resources_with_mimetype,
  COALESCE(res.with_size, 0)               AS resources_with_size,
  COALESCE(res.with_last_modified, 0)      AS resources_with_last_modified
FROM dataset d
LEFT JOIN source_system s ON s.source_system_id = COALESCE(d.source_system_id, 'unbekannt')
LEFT JOIN publisher     p ON p.publisher_id     = d.publisher_id
LEFT JOIN (
  SELECT
    r.dataset_id,
    COUNT(*)                                                       AS resource_count,
    SUM(CASE WHEN r.format_code IS NOT NULL THEN 1 ELSE 0 END)     AS with_format,
    SUM(CASE WHEN f.machine_readable THEN 1 ELSE 0 END)            AS machine_readable_count,
    SUM(CASE WHEN r.format_code IN ('WMS', 'WMTS') THEN 1 ELSE 0 END) AS map_image_count,
    MAX(f.open_data_stars)                                         AS max_stars,
    SUM(CASE WHEN r.has_mimetype THEN 1 ELSE 0 END)                AS with_mimetype,
    SUM(CASE WHEN r.has_size THEN 1 ELSE 0 END)                    AS with_size,
    SUM(CASE WHEN r.has_last_modified THEN 1 ELSE 0 END)           AS with_last_modified
  FROM resource r
  LEFT JOIN format f ON f.format_code = r.format_code
  GROUP BY r.dataset_id
) res ON res.dataset_id = d.dataset_id;
