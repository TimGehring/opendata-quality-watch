"""Transform a raw CKAN snapshot into normalized CSV tables for Databricks.

Usage: python harvester/transform.py data/raw/ckan_snapshot_<YYYY-MM-DD>.json

Outputs:
  data/tables/<table>.csv                  one file per table (UTF-8, header, empty = NULL)
  data/review/publisher_candidates.csv     similar publisher names for manual review
  data/review/series_top20.csv             largest detected series for manual review
  data/review/series_statistics_to_verify.csv  series from webform/api-datenrubrik with >= 3 years

Seeds: seeds/publisher_merge.csv (manual publisher merges),
       seeds/series_override.csv (series key overrides, manually_verified)
"""

import csv
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "seeds"
TABLE_DIR = ROOT / "data" / "tables"
REVIEW_DIR = ROOT / "data" / "review"
SCHEMA_FILE = ROOT / "sql" / "schema.sql"

SOURCE_API = "https://datenregister.berlin.de/api/3/action/package_search"
PLACEHOLDERS = {"", "n.n.", "-", "unbekannt"}
SIMILARITY_THRESHOLD = 0.9
MAX_PERIOD_YEAR = 2029
TOP_SERIES = 20

SOURCE_SYSTEM_LABELS = {
    "harvest-fisbroker": "Harvester FIS-Broker",
    "harvest-stromnetzberlin": "Harvester Stromnetz Berlin",
    "webform": "Webformular",
    "api-datenrubrik": "API Datenrubrik",
    "api-datenrubrik-dw": "API Datenrubrik (DW)",
    "api-gitaction": "API GitHub Action",
    "simplesearch": "SimpleSearch",
    "unbekannt": "unbekannt",
}
UNKNOWN_SOURCE = "unbekannt"
# sources whose series are listed in series_statistics_to_verify.csv
STATISTICS_SOURCES = {"webform", "api-datenrubrik"}
MIN_STATISTICS_YEARS = 3

YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
NUMERIC_ID_SUFFIX_RE = re.compile(r"-\d{6,8}$")
REFERENCE_DATE_RE = re.compile(r"(?<!\d)\d{1,2}[-_]\d{1,2}[-_](?:19|20)\d{2}(?!\d)")
MONTH_BEFORE_YEAR_RE = re.compile(
    r"(?<![a-z])(januar|februar|maerz|marz|april|mai|juni|juli|august|september|"
    r"oktober|november|dezember)[-_](?=(?:19|20)\d{2}(?!\d))"
)
SEPARATORS_RE = re.compile(r"[-_]+")

warnings: list[str] = []


# --- helpers ---------------------------------------------------------------


def is_filled(value) -> bool:
    """A value is filled if it is not None and not a placeholder."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in PLACEHOLDERS
    return True


def clean(value) -> str | None:
    """Return the stripped string or None for empty values (placeholders are kept)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_name(text: str) -> str:
    """trim + lower + collapse whitespace."""
    return " ".join(text.split()).lower()


def parse_date(value, field: str, dataset_name: str) -> str | None:
    """Return an ISO date string or None; invalid values produce a warning."""
    if not is_filled(value):
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        warnings.append(f"invalid date {field}={value!r} in {dataset_name} -> NULL")
        return None


def parse_timestamp(value, field: str, record_name: str) -> str | None:
    """Return 'YYYY-MM-DD HH:MM:SS' (seconds precision) or None."""
    if not is_filled(value):
        return None
    try:
        return datetime.fromisoformat(str(value).strip()).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        warnings.append(f"invalid timestamp {field}={value!r} in {record_name} -> NULL")
        return None


