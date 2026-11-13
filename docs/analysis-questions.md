# Analysefragen & Score

Stand 13.11.2026, nach [[08 Datenprofil 2026-11-13|Datenprofil und Nachprüfung]]. **Jede Frage wird nach Herkunft (`berlin_source`) aufgeteilt.** Eingeschlossen sind nur Einträge mit `berlin_type = datensatz` (2595).

| # | Frage | SQL-Schwerpunkt |
| --- | --- | --- |
| Q1 | Wie verteilt sich der Datenstand (`date_updated`) nach Jahren, und wie viele haben keinen? (Kontext, alt ≠ schlecht) | `CASE`, `GROUP BY`, `IS NULL` |
| Q2 | **Widersprüchliche Zeitangaben:** Update vor Veröffentlichung, Zeitraum-Beginn nach Ende, Platzhalter wie 2099 | `WHERE` mit Vergleichen, `UNION ALL` der Regelverstöße |
| Q3 | **Zersplitterte Zeitreihen:** (a) Wie viele Datensätze sind nur ein Jahrgang einer Reihe, je Quelle? (b) Welche *geprüften* Statistik-Reihen enden 2023 oder früher? | `JOIN` auf `series`, `GROUP BY`, `MAX`, `HAVING` |
| Q4 | Wie viele Datensätze haben mindestens eine maschinenlesbare Ressource? Wie verteilen sich die bereinigten Formate? | `JOIN` auf `format_alias`/`format`, `EXISTS` |
| Q5 | Wie vollständig sind die Metadaten (Datensatz- und Ressourcen-Ebene)? | gefüllte Felder zählen, `AVG` |
| Q6 | Wie viele Ressourcen-Links sind tot (4xx/5xx, Timeout)? | `JOIN` mit `link_check` |
| Q7 | Sind automatisch geerntete Einträge besser oder schlechter als händisch gepflegte? | `GROUP BY source_system.is_harvested`, Quelle „unbekannt“ ausschließen |
| Q8 | Welche Bereitsteller schneiden am schlechtesten ab (nur bei ≥ 10 Datensätzen)? | `JOIN`, `GROUP BY`, `HAVING`, `ORDER BY` |
| Q9 | Welche Themen (`groups`) schneiden am besten bzw. schlechtesten ab? | n:m-`JOIN`, `AVG` |

Gestrichen:
- **Lizenzen** (99,4 % offen), bleiben eine KPI.
- **„Rhythmus eingehalten“**, weil `temporal_granularity` die Auflösung ist und kein Rhythmus.

## Qualitätsscore (0–100) je Datensatz

View `dataset_quality`, vier gleich gewichtete Kriterien:

| Kriterium | Punkte | Volle Punkte, wenn … |
| --- | --- | --- |
| Zeitangaben | 25 | `date_updated` vorhanden, Zeitraum angegeben, keine Widersprüche (Q2) |
| Erreichbarkeit | 25 | alle Ressourcen-Links antworten (2xx/3xx) |
| Maschinenlesbarkeit | 25 | mindestens eine maschinenlesbare Ressource |
| Metadaten-Vollständigkeit | 25 | Format bei jeder Ressource, Beschreibung ≥ 100 Zeichen, ≥ 3 Schlagwörter, offene Lizenz (Kontakt-E-Mail ist immer gesetzt und zählt daher nicht) |

Die Zeitreihen (Q3) fließen nicht in den Score ein, weil nur 23 % der Datensätze zu einer Reihe gehören. Sie sind eine eigene Dashboard-Seite.

Der Score ist eine eigene Definition. In der Präsentation sagst du das offen und zeigst die Einzelkriterien immer mit.

## Lehre für die Präsentation

Die erste Hypothese war, dass `temporal_granularity` der Aktualisierungsrhythmus sei. Die Daten haben das widerlegt. Das ist genau der Schritt „Daten prüfen, bevor man Schlüsse zieht“ aus der Schulvorgabe und sollte als eigene Folie rein.
