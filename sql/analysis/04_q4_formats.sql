-- Q4a: Verteilung der bereinigten Formate über alle Ressourcen.
-- LEFT JOIN, damit Ressourcen ohne Format als "(fehlt)" mitgezählt werden.
CREATE OR REPLACE VIEW q4a_format_distribution AS
SELECT
  COALESCE(f.label, '(fehlt)')            AS format,
  f.machine_readable,
  f.open_data_stars,
  COUNT(*)                                AS resource_count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct
FROM resource r
LEFT JOIN format f ON f.format_code = r.format_code
GROUP BY COALESCE(f.label, '(fehlt)'), f.machine_readable, f.open_data_stars;

-- Q4b: Anteil der Datensätze mit mindestens einer maschinenlesbaren Ressource, je Quelle.
CREATE OR REPLACE VIEW q4b_machine_readable_by_source AS
SELECT
  source_label,
  COUNT(*)                                                             AS dataset_count,
  SUM(CASE WHEN resources_machine_readable > 0 THEN 1 ELSE 0 END)      AS with_machine_readable,
  ROUND(100.0 * SUM(CASE WHEN resources_machine_readable > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS machine_readable_pct
FROM v_dataset_base
GROUP BY source_label;
