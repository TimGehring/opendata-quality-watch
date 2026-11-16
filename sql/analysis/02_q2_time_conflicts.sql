-- Q2: Widersprüchliche Zeitangaben. Jede Regel ist ein eigener SELECT,
-- UNION ALL hängt die Ergebnisse untereinander. So lässt sich jede Regel einzeln erklären.
-- Regel 1 prüft date_updated < date_released. Das Portal zeigt date_updated als „Aktualisiert“ an,
-- das Feld wird aber uneinheitlich genutzt (Datenstand vs. letzte Aktualisierung), siehe Methodik.
CREATE OR REPLACE VIEW q2_time_conflicts AS
SELECT 'Angezeigtes Aktualisierungsdatum liegt vor der Veröffentlichung' AS rule, source_label, COUNT(*) AS dataset_count
FROM v_dataset_base WHERE conflict_updated_before_released = 1 GROUP BY source_label
UNION ALL
SELECT 'Zeitraum-Beginn nach Ende', source_label, COUNT(*)
FROM v_dataset_base WHERE conflict_coverage_reversed = 1 GROUP BY source_label
UNION ALL
SELECT 'Zeitraum-Ende als Platzhalter (≥ 2030)', source_label, COUNT(*)
FROM v_dataset_base WHERE conflict_coverage_placeholder = 1 GROUP BY source_label
UNION ALL
SELECT 'Kein Aktualisierungsdatum', source_label, COUNT(*)
FROM v_dataset_base WHERE has_date_updated = 0 GROUP BY source_label;
