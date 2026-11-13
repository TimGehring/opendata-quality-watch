-- Q3a: Wie viele Datensätze sind nur ein Jahrgang einer Zeitreihe? Je Quelle.
CREATE OR REPLACE VIEW q3a_series_fragmentation AS
SELECT
  source_label,
  COUNT(*)                                                    AS dataset_count,
  SUM(CASE WHEN series_id IS NOT NULL THEN 1 ELSE 0 END)      AS in_series,
  ROUND(100.0 * SUM(CASE WHEN series_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS in_series_pct,
  COUNT(DISTINCT series_id)                                   AS series_count
FROM v_dataset_base
GROUP BY source_label;

-- Q3b: Geprüfte Statistik-Reihen (Webformular / Datenrubrik), deren neuester Jahrgang
-- 2023 oder früher ist – Kandidaten für eingestellte Reihen.
-- HAVING filtert nach der Gruppierung, weil MAX(period_year) erst dann feststeht.
CREATE OR REPLACE VIEW q3b_possibly_discontinued AS
SELECT
  se.series_id,
  se.series_key,
  COUNT(*)              AS datasets,
  MIN(b.period_year)    AS first_year,
  MAX(b.period_year)    AS last_year
FROM series se
JOIN v_dataset_base b ON b.series_id = se.series_id
WHERE se.manually_verified
  AND b.source_system_id IN ('webform', 'api-datenrubrik', 'api-datenrubrik-dw')
GROUP BY se.series_id, se.series_key
HAVING MAX(b.period_year) <= 2023
ORDER BY last_year;
