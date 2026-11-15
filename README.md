# opendata-quality-watch

Ziel des Projekts ist es, die Metadatenqualität des Berliner Open-Data-Portals
([datenregister.berlin.de](https://datenregister.berlin.de)) regelmäßig und nachvollziehbar
zu messen. Ein Harvester lädt die Metadaten aller Datensätze über die CKAN-API als
Snapshot, Profiling-Skripte und SQL-Auswertungen bestimmen Vollständigkeit, Aktualität
und typische Mängel (z. B. Platzhalterwerte, fehlende Lizenzen, veraltete Ressourcen),
und ein Dashboard macht die Entwicklung über die Zeit sichtbar.

**Ergebnisse ansehen (ohne Login):** <https://timgehring.github.io/opendata-quality-watch/>  
**Repository:** <https://github.com/TimGehring/opendata-quality-watch>

## Struktur

| Ordner        | Inhalt                                          |
|---------------|-------------------------------------------------|
| `harvester/`  | Skripte zum Laden und Profilieren der Metadaten |
| `sql/`        | Tabellenschema (`schema.sql`) und SQL-Auswertungen |
| `seeds/`      | Manuell gepflegte Stammdaten (Formate, Format-Aliase, HVD-Kategorien, Publisher-Zusammenführungen und -Kurznamen) |
| `scripts/`    | Hilfsskripte (Upload und Deploy nach Databricks, Export und Prüfung der Ergebnisseite) |
| `site/`       | Statische Ergebnisseite (GitHub Pages), Daten in `site/data/*.json` |
| `notebooks/`  | Databricks-Notebooks (Egress-Test, Laden der Tabellen) |
| `dashboard/`  | AI/BI-Dashboard als Code (`opendata_quality.lvdash.json`, erzeugt von `build_dashboard.py`), Screenshots |
| `data/raw/`   | Snapshots (nicht im Git, enthalten Kontaktdaten aus dem Portal) |
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
- **Claude Code:** Harvester, Transform-Skript, Datenbankschema, Lade- und Deploy-Skripte, Link-Check, Dashboard, Ergebnisseite (`site/`) mit Export- und Prüfskript.
- **Kontrolle:** Die Abfragen werden lokal mit `tests/test_views_sqlite.py` gegen die exportierten Tabellen geprüft (z. B. Summen = Anzahl Datensätze). Einzelne Ergebnisse werden stichprobenartig im Portal nachgesehen. Eine Hypothese der KI (`temporal_granularity` = Aktualisierungsrhythmus) wurde anhand der Daten widerlegt und verworfen.
- Alle Entscheidungen und Ergebnisse hat der Autor nachvollzogen und kann sie erklären.

## Analysen

`sql/analysis/` enthält die Views für die Analysefragen Q1–Q9 und den Qualitätsscore (`v_dataset_score`). In Databricks anlegen mit `scripts/deploy_databricks.sh analysis`. Lokaler Test ohne Databricks: `python3 tests/test_views_sqlite.py`.

## Dashboard

Das Databricks AI/BI-Dashboard (7 Seiten, globaler Filter „Quelle“) liegt als Code in
`dashboard/opendata_quality.lvdash.json`. Die Datei wird von `dashboard/build_dashboard.py`
erzeugt und nicht von Hand bearbeitet. Alle Datasets lesen nur Views aus `workspace.opendata`.

```bash
./scripts/deploy_databricks.sh analysis    # Views anlegen (vorher: python3 tests/test_views_sqlite.py)
./scripts/deploy_databricks.sh dashboard   # JSON bauen, Dashboard anlegen/aktualisieren, veröffentlichen
python3 dashboard/check_widgets.py         # jede Widget-Abfrage per Statement-API: Fehler oder leer?
```

Beim ersten Lauf wird das Dashboard mit `databricks lakeview create` angelegt und die ID in
`dashboard/dashboard_id.txt` gespeichert. Danach aktualisiert `databricks lakeview update` dasselbe
Dashboard. Veröffentlicht wird mit eingebetteten Zugangsdaten (`--embed-credentials`).
Ansehen können es nur angemeldete Nutzer des Workspace. Für alle anderen gibt es die Ergebnisseite (siehe unten) und Screenshots
in `dashboard/screenshots/`.

## Ergebnisse ohne Databricks ansehen

Das Dashboard können nur angemeldete Nutzer des Databricks-Workspace öffnen. Deshalb gibt es eine
statische Ergebnisseite ohne Login: **<https://timgehring.github.io/opendata-quality-watch/>**

Sie zeigt dieselben Abschnitte wie das Dashboard (Befunde, Kennzahlen, Maschinenlesbarkeit,
Zeitangaben, Erreichbarkeit, Bereitsteller & Themen, durchsuchbare Datensatzliste, Methodik).
Alle Zahlen stammen aus JSON-Dateien in `site/data/`, die aus den Views exportiert werden; im
HTML/JS steht keine Ergebniszahl fest. Die Datensatzliste enthält keine Personendaten.

```bash
python3 scripts/export_results.py   # Views per Statement-API abfragen -> site/data/*.json, meta.json
python3 scripts/check_site.py       # JSON gegen Views, gerenderte Seite (headless Chrome) gegen Views
cd site && python3 -m http.server   # lokal ansehen: http://localhost:8000
```

`check_site.py` braucht Node ≥ 22 und Google Chrome. Bei jedem Push auf `master` veröffentlicht die
GitHub Action `.github/workflows/pages.yml` den Ordner `site/` auf GitHub Pages. Chart.js liegt lokal
in `site/vendor/` (MIT), die Seite lädt nichts von Dritten und nutzt kein Tracking.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
