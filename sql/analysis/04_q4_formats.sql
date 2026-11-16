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

-- Q4c: Maschinenlesbarkeit pro Angebot statt pro Datensatz.
-- Der FIS-Broker legt Kartenbild (WMS) und Daten (WFS) desselben Angebots als getrennte Datensätze an
-- (offer_key = Name ohne Endung -wms-/-wfs-/-wmts-<guid>). Ein Angebot ist maschinenlesbar, wenn
-- mindestens einer seiner Datensätze eine maschinenlesbare Ressource hat. HVD = mindestens ein
-- Datensatz des Angebots hat einen hvd_code. Quelle: FIS-Broker, sobald ein Datensatz des Angebots
-- von dort kommt, sonst die (einzige) Quelle. Im Snapshot vom 13.11.2026 mischt nur ein Angebot zwei
-- Quellen (Webformular-Datensatz plus WMS/WFS-Zwilling aus dem FIS-Broker).
-- Eine Zeile je Gruppe: dimension 'HVD' (High-Value vs. übrige), 'Quelle' und 'gesamt'.
-- Der Score pro Datensatz (dataset_quality) bleibt davon unberührt.
CREATE OR REPLACE VIEW q4c_offers_machine_readable AS
WITH offer AS (
  SELECT
    offer_key,
    CASE WHEN MAX(CASE WHEN source_system_id = 'harvest-fisbroker' THEN 1 ELSE 0 END) = 1
         THEN MAX(CASE WHEN source_system_id = 'harvest-fisbroker' THEN source_label END)
         ELSE MIN(source_label) END                     AS source_label,
    COUNT(*)                                            AS dataset_count,
    MAX(CASE WHEN hvd_code IS NOT NULL THEN 1 ELSE 0 END) AS is_hvd,
    MAX(has_machine_readable)                           AS has_machine_readable
  FROM v_dataset_base
  GROUP BY offer_key
),
grouped AS (
  SELECT 'HVD' AS dimension,
         CASE WHEN is_hvd = 1 THEN 'High-Value-Angebot' ELSE 'übrige' END AS group_name,
         offer_key, dataset_count, has_machine_readable
  FROM offer
  UNION ALL
  SELECT 'Quelle', source_label, offer_key, dataset_count, has_machine_readable FROM offer
  UNION ALL
  SELECT 'gesamt', 'alle Angebote', offer_key, dataset_count, has_machine_readable FROM offer
)
SELECT
  dimension,
  group_name,
  COUNT(*)                                                          AS offer_count,
  SUM(dataset_count)                                                AS dataset_count,
  SUM(CASE WHEN dataset_count > 1 THEN 1 ELSE 0 END)                AS multi_dataset_offers,
  SUM(has_machine_readable)                                         AS with_machine_readable,
  COUNT(*) - SUM(has_machine_readable)                              AS without_machine_readable,
  ROUND(100.0 * SUM(has_machine_readable) / COUNT(*), 1)            AS machine_readable_pct
FROM grouped
GROUP BY dimension, group_name;
