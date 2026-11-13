"""Profile field fill rates and value distributions of a CKAN snapshot.

Usage: python harvester/profile_fields.py data/raw/ckan_snapshot_<YYYY-MM-DD>.json
"""

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

PLACEHOLDERS = {"", "n.n.", "-", "unbekannt"}

DATASET_FIELDS = [
    "berlin_type", "berlin_source", "author", "organization.title", "maintainer",
    "maintainer_email", "license_id", "isopen", "date_released", "date_updated",
    "temporal_granularity", "temporal_coverage_from", "temporal_coverage_to",
    "geographical_granularity", "hvd_category", "num_resources", "num_tags", "groups[].name",
]
RESOURCE_FILL_FIELDS = ["last_modified", "size", "mimetype"]
TOP_VALUES = 5
TOP_FORMATS = 15


def get_values(record: dict, field: str) -> list:
    """Return the raw value(s) of a field; supports 'a.b' and 'list[].key' paths."""
    if "[]." in field:
        list_key, sub_key = field.split("[].")
        return [item.get(sub_key) for item in record.get(list_key) or []]
    value = record
    for part in field.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return [value]


def placeholder_of(value) -> str | None:
    """Return the normalized placeholder if value is one, else None."""
    if isinstance(value, str) and value.strip().lower() in PLACEHOLDERS:
        return value.strip().lower()
    return None


def is_filled(value) -> bool:
    """A value is filled if it is not None, not an empty list and not a placeholder."""
    return value is not None and value != [] and placeholder_of(value) is None


def format_value(value, max_len: int = 50) -> str:
    """Shorten a value for table output and escape pipe characters."""
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def pct(part: int, total: int) -> str:
    """Format a share as percentage."""
    return f"{100 * part / total:.1f} %" if total else "–"


def profile_records(records: list[dict], fields: list[str]) -> tuple[list[str], dict]:
    """Build table rows (fill rate + top values) and placeholder counts per field."""
    rows = []
    placeholders: dict[str, Counter] = {}
    for field in fields:
        filled = 0
        value_counts: Counter = Counter()
        placeholder_counts: Counter = Counter()
        for record in records:
            values = get_values(record, field)
            good = [v for v in values if is_filled(v)]
            if good:
                filled += 1
            value_counts.update(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in good)
            placeholder_counts.update(p for p in map(placeholder_of, values) if p is not None)
        top = ", ".join(f"{format_value(v)} ({n})" for v, n in value_counts.most_common(TOP_VALUES))
        rows.append(f"| `{field}` | {pct(filled, len(records))} | {top} |")
        if placeholder_counts:
            placeholders[field] = placeholder_counts
    return rows, placeholders


def placeholder_rows(placeholders: dict[str, Counter]) -> list[str]:
    """Render placeholder counts as table rows."""
    return [
        f"| `{field}` | " + ", ".join(f'"{p}" ({n})' for p, n in counts.most_common()) + " |"
        for field, counts in placeholders.items()
    ]


def build_report(datasets: list[dict], snapshot_name: str) -> str:
    """Assemble the full markdown profile report."""
    resources = [r for d in datasets for r in d.get("resources") or []]
    lines = [
        f"# Feldprofil {snapshot_name}",
        "",
        f"- Datensätze: **{len(datasets)}**",
        f"- Ressourcen: **{len(resources)}**",
        f"- Als nicht gefüllt gelten: `null`, leere Liste sowie Platzhalter {sorted(PLACEHOLDERS)}"
        " (case-insensitive, getrimmt).",
        "",
        "## Datensatz-Felder",
        "",
        "| Feld | Anteil gefüllt | Top-5-Werte (Häufigkeit) |",
        "|---|---:|---|",
    ]
    dataset_rows, dataset_placeholders = profile_records(datasets, DATASET_FIELDS)
    lines += dataset_rows

    lines += ["", "## Ressourcen", "", f"### Format (Top {TOP_FORMATS})", "", "| Format | Anzahl | Anteil |", "|---|---:|---:|"]
    formats = Counter((r.get("format") or "").strip() or "(leer)" for r in resources)
    lines += [f"| {format_value(f)} | {n} | {pct(n, len(resources))} |" for f, n in formats.most_common(TOP_FORMATS)]
    lines.append(f"\nVerschiedene Formatwerte insgesamt: {len(formats)}")

    lines += ["", "### Füllgrad", "", "| Feld | Anteil gefüllt | Top-5-Werte (Häufigkeit) |", "|---|---:|---|"]
    resource_rows, resource_placeholders = profile_records(resources, RESOURCE_FILL_FIELDS + ["format"])
    lines += resource_rows

    lines += ["", "## Platzhalter (als nicht gefüllt gezählt)", "", "| Feld | Platzhalter (Anzahl) |", "|---|---|"]
    all_placeholders = {**dataset_placeholders, **{f"resources[].{k}": v for k, v in resource_placeholders.items()}}
    lines += placeholder_rows(all_placeholders) or ["| – | keine |"]

    lines += ["", "## `date_updated` nach Jahr", "", "| Jahr | Anzahl | Anteil |", "|---|---:|---:|"]
    years = Counter(
        str(d["date_updated"])[:4] if is_filled(d.get("date_updated")) else "(leer)" for d in datasets
    )
    lines += [f"| {y} | {n} | {pct(n, len(datasets))} |" for y, n in sorted(years.items(), reverse=True)]
    return "\n".join(lines) + "\n"


def main() -> None:
    """Read the snapshot, print the report and save it to data/profile_<date>.md."""
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    snapshot_path = Path(sys.argv[1])
    datasets = json.loads(snapshot_path.read_text(encoding="utf-8"))

    match = re.search(r"\d{4}-\d{2}-\d{2}", snapshot_path.name)
    snapshot_date = match.group(0) if match else date.today().isoformat()
    report = build_report(datasets, snapshot_path.name)
    print(report)

    output_path = Path(__file__).resolve().parent.parent / "data" / f"profile_{snapshot_date}.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
