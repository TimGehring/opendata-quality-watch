"""Download all dataset metadata from the Berlin CKAN portal as a raw JSON snapshot."""

import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

API_URL = "https://datenregister.berlin.de/api/3/action/package_search"
PAGE_SIZE = 1000
PAUSE_SECONDS = 1
TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
USER_AGENT = "opendata-quality-watch/0.1 (+https://datenregister.berlin.de; metadata quality research)"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch_page(session: requests.Session, start: int) -> dict:
    """Fetch one result page; retry with exponential backoff on failure."""
    params = {"rows": PAGE_SIZE, "start": start, "sort": "id asc"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
            if not payload.get("success"):
                raise RuntimeError(f"API returned success=false: {payload.get('error')}")
            return payload["result"]
        except (requests.RequestException, ValueError, RuntimeError) as error:
            if attempt == MAX_RETRIES:
                raise
            wait = 2**attempt
            print(f"  start={start}: attempt {attempt} failed ({error}), retrying in {wait} s")
            time.sleep(wait)
    raise AssertionError("unreachable")


def fetch_all_datasets() -> tuple[list[dict], int]:
    """Page through package_search until all datasets are loaded."""
    datasets: list[dict] = []
    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        start = 0
        total = None
        while total is None or start < total:
            if start > 0:
                time.sleep(PAUSE_SECONDS)
            result = fetch_page(session, start)
            total = result["count"]
            page = result["results"]
            print(f"  start={start}: {len(page)} datasets (count={total})")
            if not page:
                break
            datasets.extend(page)
            start += PAGE_SIZE
    return datasets, total


def main() -> None:
    """Fetch the snapshot, verify its size and write it to data/raw/."""
    print(f"Fetching {API_URL}")
    datasets, total = fetch_all_datasets()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"ckan_snapshot_{date.today().isoformat()}.json"
    output_path.write_text(json.dumps(datasets, ensure_ascii=False, indent=1), encoding="utf-8")

    unique_ids = len({d["id"] for d in datasets})
    print(f"Loaded datasets: {len(datasets)} (unique ids: {unique_ids}, count: {total})")
    print(f"Saved to: {output_path}")
    if len(datasets) != total or unique_ids != total:
        sys.exit(f"ERROR: loaded {len(datasets)} ({unique_ids} unique) datasets, expected {total}")


if __name__ == "__main__":
    main()
