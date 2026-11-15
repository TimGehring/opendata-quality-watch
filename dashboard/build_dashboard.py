# Erzeugt dashboard/opendata_quality.lvdash.json (Databricks AI/BI-Dashboard, "Lakeview").
# Aufruf aus dem Repo-Root: python3 dashboard/build_dashboard.py
# Anlegen/aktualisieren in Databricks: ./scripts/deploy_databricks.sh dashboard
#
# Alle Datasets lesen nur Views aus workspace.opendata (sql/analysis/). Im Dashboard selbst
# stehen höchstens Umformungen für die Darstellung (Top 12 + Rest, Spalten untereinander).
# Raster: 12 Spalten breit, Höhe in Rastereinheiten.
import json
from pathlib import Path

V = "workspace.opendata."
SNAPSHOT = "13.11.2026"
# Stand Snapshot 13.11.2026, nachgerechnet per
#   SELECT SUM(links_checked), SUM(resource_count) FROM workspace.opendata.v_dataset_score
# Der Untertitel ist fester Text und folgt dem Quellen-Filter nicht.
LINKS_CHECKED = "5.396"
RESOURCES_TOTAL = "6.228"
REPO_HINT = ("Repository: [github.com/TimGehring/opendata-quality-watch](https://github.com/TimGehring/opendata-quality-watch) (MIT)  \n"
             "Ergebnisse ohne Login: [timgehring.github.io/opendata-quality-watch](https://timgehring.github.io/opendata-quality-watch/)")

# ---------------------------------------------------------------- Datasets

DATASETS = {
    "ds_score": ("Datensätze mit Score", f"""
SELECT dataset_id, name, title, publisher_name, source_label,
       quality_score, quality_score_without_links,
       time_points, reach_points, machine_points, completeness_points,
       has_machine_readable, has_date_updated, links_checked, links_broken
FROM {V}v_dataset_score"""),
    "ds_score_by_source": ("Score je Quelle", f"""
SELECT source_label, quality_score
FROM {V}v_dataset_score
WHERE source_label <> 'unbekannt'"""),
    "ds_detail": ("Datensatz-Detail", f"""
SELECT quality_score, reasons, title, portal_url, publisher_short, publisher_name, source_label, source_label_long,
       time_points, reach_points, machine_points, completeness_points
FROM {V}v_dataset_score
WHERE :thema = 'Alle Themen'
   OR dataset_id IN (SELECT dataset_id FROM {V}v_dataset_theme WHERE theme = :thema)
ORDER BY quality_score ASC NULLS LAST"""),
    "ds_themes": ("Themenliste (Filter)", f"""
SELECT 'Alle Themen' AS theme
UNION ALL
SELECT DISTINCT theme FROM {V}v_dataset_theme"""),
    "ds_q7_long": ("Q7 Teilpunkte", f"""
SELECT origin, 'Zeitangaben' AS teil, avg_time AS punkte FROM {V}q7_harvested_vs_manual
UNION ALL SELECT origin, 'Erreichbarkeit', avg_reach FROM {V}q7_harvested_vs_manual
UNION ALL SELECT origin, 'Maschinenlesbarkeit', avg_machine FROM {V}q7_harvested_vs_manual
UNION ALL SELECT origin, 'Vollständigkeit', avg_completeness FROM {V}q7_harvested_vs_manual"""),
    "ds_q4a_top": ("Q4a Formate Top 12", f"""
WITH ranked AS (
  SELECT format, machine_readable, resource_count,
         ROW_NUMBER() OVER (ORDER BY resource_count DESC) AS rang
  FROM {V}q4a_format_distribution
)
SELECT CASE WHEN rang <= 12 THEN format ELSE 'übrige Formate' END AS format,
       CASE WHEN rang > 12 THEN 'gemischt (übrige)'
            WHEN machine_readable THEN 'maschinenlesbar'
            WHEN NOT machine_readable THEN 'nicht maschinenlesbar'
            ELSE 'ohne Formatangabe' END AS lesbarkeit,
       SUM(resource_count) AS ressourcen
FROM ranked
GROUP BY 1, 2
ORDER BY ressourcen DESC"""),
    "ds_q8b_long": ("Q8b High-Value vs. übrige", f"""
SELECT group_name, 'Ø Score ohne Links' AS kennzahl, avg_score_without_links AS wert FROM {V}q8b_hvd_vs_rest
UNION ALL
SELECT group_name, '% mit maschinenlesbarer Ressource', machine_readable_pct FROM {V}q8b_hvd_vs_rest"""),
    "ds_q1": ("Q1 Datenstand", f"SELECT source_label, age_bucket, dataset_count, share_in_source_pct FROM {V}q1_data_age"),
    "ds_q2": ("Q2 Widersprüche", f"SELECT rule, source_label, dataset_count FROM {V}q2_time_conflicts"),
    "ds_q3a": ("Q3a Zeitreihen", f"SELECT source_label, dataset_count, in_series, in_series_pct, series_count FROM {V}q3a_series_fragmentation"),
    "ds_q3b": ("Q3b eingestellte Reihen", f"SELECT series_key, datasets, first_year, last_year FROM {V}q3b_possibly_discontinued"),
    "ds_q6": ("Q6 Erreichbarkeit", f"SELECT source_label, checked_resources, reachable, broken, broken_pct FROM {V}q6_link_reachability"),
    "ds_q6b": ("Q6b Hosts", f"SELECT host, checked_links, broken, broken_pct FROM {V}q6b_broken_hosts"),
    "ds_q8": ("Q8 Bereitsteller", f"""
SELECT publisher_short, dataset_count, avg_score, avg_time, avg_reach, avg_machine, avg_completeness
FROM {V}q8_publisher_ranking
ORDER BY avg_score ASC"""),
    "ds_q9": ("Q9 Themen", f"SELECT theme, dataset_count, avg_score_without_links, avg_score FROM {V}q9_theme_ranking"),
}

