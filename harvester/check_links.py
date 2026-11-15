"""Check whether the resource URLs from data/tables/resource.csv are reachable (Ticket 2.5).

Usage: python harvester/check_links.py

Input:  data/tables/resource.csv, data/tables/harvest_run.csv
Output: data/tables/link_check.csv (columns of table link_check in sql/schema.sql,
        UTF-8, header, empty = NULL, checked_at in UTC)

Polite and parallel: at most 16 requests at the same time, at most 2 per host
(each host gets at most 2 workers that share its queue, so a slow host never blocks the
others), timeout 15 s, 1 retry. Method: HEAD first, GET with stream=True (headers only)
if HEAD fails or answers with an error status (e.g. 405/501). A HEAD answer 404/410 is
final (no GET), because some servers rate-limit 404 answers.

Rate limiting (429): the host waits Retry-After, on further 429 in a row the wait doubles
(up to 60 s), a normal answer halves it and keeps it as gap between requests. A host that answered 429 is checked by one worker
only. A URL answered with 429 goes back to the end of its host queue (the block seems to be
per URL and is kept alive by asking again), after 5 such answers 429 is stored with a note.

Map services (format WMS/WFS/WMTS) without query string get
"?SERVICE=<type>&REQUEST=GetCapabilities" appended, otherwise the servers answer 400.

Resumable: resource_ids already present in link_check.csv are skipped, new results are
appended. Delete the file for a completely new check.
"""

import csv
import queue
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

TABLES = Path("data/tables")
RESOURCE_FILE = TABLES / "resource.csv"
HARVEST_RUN_FILE = TABLES / "harvest_run.csv"
OUTPUT_FILE = TABLES / "link_check.csv"

COLUMNS = ["link_check_id", "resource_id", "harvest_run_id", "checked_at", "http_status",
           "is_reachable", "response_time_ms", "content_type", "error_message"]

MAX_WORKERS = 16
MAX_PER_HOST = 2
TIMEOUT_S = 15
RETRIES = 1
RETRY_PAUSE_S = 2
PROGRESS_EVERY = 500
USER_AGENT = "opendata-quality-watch (Schulprojekt; Kontakt im Repo)"
MAP_SERVICES = {"WMS", "WFS", "WMTS"}
UNCHECKED_SCHEMES = {"mailto", "ftp", "ftps", "sftp"}

# Rate limiting (429), see module docstring. www.berlin.de, for example, answers 429 with
# "Retry-After: 2" after about 10 quick 404 answers and then lets one 404 through every 20-50 s.
RATE_LIMIT_DEFAULT_WAIT_S = 2
RATE_LIMIT_MAX_WAIT_S = 60
RATE_LIMIT_ATTEMPTS = 5
FINAL_HEAD_STATUS = {404, 410}

_host_next_request = defaultdict(float)  # host -> earliest time.monotonic() for the next request
_host_backoff = defaultdict(float)       # host -> current 429 wait (0 = not rate-limited right now)
_throttled_hosts = set()                 # hosts that answered 429 at least once
_host_timing_lock = threading.Lock()
_local = threading.local()


def wait_for_host(host):
    """Sleep until the host may be asked again."""
    while True:
        with _host_timing_lock:
            wait = _host_next_request[host] - time.monotonic()
        if wait <= 0:
            return
        time.sleep(min(wait, 5))


def rate_limited(host, retry_after):
    """Register a 429 answer: wait Retry-After, double the wait on further 429 in a row."""
    try:
        first_wait = max(float(retry_after), 1)
    except (TypeError, ValueError):
        first_wait = RATE_LIMIT_DEFAULT_WAIT_S
    with _host_timing_lock:
        backoff = _host_backoff[host]
        backoff = first_wait if backoff == 0 else min(2 * backoff, RATE_LIMIT_MAX_WAIT_S)
        _host_backoff[host] = backoff
        _throttled_hosts.add(host)
        _host_next_request[host] = max(_host_next_request[host], time.monotonic() + backoff)


def answered(host):
    """A normal answer (not 429) halves the 429 wait of the host and keeps that gap."""
    with _host_timing_lock:
        backoff = _host_backoff[host] / 2
        _host_backoff[host] = backoff if backoff >= 1 else 0
        _host_next_request[host] = max(_host_next_request[host], time.monotonic() + _host_backoff[host])


def session():
    """One requests.Session per worker thread (keep-alive, Session is not thread-safe)."""
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        _local.session = s
    return _local.session


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def prepare_url(url, format_code):
    """Return (url to request, note) – appends GetCapabilities for map services."""
    if format_code in MAP_SERVICES and not urlsplit(url).query:
        base = url.rstrip("?")
        return f"{base}?SERVICE={format_code}&REQUEST=GetCapabilities", \
            f"GetCapabilities angehängt ({format_code})"
    return url, None