def read_seed(name: str) -> list[dict]:
    with open(SEED_DIR / name, encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def extras_value(dataset: dict, key: str):
    for extra in dataset.get("extras") or []:
        if extra.get("key") == key:
            return extra.get("value")
    return None


# --- series heuristic -------------------------------------------------------


def strip_id_suffix(dataset: dict) -> str:
    """Remove an appended numeric ID (-\\d{6,8}) or the FIS-Broker guid hash (-<guid[:8]>)."""
    name = dataset["name"]
    guid = extras_value(dataset, "guid")
    if guid and len(guid) >= 8 and name.endswith("-" + guid[:8].lower()):
        return name[: -9]
    return NUMERIC_ID_SUFFIX_RE.sub("", name)


def series_key(base_name: str) -> str:
    """Name without reference dates, month names before years and 4-digit years."""
    key = REFERENCE_DATE_RE.sub("", base_name)
    key = MONTH_BEFORE_YEAR_RE.sub("", key)
    key = YEAR_RE.sub("", key)
    return SEPARATORS_RE.sub("-", key).strip("-")


def period_year(base_name: str, coverage_to: str | None) -> int | None:
    """Highest year in the name, else year of temporal_coverage_to; only years <= 2029."""
    years = [int(y) for y in YEAR_RE.findall(base_name) if int(y) <= MAX_PERIOD_YEAR]
    if years:
        return max(years)
    if coverage_to and int(coverage_to[:4]) <= MAX_PERIOD_YEAR:
        return int(coverage_to[:4])
    return None


# --- table builders ---------------------------------------------------------


def build_publishers(datasets: list[dict], merges: list[dict]):
    """Merge author values if their normalized text is identical, plus the manual
    pairs from seeds/publisher_merge.csv (alias -> canonical_name), nothing else."""
    variants: dict[str, Counter] = defaultdict(Counter)
    for ds in datasets:
        if is_filled(ds.get("author")):
            variants[normalize_name(ds["author"])][ds["author"]] += 1

    canonical_names = {}
    for merge in merges:
        alias, canonical = normalize_name(merge["alias"]), normalize_name(merge["canonical_name"])
        for norm, label in ((alias, merge["alias"]), (canonical, merge["canonical_name"])):
            if norm not in variants:
                raise SystemExit(f"publisher_merge.csv: {label!r} not found in snapshot")
        if alias in canonical_names:
            raise SystemExit(f"publisher_merge.csv: {merge['alias']!r} merged twice")
        canonical_names[alias] = canonical
    for alias, canonical in canonical_names.items():
        if canonical in canonical_names:
            raise SystemExit(f"publisher_merge.csv: canonical {canonical!r} is itself an alias")
        variants[canonical] += variants.pop(alias)
    merged_names = {normalize_name(m["canonical_name"]): " ".join(m["canonical_name"].split())
                    for m in merges}

    publishers, aliases, alias_to_id, counts = [], [], {}, {}
    for publisher_id, norm in enumerate(sorted(variants), start=1):
        name = merged_names.get(norm) or variants[norm].most_common(1)[0][0].strip()
        publishers.append({"publisher_id": publisher_id, "name": " ".join(name.split()),
                           "name_normalized": norm})
        counts[publisher_id] = sum(variants[norm].values())
        for alias in sorted(variants[norm]):
            aliases.append({"alias": alias, "publisher_id": publisher_id})
            alias_to_id[alias] = publisher_id
    return publishers, aliases, alias_to_id, counts


def publisher_candidates(publishers: list[dict], counts: dict) -> list[dict]:
    """Pairs of distinct publishers with difflib ratio > threshold (review only)."""
    rows = []
    for i, a in enumerate(publishers):
        for b in publishers[i + 1:]:
            ratio = difflib.SequenceMatcher(None, a["name_normalized"], b["name_normalized"]).ratio()
            if ratio > SIMILARITY_THRESHOLD:
                rows.append({
                    "ratio": f"{ratio:.3f}",
                    "publisher_id_a": a["publisher_id"], "name_a": a["name"],
                    "datasets_a": counts[a["publisher_id"]],
                    "publisher_id_b": b["publisher_id"], "name_b": b["name"],
                    "datasets_b": counts[b["publisher_id"]],
                })
    return sorted(rows, key=lambda r: r["ratio"], reverse=True)


def build_licenses(datasets: list[dict]) -> list[dict]:
    licenses: dict[str, dict] = {}
    for ds in datasets:
        lid = ds["license_id"]
        row = {"license_id": lid, "title": clean(ds.get("license_title")) or lid,
               "url": clean(ds.get("license_url")), "is_open": bool(ds.get("isopen"))}
        if lid in licenses and licenses[lid]["is_open"] != row["is_open"]:
            warnings.append(f"license {lid}: inconsistent isopen across datasets")
        licenses.setdefault(lid, row)
    return sorted(licenses.values(), key=lambda r: r["license_id"])


def build_source_systems(datasets: list[dict]) -> list[dict]:
    codes = sorted({source_system_id(ds) for ds in datasets})
    rows = []
    for code in codes:
        if code not in SOURCE_SYSTEM_LABELS:
            warnings.append(f"source_system {code!r} has no label, using code")
        rows.append({"source_system_id": code, "label": SOURCE_SYSTEM_LABELS.get(code, code),
                     "is_harvested": code.startswith("harvest-")})
    return rows


def source_system_id(dataset: dict) -> str:
    """berlin_source, or 'unbekannt' if it is missing (no NULL foreign key)."""
    if is_filled(dataset.get("berlin_source")):
        return dataset["berlin_source"].strip()
    return UNKNOWN_SOURCE


def build_themes(datasets: list[dict]):
    themes, links = {}, []
    for ds in datasets:
        for group in ds.get("groups") or []:
            themes.setdefault(group["name"], (clean(group.get("title")) or group["name"]))
            links.append({"dataset_id": ds["id"], "theme_id": group["name"]})
    rows = [{"theme_id": k, "label": v} for k, v in sorted(themes.items())]
    return rows, links


def build_series(datasets: list[dict], overrides: list[dict]):
    """Return (series rows, dataset_id -> series_id, dataset_id -> period_year,
    review rows, series_id -> members).

    seeds/series_override.csv: canonical_key (if set) replaces the heuristic key,
    verified=true sets series.manually_verified for the resulting series."""
    info, groups = {}, defaultdict(list)
    for ds in datasets:
        base = strip_id_suffix(ds)
        cov_to = parse_date(ds.get("temporal_coverage_to"), "temporal_coverage_to", ds["name"])
        info[ds["id"]] = period_year(base, cov_to)
        key = series_key(base)
        if key:
            groups[key].append(ds)

    remap, verified = {}, set()
    for row in overrides:
        key, canonical = row["series_key"].strip(), row["canonical_key"].strip()
        if key not in groups:
            warnings.append(f"series_override.csv: series_key {key!r} not found in snapshot")
            continue
        if canonical:
            if canonical not in groups:
                raise SystemExit(f"series_override.csv: canonical_key {canonical!r} not found in snapshot")
            remap[key] = canonical
        if row["verified"].strip().lower() == "true":
            verified.add(canonical or key)
    for key, canonical in remap.items():
        if canonical in remap:
            raise SystemExit(f"series_override.csv: canonical_key {canonical!r} is itself remapped")
        groups[canonical] += groups.pop(key)

    series_rows, assignment, review, members_by_id = [], {}, [], {}
    members_by_size = sorted(((k, v) for k, v in groups.items() if len(v) >= 2),
                             key=lambda kv: (-len(kv[1]), kv[0]))
    for series_id, (key, members) in enumerate(members_by_size, start=1):
        years = [info[ds["id"]] for ds in members if info[ds["id"]] is not None]
        series_rows.append({"series_id": series_id, "series_key": key, "dataset_count": len(members),
                            "first_period_year": min(years) if years else None,
                            "last_period_year": max(years) if years else None,
                            "manually_verified": key in verified})
        members_by_id[series_id] = members
        for ds in members:
            assignment[ds["id"]] = series_id
        if series_id <= TOP_SERIES:
            names = sorted(ds["name"] for ds in members)
            review.append({**series_rows[-1], "example_names": " | ".join(names[:4])})
    return series_rows, assignment, info, review, members_by_id


def series_statistics_review(series_rows, members_by_id, period_years) -> list[dict]:
    """Series with members from STATISTICS_SOURCES and >= 3 distinct period years (manual check)."""
    rows = []
    for series in series_rows:
        members = [ds for ds in members_by_id[series["series_id"]]
                   if source_system_id(ds) in STATISTICS_SOURCES]
        years = {period_years[ds["id"]] for ds in members if period_years[ds["id"]] is not None}
        if len(years) >= MIN_STATISTICS_YEARS:
            rows.append({"series_key": series["series_key"], "count": len(members),
                         "min_year": min(years), "max_year": max(years),
                         "example_name": min(ds["name"] for ds in members)})
    return sorted(rows, key=lambda r: (-r["count"], r["series_key"]))


def build_datasets(datasets, run_id, alias_to_id, series_assignment, period_years, hvd_codes):
    rows = []
    for ds in datasets:
        name = ds["name"]
        hvd = clean(ds.get("hvd_category"))
        if hvd and hvd not in hvd_codes:
            raise SystemExit(f"hvd_category {hvd!r} missing in seeds/hvd_category.csv")
        rows.append({
            "dataset_id": ds["id"],
            "harvest_run_id": run_id,
            "name": name,
            "title": clean(ds.get("title")) or name,
            "publisher_id": alias_to_id.get(ds.get("author")),
            "ckan_organization": clean((ds.get("organization") or {}).get("title")),
            "source_system_id": source_system_id(ds),
            "license_id": ds["license_id"],
            "hvd_code": hvd,
            "series_id": series_assignment.get(ds["id"]),
            "period_year": period_years[ds["id"]],
            "is_open": bool(ds.get("isopen")),
            "notes_length": len((ds.get("notes") or "").strip()),
            "num_tags": len(ds.get("tags") or []),
            "num_resources": len(ds.get("resources") or []),
            "has_maintainer": is_filled(ds.get("maintainer")),
            "has_contact_email": is_filled(ds.get("maintainer_email")) or is_filled(ds.get("author_email")),
            "date_released": parse_date(ds.get("date_released"), "date_released", name),
            "date_updated": parse_date(ds.get("date_updated"), "date_updated", name),
            "temporal_coverage_from": parse_date(ds.get("temporal_coverage_from"), "temporal_coverage_from", name),
            "temporal_coverage_to": parse_date(ds.get("temporal_coverage_to"), "temporal_coverage_to", name),
            "temporal_granularity": clean(ds.get("temporal_granularity")),
            "geographical_coverage": clean(ds.get("geographical_coverage")),
            "geographical_granularity": clean(ds.get("geographical_granularity")),
            "metadata_created": parse_timestamp(ds.get("metadata_created"), "metadata_created", name),
            "metadata_modified": parse_timestamp(ds.get("metadata_modified"), "metadata_modified", name),
        })
    return rows


def build_resources(datasets, format_map):
    rows = []
    for ds in datasets:
        for res in ds.get("resources") or []:
            raw = res.get("format") or ""
            if raw not in format_map:
                raise SystemExit(f"format {raw!r} missing in seeds/format_alias.csv")
            size = res.get("size")
            size = size if isinstance(size, int) else None
            label = f"resource {res['id']}"
            rows.append({
                "resource_id": res["id"],
                "dataset_id": ds["id"],
                "position": res.get("position") or 0,
                "name": clean(res.get("name")),
                "url": clean(res.get("url")),
                "format_raw": clean(raw),
                "format_code": format_map[raw],
                "mimetype": clean(res.get("mimetype")) if is_filled(res.get("mimetype")) else None,
                "size_bytes": size,
                "last_modified": parse_timestamp(res.get("last_modified"), "last_modified", label),
                "created": parse_timestamp(res.get("created"), "created", label),
                "has_mimetype": is_filled(res.get("mimetype")),
                "has_size": size is not None and size > 0,
                "has_last_modified": is_filled(res.get("last_modified")),
            })
    return rows


# --- output and checks --------------------------------------------------------


def schema_columns() -> dict[str, list[str]]:
    """Column order per table as defined in sql/schema.sql."""
    tables, current = {}, None
    for line in SCHEMA_FILE.read_text(encoding="utf-8").splitlines():
        if match := re.match(r"CREATE TABLE (\w+) \(", line):
            current = tables.setdefault(match.group(1), [])
        elif line.startswith(")"):
            current = None
        elif current is not None and (match := re.match(r"\s+(\w+)\s+(STRING|INT|BIGINT|DATE|TIMESTAMP|BOOLEAN)\b", line)):
            current.append(match.group(1))
    return tables


def to_csv_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([to_csv_value(row[c]) for c in columns])


PRIMARY_KEYS = {
    "harvest_run": ["harvest_run_id"], "publisher": ["publisher_id"], "publisher_alias": ["alias"],
    "source_system": ["source_system_id"], "license": ["license_id"], "hvd_category": ["hvd_code"],
    "theme": ["theme_id"], "series": ["series_id"], "format": ["format_code"],
    "format_alias": ["raw_format"], "dataset": ["dataset_id"],
    "dataset_theme": ["dataset_id", "theme_id"], "resource": ["resource_id"],
}
FOREIGN_KEYS = [  # (table, column, referenced table, referenced column)
    ("publisher_alias", "publisher_id", "publisher", "publisher_id"),
    ("format_alias", "format_code", "format", "format_code"),
    ("dataset", "harvest_run_id", "harvest_run", "harvest_run_id"),
    ("dataset", "publisher_id", "publisher", "publisher_id"),
    ("dataset", "source_system_id", "source_system", "source_system_id"),
    ("dataset", "license_id", "license", "license_id"),
    ("dataset", "hvd_code", "hvd_category", "hvd_code"),
    ("dataset", "series_id", "series", "series_id"),
    ("dataset_theme", "dataset_id", "dataset", "dataset_id"),
    ("dataset_theme", "theme_id", "theme", "theme_id"),
    ("resource", "dataset_id", "dataset", "dataset_id"),
    ("resource", "format_code", "format", "format_code"),
]


def check_integrity(tables: dict[str, list[dict]]) -> list[str]:
    """PK unique and not NULL, every non-NULL FK points to an existing PK."""
    violations = []
    for table, key in PRIMARY_KEYS.items():
        seen = Counter(tuple(row[c] for c in key) for row in tables[table])
        violations += [f"{table}: PK NULL {k}" for k in seen if None in k]
        violations += [f"{table}: PK duplicate {k} ({n}x)" for k, n in seen.items() if n > 1]
    for table, column, ref_table, ref_column in FOREIGN_KEYS:
        existing = {row[ref_column] for row in tables[ref_table]}
        for row in tables[table]:
            if row[column] is not None and row[column] not in existing:
                violations.append(f"{table}.{column}={row[column]!r} -> {ref_table}.{ref_column} missing")
    return violations


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    snapshot_path = Path(sys.argv[1])
    raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    datasets = [ds for ds in raw if ds.get("berlin_type") == "datensatz"]

    match = re.search(r"(\d{4}-\d{2}-\d{2})", snapshot_path.name)
    if not match:
        sys.exit("snapshot file name must contain the date YYYY-MM-DD")
    snapshot_date = date.fromisoformat(match.group(1))
    run_id = int(snapshot_date.strftime("%Y%m%d"))

    formats = [{**r, "machine_readable": r["machine_readable"] == "true",
                "open_data_stars": int(r["open_data_stars"]) if r["open_data_stars"] else None}
               for r in read_seed("format.csv")]
    format_alias_seed = read_seed("format_alias.csv")
    format_map = {r["raw_format"]: (r["format_code"] or None) for r in format_alias_seed}
    hvd_rows = [{"hvd_code": r["hvd_code"], "label": r["label"] or None} for r in read_seed("hvd_category.csv")]

    publishers, aliases, alias_to_id, publisher_counts = build_publishers(
        datasets, read_seed("publisher_merge.csv"))
    themes, dataset_themes = build_themes(datasets)
    series, series_assignment, period_years, series_review, series_members = build_series(
        datasets, read_seed("series_override.csv"))
    resources = build_resources(datasets, format_map)

    tables = {
        "harvest_run": [{
            "harvest_run_id": run_id, "snapshot_date": snapshot_date.isoformat(),
            "snapshot_file": snapshot_path.name, "source_api": SOURCE_API,
            "datasets_total": len(raw), "datasets_loaded": len(datasets),
            "resources_loaded": len(resources),
            "transformed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }],
        "publisher": publishers,
        "publisher_alias": aliases,
        "source_system": build_source_systems(datasets),
        "license": build_licenses(datasets),
        "hvd_category": hvd_rows,
        "theme": themes,
        "series": series,
        "format": formats,
        # empty raw format maps to NULL and cannot be a PK, so it stays only in the seed
        "format_alias": [{"raw_format": r["raw_format"], "format_code": r["format_code"]}
                         for r in format_alias_seed if r["raw_format"]],
        "dataset": build_datasets(datasets, run_id, alias_to_id, series_assignment, period_years,
                                  {r["hvd_code"] for r in hvd_rows}),
        "dataset_theme": dataset_themes,
        "resource": resources,
    }

    columns = schema_columns()
    for table, rows in tables.items():
        if table not in columns:
            sys.exit(f"table {table} missing in {SCHEMA_FILE.name}")
        if rows and set(rows[0]) != set(columns[table]):
            sys.exit(f"{table}: columns differ from schema.sql: {sorted(set(rows[0]) ^ set(columns[table]))}")

    violations = check_integrity(tables)
    if violations:
        print(f"INTEGRITY CHECK FAILED ({len(violations)} violations):")
        for violation in violations[:50]:
            print(f"  {violation}")
        sys.exit(1)

    for table, rows in tables.items():
        write_csv(TABLE_DIR / f"{table}.csv", rows, columns[table])
    candidates = publisher_candidates(publishers, publisher_counts)
    write_csv(REVIEW_DIR / "publisher_candidates.csv", candidates,
              ["ratio", "publisher_id_a", "name_a", "datasets_a", "publisher_id_b", "name_b", "datasets_b"])
    write_csv(REVIEW_DIR / "series_top20.csv", series_review,
              ["series_id", "series_key", "dataset_count", "first_period_year", "last_period_year", "example_names"])
    statistics_review = series_statistics_review(series, series_members, period_years)
    write_csv(REVIEW_DIR / "series_statistics_to_verify.csv", statistics_review,
              ["series_key", "count", "min_year", "max_year", "example_name"])

    for warning in warnings:
        print(f"WARNING: {warning}")
    print(f"Snapshot: {snapshot_path.name} (harvest_run_id {run_id})")
    print("Integrity check: OK (all PKs unique, all FKs resolved)")
    print("Rows per table:")
    for table, rows in tables.items():
        print(f"  {table:<16} {len(rows):>6}")
    print("  link_check            0  (not filled by transform)")
    in_series = sum(1 for d in tables["dataset"] if d["series_id"] is not None)
    print(f"Datasets in series: {in_series} of {len(datasets)}")
    verified = sum(1 for s in tables["series"] if s["manually_verified"])
    print(f"Series manually verified: {verified} of {len(tables['series'])}")
    print(f"Review: {len(candidates)} publisher candidates, top {len(series_review)} series, "
          f"{len(statistics_review)} statistics series to verify -> {REVIEW_DIR}")


if __name__ == "__main__":
    main()
