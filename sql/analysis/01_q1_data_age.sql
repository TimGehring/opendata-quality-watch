-- Q1: Wie verteilt sich der Datenstand (date_updated) über die Zeit, je Quelle?
-- Nur Kontext: ein altes Datum ist bei historischen Daten korrekt (alt ≠ schlecht).
-- Die Stufe "fehlt" muss als erstes WHEN stehen, weil ein Vergleich mit NULL nie wahr ist.
CREATE OR REPLACE VIEW q1_data_age AS
SELECT
  source_label,
  age_bucket,
  dataset_count,
  ROUND(100.0 * dataset_count / SUM(dataset_count) OVER (PARTITION BY source_label), 1) AS share_in_source_pct
FROM (
  SELECT
    source_label,
    CASE
      WHEN date_updated IS NULL        THEN '1 fehlt'
      WHEN year(date_updated) >= 2025  THEN '2 2025–2026'
      WHEN year(date_updated) >= 2020  THEN '3 2020–2024'
      WHEN year(date_updated) >= 2010  THEN '4 2010–2019'
      ELSE                                  '5 vor 2010'
    END            AS age_bucket,
    COUNT(*)       AS dataset_count
  FROM v_dataset_base
  GROUP BY source_label,
    CASE
      WHEN date_updated IS NULL        THEN '1 fehlt'
      WHEN year(date_updated) >= 2025  THEN '2 2025–2026'
      WHEN year(date_updated) >= 2020  THEN '3 2020–2024'
      WHEN year(date_updated) >= 2010  THEN '4 2010–2019'
      ELSE                                  '5 vor 2010'
    END
) t;
