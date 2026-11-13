-- Q6: Wie viele Ressourcen-Links sind erreichbar? Es zählt jeweils die letzte Prüfung je Ressource.
-- ROW_NUMBER nummeriert die Prüfungen je Ressource, neueste zuerst, rn = 1 ist die aktuellste.
CREATE OR REPLACE VIEW v_latest_link_check AS
SELECT resource_id, http_status, is_reachable, error_message, checked_at
FROM (
  SELECT lc.*,
         ROW_NUMBER() OVER (PARTITION BY resource_id ORDER BY checked_at DESC) AS rn
  FROM link_check lc
) t
WHERE rn = 1;

CREATE OR REPLACE VIEW q6_link_reachability AS
SELECT
  b.source_label,
  COUNT(*)                                                   AS checked_resources,
  SUM(CASE WHEN l.is_reachable THEN 1 ELSE 0 END)            AS reachable,
  SUM(CASE WHEN NOT l.is_reachable THEN 1 ELSE 0 END)        AS broken,
  ROUND(100.0 * SUM(CASE WHEN NOT l.is_reachable THEN 1 ELSE 0 END) / COUNT(*), 1) AS broken_pct
FROM v_latest_link_check l
JOIN resource r       ON r.resource_id = l.resource_id
JOIN v_dataset_base b ON b.dataset_id  = r.dataset_id
GROUP BY b.source_label;