def classify_exception(exc):
    """Short German error text whose prefix is used for the summary categories."""
    text = str(exc)
    if isinstance(exc, requests.exceptions.SSLError):
        kind = "SSL-Fehler"
    elif isinstance(exc, requests.exceptions.Timeout):
        kind = "Timeout"
    elif isinstance(exc, requests.exceptions.ConnectionError) and any(
            marker in text for marker in ("NameResolution", "getaddrinfo", "nodename nor servname",
                                          "Name or service not known", "No address associated")):
        kind = "DNS-Fehler"
    elif isinstance(exc, requests.exceptions.TooManyRedirects):
        kind = "Zu viele Weiterleitungen"
    elif isinstance(exc, requests.exceptions.ConnectionError):
        kind = "Verbindungsfehler"
    else:
        kind = "Fehler"
    return f"{kind}: {type(exc).__name__}: {text}"[:300]


def request_once(url):
    """HEAD, then GET (stream, headers only) if HEAD fails or returns an error status.

    Returns (status, content_type, elapsed_ms, error, retry_after). error is None if a status
    was received. 429, 404 and 410 on HEAD are returned directly (a GET would not change the
    result, but would count against a rate limit for 404 answers).
    """
    s = session()
    start = time.monotonic()
    try:
        r = s.head(url, timeout=TIMEOUT_S, allow_redirects=True)
        r.close()
        if r.status_code < 400 or r.status_code == 429 or r.status_code in FINAL_HEAD_STATUS:
            return (r.status_code, r.headers.get("Content-Type"), int((time.monotonic() - start) * 1000),
                    None, r.headers.get("Retry-After"))
    except requests.exceptions.RequestException:
        pass  # fall back to GET
    start = time.monotonic()
    try:
        with s.get(url, timeout=TIMEOUT_S, allow_redirects=True, stream=True) as r:
            return (r.status_code, r.headers.get("Content-Type"), int((time.monotonic() - start) * 1000),
                    None, r.headers.get("Retry-After"))
    except requests.exceptions.RequestException as exc:
        return None, None, None, exc, None


class RateLimited(Exception):
    """429 that should be retried later (see host_worker)."""


def check(resource, attempts_429=0):
    """Check one resource and return a dict with the link_check columns (without id/run).

    Raises RateLimited on 429 as long as the URL has had fewer than RATE_LIMIT_ATTEMPTS of them.
    """
    raw_url = (resource["url"] or "").strip()
    result = {"resource_id": resource["resource_id"], "http_status": None, "is_reachable": False,
              "response_time_ms": None, "content_type": None, "error_message": None}
    parts = urlsplit(raw_url)
    scheme = parts.scheme.lower()

    if scheme in UNCHECKED_SCHEMES:
        result["error_message"] = "nicht geprüft (Schema)"
    elif scheme not in ("http", "https") or not parts.hostname:
        result["error_message"] = "keine URL" if not raw_url or not scheme or not parts.netloc \
            else "nicht geprüft (Schema)"
    else:
        url, note = prepare_url(raw_url, resource["format_code"])
        host = parts.hostname.lower()
        retries = 0
        while True:
            wait_for_host(host)
            status, content_type, elapsed_ms, error, retry_after = request_once(url)
            if status == 429:
                rate_limited(host, retry_after)
                if attempts_429 + 1 < RATE_LIMIT_ATTEMPTS:
                    raise RateLimited
                break
            answered(host)
            if (error is not None or (status or 0) >= 500) and retries < RETRIES:
                retries += 1
                time.sleep(RETRY_PAUSE_S)
            else:
                break
        result.update(http_status=status, content_type=content_type, response_time_ms=elapsed_ms,
                      is_reachable=status is not None and status < 400)
        messages = [m for m in (note, classify_exception(error) if error else None) if m]
        if status == 429:
            messages.append(f"Rate-Limit (429) bei {RATE_LIMIT_ATTEMPTS} Versuchen")
        result["error_message"] = "; ".join(messages) or None

    result["checked_at"] = now_utc()
    return result


def host_of(resource):
    return (urlsplit((resource["url"] or "").strip()).hostname or "").lower()


