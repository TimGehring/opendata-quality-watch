# ER-Modell (Entwurf, Ticket 2.1)

Entwurf in 3NF. Personendaten (`maintainer`, `maintainer_email`) werden **nicht** gespeichert, nur als Ja/Nein-Flag. Schlagwörter speichern wir nur als Anzahl (`num_tags`), um Tabellen zu sparen.

```mermaid
erDiagram
    PUBLISHER ||--o{ PUBLISHER_ALIAS : "hat Schreibweisen"
    PUBLISHER ||--o{ DATASET : "stellt bereit"
    SOURCE_SYSTEM ||--o{ DATASET : "erzeugt"
    LICENSE ||--o{ DATASET : "lizenziert"
    SERIES |o--o{ DATASET : "Jahrgang von"
    HVD_CATEGORY |o--o{ DATASET : "kategorisiert"
    DATASET ||--o{ DATASET_THEME : ""
    THEME ||--o{ DATASET_THEME : ""
    DATASET ||--o{ RESOURCE : "enthält"
    FORMAT_ALIAS }o--|| FORMAT : "normalisiert zu"
    FORMAT |o--o{ RESOURCE : "hat Format"
    RESOURCE ||--o{ LINK_CHECK : "geprüft durch"
    HARVEST_RUN ||--o{ DATASET : "geladen in"

    PUBLISHER { int publisher_id PK
                string name }
    PUBLISHER_ALIAS { string raw_author PK
                      int publisher_id FK }
    SOURCE_SYSTEM { string berlin_source PK
                    boolean is_harvested }
    LICENSE { string license_id PK
              string title
              boolean is_open }
    SERIES { int series_id PK
             string series_key UK "Name ohne Jahreszahlen"
             string title
             boolean manually_verified }
    HVD_CATEGORY { string code PK
                   string label }
    THEME { string theme_id PK
            string title }
    DATASET_THEME { string dataset_id PK,FK
                    string theme_id PK,FK }
    DATASET { string dataset_id PK "CKAN-UUID"
              string name UK
              string title
              string berlin_type
              int publisher_id FK
              string berlin_source FK
              string license_id FK
              string temporal_granularity "Auflösung, nur Info"
              int series_id FK "NULL = keine Reihe"
              int period_year "Jahrgang innerhalb der Reihe"
              string hvd_code FK
              date date_released
              date date_updated
              date temporal_coverage_from
              date temporal_coverage_to
              string geographical_granularity
              int notes_length
              int num_tags
              boolean has_maintainer
              boolean has_contact_email
              int harvest_run_id FK }
    FORMAT { string format_code PK
             string label
             boolean machine_readable
             int open_data_stars }
    FORMAT_ALIAS { string raw_format PK
                   string format_code FK }
    RESOURCE { string resource_id PK
               string dataset_id FK
               string url
               string raw_format
               string format_code FK "NULL = Format fehlt"
               boolean has_mimetype
               boolean has_size
               boolean has_last_modified }
    LINK_CHECK { string resource_id PK,FK
                 timestamp checked_at PK
                 int http_status
                 string error
                 int response_ms }
    HARVEST_RUN { int harvest_run_id PK
                  timestamp harvested_at
                  int dataset_count
                  string snapshot_file }
```

## Begründungen für die Präsentation

- **`publisher` + `publisher_alias`**: `author` ist Freitext mit Tippfehlern. Ohne Alias-Tabelle würde eine Behörde mehrfach gezählt (Normalisierung gegen Redundanz und Anomalien).
- **`format` + `format_alias`**: 52 Schreibweisen werden auf wenige echte Formate abgebildet. Maschinenlesbarkeit steht genau einmal pro Format (3NF statt pro Ressource wiederholt).
- **`series`**: Zeitreihen sind über viele Datensätze verteilt. Die Reihe ist ein eigenes Objekt. Die Zuordnung erfolgt per Heuristik und wird von Hand nachgeprüft (`manually_verified`).
- **`dataset_theme`**: Ein Datensatz kann mehreren Themen angehören (n:m) und braucht deshalb eine Zwischentabelle.
- **Keine Personendaten**: nur Flags, keine Namen oder Mail-Adressen.
- **Delta-Tabellen in Databricks** erzwingen keine Fremdschlüssel. PK und FK werden als *informational constraints* deklariert, und der Import prüft die Integrität (z. B. kein `format_code`, der nicht in `format` steht).

## Offene Fragen

- [ ] `hvd_category`-Codes (z. B. `c_dd313021`) auf Klartext abbilden, über das EU-Vokabular „High-value dataset categories“ prüfen.
- [x] Datensätze mit `berlin_type` = `dokument` oder `app` (37 Stück) werden ausgeschlossen.