THEMA_PARAM = {
    "displayName": "Thema",
    "keyword": "thema",
    "dataType": "STRING",
    "defaultSelection": {"values": {"dataType": "STRING", "values": [{"value": "Alle Themen"}]}},
}

# Datasets mit Spalte source_label: auf sie wirkt der globale Filter "Quelle".
SOURCE_FILTER_DATASETS = ["ds_score", "ds_score_by_source", "ds_detail", "ds_q1", "ds_q2", "ds_q3a", "ds_q6"]

# ---------------------------------------------------------------- Formate

def num(places=0, exact=False):
    return {"type": "number-plain", "abbreviation": "none",
            "decimalPlaces": {"type": "exact" if exact else "max", "places": places}}

def pct(places=1):
    # Wert ist ein Anteil 0..1, Anzeige als Prozent
    return {"type": "number-percent", "decimalPlaces": {"type": "max", "places": places}}

# ---------------------------------------------------------------- Widgets

_counter = 0

def _name(prefix):
    global _counter
    _counter += 1
    return f"{prefix}_{_counter:02d}"

def frame(title, description=None):
    f = {"showTitle": True, "title": title}
    if description:
        f["showDescription"] = True
        f["description"] = description
    return f

def text(lines, x, y, w, h):
    return {"widget": {"name": _name("text"), "multilineTextboxSpec": {"lines": [l + "\n" for l in lines]}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def query(dataset, fields, disaggregated):
    return [{"name": "main_query", "query": {
        "datasetName": dataset,
        "fields": [{"name": n, "expression": e} for n, e in fields],
        "disaggregated": disaggregated}}]

def counter(title, dataset, expr, fmt, x, y, w=3, h=3, description=None):
    return {"widget": {"name": _name("kpi"),
                       "queries": query(dataset, [("wert", expr)], False),
                       "spec": {"version": 2, "widgetType": "counter", "frame": frame(title, description),
                                "encodings": {"value": {"fieldName": "wert", "format": fmt}}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def bar(title, dataset, x_field, x_label, y_field, y_label, y_expr=None, color=None, stack=False,
        sort="y-reversed", horizontal=False, y_fmt=None, pos=(0, 0, 6, 7), description=None,
        disaggregated=None, extra=None):
    """Balkendiagramm. y_expr gesetzt -> aggregiert (GROUP BY über x/color)."""
    fields = [(x_field, f"`{x_field}`")]
    y_name = y_field if y_expr is None else f"y_{y_field}"
    fields.append((y_name, y_expr or f"`{y_field}`"))
    if color:
        fields.append((color[0], f"`{color[0]}`"))
    for e in extra or []:
        fields.append((e[0], f"`{e[0]}`"))
    cat = {"fieldName": x_field, "displayName": x_label,
           "scale": {"type": "categorical", **({"sort": {"by": sort}} if sort else {})}}
    val = {"fieldName": y_name, "displayName": y_label, "scale": {"type": "quantitative"},
           "format": y_fmt or num(1)}
    enc = {"x": val, "y": cat} if horizontal else {"x": cat, "y": val}
    if color:
        enc["color"] = {"fieldName": color[0], "displayName": color[1], "scale": {"type": "categorical"}}
    if extra:
        enc["extra"] = [{"fieldName": e[0], "displayName": e[1]} for e in extra]
    spec = {"version": 3, "widgetType": "bar", "frame": frame(title, description), "encodings": enc}
    if color:
        spec["mark"] = {"layout": "stack" if stack else "group"}
    dis = (y_expr is None) if disaggregated is None else disaggregated
    x, y, w, h = pos
    return {"widget": {"name": _name("bar"), "queries": query(dataset, fields, dis), "spec": spec},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def table(title, dataset, columns, pos, description=None, hidden_fields=()):
    """columns: (feld, Anzeigename, format|None[, extra-Dict]).
    hidden_fields: nur abgefragt (z. B. für Link-Vorlagen), nicht als Spalte angezeigt."""
    cols = []
    for c in columns:
        col = {"fieldName": c[0], "displayName": c[1]}
        if c[2]:
            col["format"] = c[2]
        if len(c) > 3:
            col.update(c[3])
        cols.append(col)
    x, y, w, h = pos
    return {"widget": {"name": _name("table"),
                       "queries": query(dataset, [(c[0], f"`{c[0]}`") for c in columns]
                                        + [(h, f"`{h}`") for h in hidden_fields], True),
                       "spec": {"version": 2, "widgetType": "table", "frame": frame(title, description),
                                "encodings": {"columns": cols}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def field_filter(title, widget_type, field, datasets, pos, description=None):
    queries, fields = [], []
    for ds in datasets:
        qn = f"f_{field}_{ds}"
        queries.append({"name": qn, "query": {"datasetName": ds, "fields": [
            {"name": field, "expression": f"`{field}`"},
            {"name": f"{field}_associativity", "expression": "COUNT_IF(`associative_filter_predicate_group`)"}],
            "disaggregated": False}})
        fields.append({"fieldName": field, "queryName": qn})
    x, y, w, h = pos
    return {"widget": {"name": _name("filter"), "queries": queries,
                       "spec": {"version": 2, "widgetType": widget_type, "frame": frame(title, description),
                                "encodings": {"fields": fields}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

def theme_param_filter(pos):
    q_values, q_param = "f_theme_values", "p_thema_ds_detail"
    x, y, w, h = pos
    return {"widget": {"name": _name("filter"),
                       "queries": [
                           {"name": q_values, "query": {"datasetName": "ds_themes", "fields": [
                               {"name": "theme", "expression": "`theme`"},
                               {"name": "theme_associativity", "expression": "COUNT_IF(`associative_filter_predicate_group`)"}],
                               "disaggregated": False}},
                           {"name": q_param, "query": {"datasetName": "ds_detail",
                               "parameters": [{"name": "thema", "keyword": "thema"}], "disaggregated": False}}],
                       "spec": {"version": 2, "widgetType": "filter-single-select", "frame": frame("Thema"),
                                "selection": {"defaultSelection": {"values": {"dataType": "STRING",
                                                                              "values": [{"value": "Alle Themen"}]}}},
                                "encodings": {"fields": [{"fieldName": "theme", "queryName": q_values},
                                                         {"parameterName": "thema", "queryName": q_param}]}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

# ---------------------------------------------------------------- Seiten

SCORE_COLS = [
    ("time_points", "Zeitangaben (max. 25)", num(1)),
    ("reach_points", "Erreichbarkeit (max. 25)", num(1)),
    ("machine_points", "Maschinenlesbarkeit (max. 25)", num(1)),
    ("completeness_points", "Vollständigkeit (max. 25)", num(1)),
]

def page_overview():
    L = [
        text(["## Metadatenqualität im Berliner Open-Data-Portal",
              "Dieses Dashboard misst, wie gut die Metadaten der Datensätze auf daten.berlin.de sind: "
              "ob Zeitangaben stimmen, Ressourcen maschinenlesbar und Links erreichbar sind und ob die Beschreibung vollständig ist. "
              "Grundlage ist ein eigener Qualitätsscore (0–100) aus vier gleich gewichteten Kriterien, aufgeteilt nach Quelle, Bereitsteller und Thema.",
              "",
              f"**Stand: Snapshot {SNAPSHOT}, 2.595 Datensätze.**"], 0, 0, 12, 3),
        text(["### Wichtigste Befunde",
              "- **Stromnetz Berlin:** Alle 250 geernteten Datensätze verweisen nur auf tote Links (HTTP 404), "
              "obwohl ihre Metadaten überdurchschnittlich vollständig sind (Ø 21,9 von 25 Punkten, gesamt 19,7).",
              "- **EU-High-Value-Datensätze:** nur 39,6 % maschinenlesbar (übrige 64,6 %). "
              "Von den nicht maschinenlesbaren bieten gut zwei Drittel nur einen Kartenbild-Dienst (WMS) an.",
              "- **Geodaten aus dem FIS-Broker:** 59 % haben keine maschinenlesbare Ressource, "
              "48 % gibt es nur als Kartenbild (WMS)."], 0, 3, 12, 3),
        counter("Datensätze", "ds_score", "COUNT(`dataset_id`)", num(0), 0, 6, 4),
        counter("Ø Qualitätsscore (mit Links)", "ds_score", "AVG(`quality_score`)", num(1), 4, 6, 4,
                description="Datensätze mit geprüften Links"),
        counter("maschinenlesbar", "ds_score", "AVG(`has_machine_readable`)", pct(1), 8, 6, 4,
                description="≥ 1 maschinenlesbare Ressource"),
        counter("tote Links", "ds_score", "SUM(`links_broken`) / SUM(`links_checked`)", pct(1), 0, 9, 6,
                description=f"Anteil an geprüften Links ({LINKS_CHECKED} von {RESOURCES_TOTAL})"),
        counter("ohne Aktualisierungsdatum", "ds_score", "1 - AVG(`has_date_updated`)", pct(1), 6, 9, 6,
                description="Feld date_updated leer"),
        bar("Ø Qualitätsscore je Quelle", "ds_score_by_source", "source_label", "Quelle", "quality_score",
            "Ø Score (mit Links)", y_expr="AVG(`quality_score`)", horizontal=True, sort="x-reversed",
            pos=(0, 12, 6, 8),
            description="Ohne Quelle „unbekannt“ (4 Datensätze) und ohne Datensätze ohne geprüfte Links"),
        bar("Automatisch geerntet vs. händisch gepflegt", "ds_q7_long", "origin", "Herkunft", "punkte", "Ø Punkte",
            color=("teil", "Teilpunkte"), stack=True, sort=None, pos=(6, 12, 6, 8),
            description="Ø Teilpunkte (je max. 25), Quelle „unbekannt“ ausgeschlossen"),
    ]
    return "ueberblick", "Überblick", L

def page_machine():
    L = [
        bar("Formatverteilung der Ressourcen (Top 12 + übrige)", "ds_q4a_top", "format", "Format", "ressourcen",
            "Ressourcen", y_expr="SUM(`ressourcen`)", color=("lesbarkeit", "Maschinenlesbar"), stack=True,
            y_fmt=num(0), pos=(0, 0, 8, 9), horizontal=True, sort="x-reversed"),
        text(["### Vorbehalt: WMS",
              "WMS (Web Map Service) liefert nur ein **Kartenbild**, keine Sachdaten. "
              "Deshalb zählt WMS (ebenso WMTS) bei uns **nicht als maschinenlesbar**. "
              "Viele Geodatensätze bieten nur WMS an; sie erhalten keine Punkte für Maschinenlesbarkeit "
              "und tragen im Detail den Grund „nur Kartenbild“.",
              "",
              "Die Formatverteilung gilt für alle Quellen (der Quellen-Filter wirkt hier nicht)."], 8, 0, 4, 9),
        bar("High-Value-Datensätze (EU) vs. übrige", "ds_q8b_long", "kennzahl", "Kennzahl", "wert", "Wert",
            color=("group_name", "Gruppe"), stack=False, sort=None, pos=(0, 9, 12, 7),
            description="High-Value-Datensätze nach EU-Durchführungsverordnung 2023/138; Score ohne Links"),
    ]
    return "maschinenlesbarkeit", "Maschinenlesbarkeit", L

def page_time():
    L = [
        bar("Datenstand je Quelle (Jahr der letzten Aktualisierung)", "ds_q1", "source_label", "Quelle",
            "share_in_source_pct", "Anteil in der Quelle (%)", y_expr="SUM(`share_in_source_pct`)",
            color=("age_bucket", "Datenstand"), stack=True, sort=None, horizontal=True, pos=(0, 0, 7, 8),
            description="Alt ist nicht schlecht: historische Daten dürfen ein altes Datum haben"),
        text(["### Hinweis zu temporal_granularity",
              "Das Feld **temporal_granularity** beschreibt die **Auflösung** der Daten (z. B. „Jahr“, „Monat“), "
              "**nicht den Aktualisierungsrhythmus**. Eine erste Annahme, es sei der Rhythmus, haben die Daten widerlegt. "
              "Deshalb prüfen wir nicht, ob ein Rhythmus eingehalten wird."], 7, 0, 5, 4),
        table("Widersprüchliche Zeitangaben je Regel und Quelle", "ds_q2",
              [("rule", "Regel", None), ("source_label", "Quelle", None), ("dataset_count", "Datensätze", num(0))],
              pos=(7, 4, 5, 9)),
        bar("Anteil Datensätze in Zeitreihen je Quelle", "ds_q3a", "source_label", "Quelle", "in_series_pct",
            "Anteil in Zeitreihen (%)", y_expr="SUM(`in_series_pct`)", pos=(0, 8, 7, 7),
            description="Zeitreihe = mehrere Jahrgänge desselben Datensatzes (Heuristik über den Namen)"),
        table("Geprüfte Reihen, die womöglich eingestellt sind (letzter Jahrgang ≤ 2023)", "ds_q3b",
              [("series_key", "Reihe", None), ("datasets", "Jahrgänge", num(0)),
               ("first_year", "erster Jahrgang", {"type": "number-plain", "abbreviation": "none",
                                                   "hideGroupSeparator": True,
                                                   "decimalPlaces": {"type": "exact", "places": 0}}),
               ("last_year", "letzter Jahrgang", {"type": "number-plain", "abbreviation": "none",
                                                   "hideGroupSeparator": True,
                                                   "decimalPlaces": {"type": "exact", "places": 0}})],
              pos=(0, 15, 8, 8),
              description="Nur von Hand geprüfte Reihen aus Webformular/Datenrubrik"),
        text(["### LOR-Reform 2021 prüfen",
              "Endet eine Reihe um 2020/2021, kann sie unter neuem Namen weiterlaufen: "
              "2021 wurden die Lebensweltlich orientierten Räume (LOR) neu zugeschnitten. "
              "Vor dem Urteil „eingestellt“ im Portal nach einer Nachfolge-Reihe suchen.",
              "",
              "Diese Tabelle wird vom Quellen-Filter nicht gefiltert."], 8, 15, 4, 8),
    ]
    return "zeit", "Zeitangaben & Zeitreihen", L

def page_links():
    L = [
        counter("tote Links (alle geprüften Ressourcen)", "ds_q6", "SUM(`broken`) / SUM(`checked_resources`)",
                pct(1), 0, 0, 4, 3),
        counter("geprüfte Links", "ds_q6", "SUM(`checked_resources`)", num(0), 4, 0, 4, 3),
        counter("davon tot", "ds_q6", "SUM(`broken`)", num(0), 8, 0, 4, 3),
        bar("Anteil toter Links je Quelle", "ds_q6", "source_label", "Quelle", "broken_pct", "tote Links (%)",
            y_expr="SUM(`broken`) * 100.0 / SUM(`checked_resources`)", pos=(0, 3, 8, 8),
            description=f"Link-Check am {SNAPSHOT}: HTTP 4xx/5xx, DNS-Fehler oder Timeout = tot"),
        text(["### So wurde geprüft",
              f"Jeder Ressourcen-Link wurde am {SNAPSHOT} einmal abgerufen (erst HEAD, bei Fehler GET). "
              "Tot heißt: HTTP-Fehler 4xx/5xx, DNS-Fehler oder Zeitüberschreitung (15 s). "
              "Ein einmaliger Check kann vorübergehende Ausfälle erwischen."], 8, 3, 4, 8),
        table("Hosts mit den meisten defekten Links (nur Hosts mit ≥ 20 Links)", "ds_q6b",
              [("host", "Host", None), ("checked_links", "geprüfte Links", num(0)),
               ("broken", "defekt", num(0)), ("broken_pct", "Anteil defekt (%)", num(1))],
              pos=(0, 11, 12, 7), description="Gilt für alle Quellen (der Quellen-Filter wirkt hier nicht)"),
    ]
    return "erreichbarkeit", "Erreichbarkeit", L

def page_publishers():
    L = [
        table("Bereitsteller mit mindestens 10 Datensätzen, schwächste zuerst", "ds_q8",
              [("publisher_short", "Bereitsteller", None), ("dataset_count", "n", num(0)),
               ("avg_score", "Ø Score", num(1)),
               ("avg_time", "Ø Zeit", num(1)), ("avg_reach", "Ø Erreichb.", num(1)),
               ("avg_machine", "Ø Maschinenl.", num(1)), ("avg_completeness", "Ø Vollst.", num(1))],
              pos=(0, 0, 12, 10),
              description="Kurznamen; Langnamen im Datensatz-Detail (Filter und Tooltip am Titel). Ø Score mit Links, Teilpunkte je max. 25. Quellen-Filter wirkt hier nicht."),
        bar("Ø Qualitätsscore je Thema", "ds_q9", "theme", "Thema", "avg_score", "Ø Score (mit Links)",
            horizontal=True, sort="x", pos=(0, 10, 12, 10),
            extra=[("dataset_count", "Datensätze"), ("avg_score_without_links", "Ø Score ohne Links")],
            description="Ein Datensatz kann zu mehreren Themen gehören. Themen mit wenigen Datensätzen schwanken stark."),
    ]
    return "bereitsteller", "Bereitsteller & Themen", L

def page_detail():
    L = [
        field_filter("Bereitsteller", "filter-multi-select", "publisher_name", ["ds_detail"], (0, 0, 5, 2)),
        theme_param_filter((5, 0, 3, 2)),
        field_filter("Score-Bereich (mit Links)", "range-slider", "quality_score", ["ds_detail"], (8, 0, 4, 2)),
        table("Datensätze mit Score und Gründen (schwächste zuerst)", "ds_detail",
              [("quality_score", "Score", num(1)),
               ("reasons", "Gründe für Punktabzug", None),
               ("title", "Titel", None,
                {"displayAs": "link", "linkUrlTemplate": "{{ portal_url }}", "linkTextTemplate": "{{ title }}",
                 "linkTitleTemplate": "{{ publisher_name }} · Quelle: {{ source_label_long }}",
                 "linkOpenInNewTab": True}),
               ("publisher_short", "Bereitsteller", None), ("source_label", "Quelle", None),
               ("time_points", "Zeit", num(1)), ("reach_points", "Erreichb.", num(1)),
               ("machine_points", "Maschinenl.", num(1)), ("completeness_points", "Vollst.", num(1))],
              pos=(0, 2, 12, 16), hidden_fields=("portal_url", "publisher_name", "source_label_long"),
              description="Score mit Links, Teilpunkte je max. 25. Titel anklicken öffnet daten.berlin.de/datensaetze/<name>; "
                          "Maus über dem Titel zeigt den Langnamen des Bereitstellers. Keine Personendaten."),
    ]
    return "detail", "Datensatz-Detail", L

def page_method():
    L = [
        text(["### Datenquelle",
              "CKAN-API von datenregister.berlin.de (`package_search`), Abruf als Snapshot am **13.11.2026**: "
              "2.632 Einträge, davon **2.595 Datensätze** (`berlin_type = datensatz`) mit 6.228 Ressourcen. "
              "Die Daten werden normalisiert in Databricks (Schema `workspace.opendata`) geladen; alle Auswertungen sind SQL-Views.",
              "",
              "Es werden keine Personendaten gespeichert, nur ob Kontaktangaben vorhanden sind."], 0, 0, 6, 5),
        text(["### Qualitätsscore: 4 × 25 Punkte",
              "- **Zeitangaben (25):** Aktualisierungsdatum 10, Zeitraum 5, keine Widersprüche 10",
              "- **Erreichbarkeit (25):** Anteil erreichbarer Ressourcen-Links × 25",
              "- **Maschinenlesbarkeit (25):** mindestens eine maschinenlesbare Ressource",
              "- **Vollständigkeit (25):** Format bei jeder Ressource 10, Beschreibung ≥ 100 Zeichen 5, ≥ 3 Schlagwörter 5, offene Lizenz 5",
              "",
              "„Score ohne Links“ rechnet die übrigen 75 Punkte auf 100 hoch. Datensätze ohne geprüften Link haben keinen Score mit Links."],
             6, 0, 6, 5),
        text(["### Vorbehalte",
              "- Der Score ist eine **eigene Definition**, keine offizielle Kennzahl. Deshalb stehen die Teilpunkte immer daneben.",
              "- **WMS/WMTS** liefern nur ein Kartenbild und zählen nicht als maschinenlesbar.",
              "- **Zeitreihen** werden heuristisch über den Datensatznamen erkannt (Jahreszahlen, Stichtage, IDs entfernt); nur ein Teil ist von Hand geprüft.",
              f"- **Link-Check** einmalig am {SNAPSHOT}; vorübergehende Ausfälle können als tot zählen. "
              "Die 404-Fehler bei Stromnetz Berlin wurden stichprobenhaft per GET bestätigt.",
              "- Der Quellen-Filter wirkt nur auf Auswertungen, die nach Quelle aufgeteilt sind."], 0, 5, 6, 6),
        text(["### KI-Nutzung",
              "Das Projekt wurde mit KI-Unterstützung erstellt: **Claude (Chat)** für Planung, ER-Modell und SQL-Analysen, "
              "**Claude Code** für Harvester, Transform, Deploy-Skripte, Link-Check und dieses Dashboard. "
              "Die Abfragen werden lokal gegen die exportierten Tabellen getestet und Ergebnisse stichprobenhaft im Portal nachgesehen. "
              "Alle Entscheidungen hat der Autor nachvollzogen.",
              "",
              "### Quellcode",
              REPO_HINT], 6, 5, 6, 6),
    ]
    return "methodik", "Methodik", L

def build():
    datasets = []
    for name, (display, sql) in DATASETS.items():
        lines = sql.strip().splitlines()
        ds = {"name": name, "displayName": display,
              "queryLines": [l + "\n" for l in lines[:-1]] + [lines[-1]]}
        if name == "ds_detail":
            ds["parameters"] = [THEMA_PARAM]
        datasets.append(ds)

    pages = []
    for fn in (page_overview, page_machine, page_time, page_links, page_publishers, page_detail, page_method):
        name, display, layout = fn()
        pages.append({"name": name, "displayName": display, "pageType": "PAGE_TYPE_CANVAS", "layout": layout})
    pages.append({"name": "globale_filter", "displayName": "Globale Filter", "pageType": "PAGE_TYPE_GLOBAL_FILTERS",
                  "layout": [field_filter("Quelle", "filter-multi-select", "source_label",
                                          SOURCE_FILTER_DATASETS, (0, 0, 1, 2))]})
    return {"datasets": datasets, "pages": pages,
            "uiSettings": {"theme": {"widgetHeaderAlignment": "ALIGNMENT_UNSPECIFIED"}, "applyModeEnabled": False}}

if __name__ == "__main__":
    out = Path(__file__).with_name("opendata_quality.lvdash.json")
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"geschrieben: {out}")