def host_worker(host, worker_no, host_queue, results):
    """Check the resources of one host one after another (up to MAX_PER_HOST of these per host).

    Only worker 0 continues once the host has answered 429.
    """
    while True:
        if worker_no > 0 and host in _throttled_hosts:
            return
        try:
            resource = host_queue.get_nowait()
        except queue.Empty:
            return
        try:
            results.put(check(resource, resource.get("_attempts_429", 0)))
        except RateLimited:
            resource["_attempts_429"] = resource.get("_attempts_429", 0) + 1
            host_queue.put(resource)  # try again after the other URLs of this host
        except Exception as exc:  # never lose a resource because of an unexpected error
            results.put({"resource_id": resource["resource_id"], "http_status": None,
                         "is_reachable": False, "response_time_ms": None, "content_type": None,
                         "error_message": f"Fehler: {type(exc).__name__}: {exc}"[:300],
                         "checked_at": now_utc()})


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def category(row):
    """Summary category of an output row (dict with string values)."""
    if row["is_reachable"] == "true":
        return "erreichbar"
    status = row["http_status"]
    if status == "429":
        return "429 Rate-Limit"
    if status:
        return "4xx" if 400 <= int(status) < 500 else "5xx" if int(status) >= 500 else "sonstiger Status"
    message = row["error_message"] or ""
    for kind in ("Timeout", "DNS-Fehler", "SSL-Fehler", "Verbindungsfehler", "keine URL", "nicht geprüft"):
        if kind in message:
            return kind
    return "sonstiger Fehler"


def summary(urls_by_resource):
    with OUTPUT_FILE.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    counts = Counter(category(r) for r in rows)
    print(f"\n== Zusammenfassung ({len(rows)} Ressourcen in {OUTPUT_FILE})")
    for name in ("erreichbar", "4xx", "429 Rate-Limit", "5xx", "Timeout", "DNS-Fehler", "SSL-Fehler",
                 "Verbindungsfehler", "sonstiger Status", "sonstiger Fehler", "keine URL", "nicht geprüft"):
        if counts[name]:
            print(f"  {name:<20} {counts[name]:>6}  ({100 * counts[name] / len(rows):5.1f} %)")
    appended = sum(1 for r in rows if "GetCapabilities angehängt" in (r["error_message"] or ""))
    print(f"  GetCapabilities angehängt: {appended}")
    failing_hosts = Counter(
        (urlsplit(urls_by_resource.get(r["resource_id"], "")).hostname or "(keine)").lower()
        for r in rows if r["is_reachable"] != "true")
    print("\n== Top-10 Hosts mit den meisten Fehlern")
    for host, n in failing_hosts.most_common(10):
        print(f"  {n:>5}  {host}")


def main():
    with RESOURCE_FILE.open(encoding="utf-8", newline="") as f:
        resources = list(csv.DictReader(f))
    with HARVEST_RUN_FILE.open(encoding="utf-8", newline="") as f:
        harvest_run_id = int(max(csv.DictReader(f), key=lambda r: int(r["harvest_run_id"]))["harvest_run_id"])
    urls_by_resource = {r["resource_id"]: (r["url"] or "").strip() for r in resources}

    done, next_id = set(), 1
    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                done.add(row["resource_id"])
                next_id = max(next_id, int(row["link_check_id"]) + 1)
    todo = [r for r in resources if r["resource_id"] not in done]
    by_host = defaultdict(list)
    for r in todo:
        by_host[host_of(r)].append(r)
    print(f"{len(resources)} Ressourcen, {len(done)} bereits geprüft, {len(todo)} zu prüfen "
          f"auf {len(by_host)} Hosts (harvest_run_id {harvest_run_id})", flush=True)

    results = queue.Queue()
    write_header = not OUTPUT_FILE.exists()
    started = time.monotonic()
    with OUTPUT_FILE.open("a", encoding="utf-8", newline="") as out, \
            ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        # largest hosts first, so that they do not end up alone at the end of the run
        for host, host_resources in sorted(by_host.items(), key=lambda item: len(item[1]), reverse=True):
            host_queue = queue.Queue()
            for r in host_resources:
                host_queue.put(r)
            for worker_no in range(min(MAX_PER_HOST, len(host_resources))):
                pool.submit(host_worker, host, worker_no, host_queue, results)
        running = Counter()
        for i in range(1, len(todo) + 1):
            result = results.get()
            result.update(link_check_id=next_id, harvest_run_id=harvest_run_id)
            next_id += 1
            writer.writerow({k: csv_value(result[k]) for k in COLUMNS})
            out.flush()
            running["erreichbar" if result["is_reachable"] else "nicht erreichbar"] += 1
            if i % PROGRESS_EVERY == 0 or i == len(todo):
                minutes = (time.monotonic() - started) / 60
                print(f"  {i}/{len(todo)} geprüft nach {minutes:.1f} min – "
                      f"erreichbar {running['erreichbar']}, nicht erreichbar {running['nicht erreichbar']}",
                      flush=True)

    summary(urls_by_resource)


if __name__ == "__main__":
    main()
