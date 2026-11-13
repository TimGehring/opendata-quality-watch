-- Q5: Wie vollständig sind die Metadaten? Datensatz-Ebene und Ressourcen-Ebene, je Quelle.
-- AVG über 0/1-Werte ergibt direkt den Anteil.
CREATE OR REPLACE VIEW q5_completeness AS
SELECT
  source_label,
  COUNT(*)                                                         AS dataset_count,
  ROUND(100 * AVG(has_date_updated), 1)                            AS date_updated_pct,
  ROUND(100 * AVG(has_coverage), 1)                                AS coverage_pct,
  ROUND(100 * AVG(CASE WHEN notes_length >= 100 THEN 1 ELSE 0 END), 1) AS description_100_pct,
  ROUND(100 * AVG(CASE WHEN num_tags >= 3 THEN 1 ELSE 0 END), 1)   AS tags_3_pct,
  ROUND(100.0 * SUM(resources_with_format)        / NULLIF(SUM(resource_count), 0), 1) AS resource_format_pct,
  ROUND(100.0 * SUM(resources_with_mimetype)      / NULLIF(SUM(resource_count), 0), 1) AS resource_mimetype_pct,
  ROUND(100.0 * SUM(resources_with_size)          / NULLIF(SUM(resource_count), 0), 1) AS resource_size_pct,
  ROUND(100.0 * SUM(resources_with_last_modified) / NULLIF(SUM(resource_count), 0), 1) AS resource_last_modified_pct
FROM v_dataset_base
GROUP BY source_label;
