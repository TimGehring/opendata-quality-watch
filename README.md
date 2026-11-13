# opendata-quality-watch

Ziel des Projekts ist es, die Metadatenqualität des Berliner Open-Data-Portals
([datenregister.berlin.de](https://datenregister.berlin.de)) regelmäßig und nachvollziehbar
zu messen. Ein Harvester lädt die Metadaten aller Datensätze über die CKAN-API als
Snapshot, Profiling-Skripte und SQL-Auswertungen bestimmen Vollständigkeit, Aktualität
und typische Mängel (z. B. Platzhalterwerte, fehlende Lizenzen, veraltete Ressourcen),
und ein Dashboard macht die Entwicklung über die Zeit sichtbar.

## Struktur

| Ordner        | Inhalt                                          |
|---------------|-------------------------------------------------|
| `harvester/`  | Skripte zum Laden und Profilieren der Metadaten |
| `sql/`        | Tabellenschema (`schema.sql`) und SQL-Auswertungen |
| `seeds/`      | Manuell gepflegte Stammdaten (Formate, Format-Aliase, HVD-Kategorien) |
| `scripts/`    | Hilfsskripte (Upload nach Databricks)           |
| `notebooks/`  | Databricks-Notebooks (Egress-Test, Laden der Tabellen) |
| `dashboard/`  | Visualisierung                                  |
| `data/raw/`   | Snapshots (nicht im Git)                        |
| `data/tables/`| Normalisierte CSV-Tabellen (nicht im Git)       |
| `data/review/`| Listen zur manuellen Prüfung (nicht im Git)     |

## Nutzung

```bash
uv sync
uv run python harvester/fetch_metadata.py
uv run python harvester/profile_fields.py data/raw/ckan_snapshot_<YYYY-MM-DD>.json
```

## So baust du es nach

Voraussetzungen: [uv](https://docs.astral.sh/uv/), ein Databricks-Workspace (Free Edition) mit
Unity Catalog und die [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/),
angemeldet per `databricks auth login`, sowie `jq`.

1. **Harvest** – alle Metadaten als Snapshot laden:
   ```bash
   uv sync
   uv run python harvester/fetch_metadata.py
   ```
   Ergebnis: `data/raw/ckan_snapshot_<YYYY-MM-DD>.json`

2. **Transform** – Snapshot in normalisierte Tabellen überführen:
   ```bash
   uv run python harvester/transform.py data/raw/ckan_snapshot_<YYYY-MM-DD>.json
   ```
   Ergebnis: `data/tables/*.csv` sowie `data/review/publisher_candidates.csv` und
   `data/review/series_top20.csv`. Das Skript bricht ab, wenn ein Fremdschlüssel ins Leere
   zeigt oder ein Formatwert bzw. HVD-Code in `seeds/` fehlt – dann den Seed ergänzen.
   Es werden nur Einträge mit `berlin_type = datensatz` übernommen und keine Personendaten
   gespeichert (nur `has_maintainer` / `has_contact_email`).

3. **Databricks** – Schema, Volume, Upload, Tabellen und Zeilenvergleich in einem Schritt:
   ```bash
   ./scripts/deploy_databricks.sh          # oder einzeln: setup | upload | load | verify
   ```
   Das Skript legt `workspace.opendata` und das Volume `raw` an (idempotent), lädt die CSVs
   mit `scripts/upload.sh` nach `/Volumes/workspace/opendata/raw/tables/`, führt
   `sql/schema.sql` und `notebooks/01_load_tables.sql` Anweisung für Anweisung über die
   Statement Execution API aus (Abbruch beim ersten Fehler) und vergleicht am Ende die
   Zeilenzahlen aller 14 Tabellen mit den lokalen CSVs. Es nutzt das erste SQL-Warehouse
   des Workspace, ein anderes über `DATABRICKS_WAREHOUSE_ID`.

4. **Notebooks** – das Repository als Git-Ordner in den Workspace holen, dann
   - `notebooks/00_egress_test.py`: prüft, ob der Cluster die CKAN-API erreicht (Ticket 1.2),
   - `notebooks/01_load_tables.sql`: Alternative zu Schritt 3 im Browser, baut die Tabellen in `workspace.opendata` neu auf
     (`sql/schema.sql`), lädt alle CSVs per `read_files` und zeigt die Zeilenzahlen.

Datenmodell: Publisher werden nur bei identischem Namen (nach trim/lower/Leerzeichen)
automatisch zusammengeführt, darüber hinaus nur die geprüften Paare aus
`seeds/publisher_merge.csv`. Ähnliche Namen stehen zur Prüfung in
`publisher_candidates.csv`. Datensatzreihen werden heuristisch über den Namen ohne
Jahreszahlen, Stichtage und angehängte IDs bzw. FIS-Broker-Hash erkannt. Korrekturen und
die Handprüfung (`manually_verified`) stehen in `seeds/series_override.csv`.

## KI-Nutzung

Dieses Projekt wurde mit KI-Unterstützung erstellt. Die Nutzung ist hier offengelegt, wie es die Projektvorgabe verlangt.

- **Claude (Chat):** Themenwahl, Projektplanung, Analyse des Datenprofils, ER-Modell, alle Analyse-Abfragen in `sql/analysis/` sowie deren Erklärungen.
- **Claude Code:** Harvester, Transform-Skript, Datenbankschema, Lade- und Deploy-Skripte.
- **Kontrolle:** Die Abfragen werden lokal mit `tests/test_views_sqlite.py` gegen die exportierten Tabellen geprüft (z. B. Summen = Anzahl Datensätze). Einzelne Ergebnisse werden stichprobenartig im Portal nachgesehen. Eine Hypothese der KI (`temporal_granularity` = Aktualisierungsrhythmus) wurde anhand der Daten widerlegt und verworfen.
- Alle Entscheidungen und Ergebnisse hat der Autor nachvollzogen und kann sie erklären.

## Analysen

`sql/analysis/` enthält die Views für die Analysefragen Q1–Q9 und den Qualitätsscore (`v_dataset_score`). In Databricks anlegen mit `scripts/deploy_databricks.sh analysis`. Lokaler Test ohne Databricks: `python3 tests/test_views_sqlite.py`.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
