-- Qualitätsscore je Datensatz: 4 Kriterien zu je 25 Punkten.
-- reach_points ist NULL, solange es für den Datensatz keine Link-Prüfung gibt,
-- dann ist auch quality_score NULL, quality_score_without_links rechnet die übrigen 75 Punkte auf 100 hoch.
-- reasons listet in Klartext, wofür Punkte fehlen (kommagetrennt, NULL wenn nichts fehlt).
-- concat_ws überspringt NULL-Werte, deshalb liefert jedes CASE ohne ELSE nur bei einem Mangel Text.
CREATE OR REPLACE VIEW dataset_quality AS
SELECT
  b.*,
  lk.checked                                                                          AS links_checked,
  lk.checked - lk.reachable                                                           AS links_broken,
  -- Zeitangaben (25): Datum vorhanden 10, Zeitraum 5, keine Widersprüche 10
  10 * b.has_date_updated
  +  5 * b.has_coverage
  + 10 * CASE WHEN b.conflict_updated_before_released + b.conflict_coverage_reversed
                   + b.conflict_coverage_placeholder = 0 THEN 1 ELSE 0 END          AS time_points,
  -- Erreichbarkeit (25): Anteil erreichbarer Links
  ROUND(25.0 * lk.reachable / NULLIF(lk.checked, 0), 1)                              AS reach_points,
  -- Maschinenlesbarkeit (25): mindestens eine maschinenlesbare Ressource
  CASE WHEN b.resources_machine_readable > 0 THEN 25 ELSE 0 END                       AS machine_points,
  -- Vollständigkeit (25): Format bei jeder Ressource 10, Beschreibung 5, Schlagwörter 5, offene Lizenz 5
  10 * CASE WHEN b.resource_count > 0 AND b.resources_with_format = b.resource_count THEN 1 ELSE 0 END
  +  5 * CASE WHEN b.notes_length >= 100 THEN 1 ELSE 0 END
  +  5 * CASE WHEN b.num_tags >= 3 THEN 1 ELSE 0 END
  +  5 * CASE WHEN b.is_open THEN 1 ELSE 0 END                                       AS completeness_points,
  NULLIF(concat_ws(', ',
    CASE WHEN b.has_date_updated = 0 THEN 'kein Datum' END,
    CASE WHEN b.has_coverage = 0 THEN 'kein Zeitraum' END,
    CASE WHEN b.conflict_updated_before_released + b.conflict_coverage_reversed
              + b.conflict_coverage_placeholder > 0 THEN 'widersprüchliche Zeitangaben' END,
    CASE WHEN b.resource_count = 0 THEN 'keine Ressource'
         WHEN b.resources_machine_readable = 0 AND b.resources_map_image > 0 THEN 'nur Kartenbild'
         WHEN b.resources_machine_readable = 0 THEN 'nicht maschinenlesbar' END,
    CASE WHEN lk.checked - lk.reachable = 1 THEN '1 toter Link'
         WHEN lk.checked - lk.reachable > 1 THEN CAST(lk.checked - lk.reachable AS STRING) || ' tote Links' END,
    CASE WHEN b.resource_count > 0 AND lk.checked IS NULL THEN 'Links nicht geprüft' END,
    CASE WHEN b.resources_with_format < b.resource_count THEN 'Format fehlt' END,
    CASE WHEN b.notes_length < 100 OR b.notes_length IS NULL THEN 'kurze Beschreibung' END,
    CASE WHEN b.num_tags < 3 OR b.num_tags IS NULL THEN 'weniger als 3 Schlagwörter' END,
    CASE WHEN NOT b.is_open THEN 'keine offene Lizenz' END
  ), '')                                                                              AS reasons
FROM v_dataset_base b
LEFT JOIN (
  SELECT r.dataset_id,
         COUNT(*)                                          AS checked,
         SUM(CASE WHEN l.is_reachable THEN 1 ELSE 0 END)   AS reachable
  FROM v_latest_link_check l
  JOIN resource r ON r.resource_id = l.resource_id
  GROUP BY r.dataset_id
) lk ON lk.dataset_id = b.dataset_id;

CREATE OR REPLACE VIEW v_dataset_score AS
SELECT
  q.*,
  q.time_points + q.reach_points + q.machine_points + q.completeness_points           AS quality_score,
  ROUND((q.time_points + q.machine_points + q.completeness_points) * 100.0 / 75, 1)   AS quality_score_without_links
FROM dataset_quality q;
