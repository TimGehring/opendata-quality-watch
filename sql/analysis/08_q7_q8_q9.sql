-- Q7: Automatisch geerntet vs. händisch gepflegt. Quelle "unbekannt" ausgeschlossen.
CREATE OR REPLACE VIEW q7_harvested_vs_manual AS
SELECT
  CASE WHEN is_harvested THEN 'automatisch geerntet' ELSE 'händisch / per API gepflegt' END AS origin,
  COUNT(*)                                   AS dataset_count,
  ROUND(AVG(quality_score_without_links), 1) AS avg_score_without_links,
  ROUND(AVG(quality_score), 1)               AS avg_score,
  ROUND(AVG(time_points), 1)                 AS avg_time,
  ROUND(AVG(reach_points), 1)                AS avg_reach,
  ROUND(AVG(machine_points), 1)              AS avg_machine,
  ROUND(AVG(completeness_points), 1)         AS avg_completeness
FROM v_dataset_score
WHERE source_system_id <> 'unbekannt'
GROUP BY CASE WHEN is_harvested THEN 'automatisch geerntet' ELSE 'händisch / per API gepflegt' END;

-- Q8: Bereitsteller mit mindestens 10 Datensätzen, schwächste zuerst.
-- WHERE filtert Zeilen vor der Gruppierung, HAVING filtert Gruppen danach.
CREATE OR REPLACE VIEW q8_publisher_ranking AS
SELECT
  publisher_name,
  COUNT(*)                                   AS dataset_count,
  ROUND(AVG(quality_score_without_links), 1) AS avg_score_without_links,
  ROUND(AVG(quality_score), 1)               AS avg_score,
  ROUND(AVG(time_points), 1)                 AS avg_time,
  ROUND(AVG(reach_points), 1)                AS avg_reach,
  ROUND(AVG(machine_points), 1)              AS avg_machine,
  ROUND(AVG(completeness_points), 1)         AS avg_completeness,
  ROUND(100 * AVG(1 - has_date_updated), 1)  AS missing_date_pct,
  ROUND(100.0 * SUM(CASE WHEN resources_machine_readable = 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS not_machine_readable_pct
FROM v_dataset_score
WHERE publisher_name IS NOT NULL
GROUP BY publisher_name
HAVING COUNT(*) >= 10
ORDER BY avg_score_without_links ASC;

-- Q9: Themen. n:m über dataset_theme, ein Datensatz kann in mehreren Themen zählen.
CREATE OR REPLACE VIEW q9_theme_ranking AS
SELECT
  t.label                                      AS theme,
  COUNT(*)                                     AS dataset_count,
  ROUND(AVG(s.quality_score_without_links), 1) AS avg_score_without_links,
  ROUND(AVG(s.quality_score), 1)               AS avg_score
FROM dataset_theme dt
JOIN theme t           ON t.theme_id    = dt.theme_id
JOIN v_dataset_score s ON s.dataset_id  = dt.dataset_id
GROUP BY t.label
ORDER BY avg_score_without_links ASC;

-- Q8b (HVD): EU-High-Value-Datensätze im Vergleich zum Rest.
CREATE OR REPLACE VIEW q8b_hvd_vs_rest AS
SELECT
  CASE WHEN hvd_code IS NOT NULL THEN 'High-Value-Datensatz' ELSE 'übrige' END AS group_name,
  COUNT(*)                                   AS dataset_count,
  ROUND(AVG(quality_score_without_links), 1) AS avg_score_without_links,
  ROUND(100.0 * SUM(CASE WHEN resources_machine_readable > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS machine_readable_pct
FROM v_dataset_score
GROUP BY CASE WHEN hvd_code IS NOT NULL THEN 'High-Value-Datensatz' ELSE 'übrige' END;

-- Themen je Datensatz in Klartext (n:m), Grundlage für den Themen-Filter im Dashboard.
-- Datensätze ohne Thema erscheinen als "(ohne Thema)", damit auch sie auswählbar sind.
CREATE OR REPLACE VIEW v_dataset_theme AS
SELECT d.dataset_id, COALESCE(t.label, '(ohne Thema)') AS theme
FROM dataset d
LEFT JOIN dataset_theme dt ON dt.dataset_id = d.dataset_id
LEFT JOIN theme t          ON t.theme_id    = dt.theme_id;
