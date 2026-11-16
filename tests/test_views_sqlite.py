# Lokaler Smoke-Test: lädt data/tables/*.csv in SQLite und führt alle Views aus sql/analysis aus.
# Aufruf aus dem Repo-Root: python3 tests/test_views_sqlite.py
import sqlite3,csv,glob,os,re,sys
from urllib.parse import urlsplit
con=sqlite3.connect(":memory:")
con.create_function("year",1,lambda d: int(d[:4]) if d else None)
# Databricks parse_url(url, part) nachbilden, hier nur HOST
con.create_function("parse_url",2,lambda u,part: (urlsplit(u).hostname if u and part=="HOST" else None))
for f in glob.glob("data/tables/*.csv"):
  t=os.path.basename(f)[:-4]
  rows=list(csv.reader(open(f,encoding="utf-8")))
  h=rows[0]
  con.execute(f"CREATE TABLE {t} ({','.join(h)})")
  conv=lambda v: None if v=="" else (1 if v=="true" else 0 if v=="false" else v)
  data=[[conv(v) for v in r] for r in rows[1:]]
  # numeric casting
  def num(v):
    if isinstance(v,str) and re.fullmatch(r"-?\d+",v): return int(v)
    return v
  data=[[num(v) for v in r] for r in data]
  if data: con.executemany(f"INSERT INTO {t} VALUES ({','.join('?'*len(h))})",data)
con.execute("CREATE TABLE IF NOT EXISTS link_check (link_check_id,resource_id,harvest_run_id,checked_at,http_status,is_reachable,response_time_ms,content_type,error_message)")
for f in sorted(glob.glob("sql/analysis/*.sql")):
  sql="\n".join(l for l in open(f,encoding="utf-8").read().splitlines() if not l.strip().startswith("--")).replace("CREATE OR REPLACE VIEW","CREATE VIEW")
  for st in [s for s in sql.split(";") if s.strip() and not all(l.strip().startswith("--") or not l.strip() for l in s.splitlines())]:
    try: con.execute(st)
    except Exception as e: print("ERR",f,e); sys.exit(1)
def show(q,lim=30):
  cur=con.execute(q); print(" | ".join(c[0] for c in cur.description))
  for r in cur.fetchmany(lim): print(r)
  print()
for v in ["q1_data_age ORDER BY source_label, age_bucket","q2_time_conflicts","q3a_series_fragmentation","q3b_possibly_discontinued","q4a_format_distribution ORDER BY resource_count DESC","q4b_machine_readable_by_source","q5_completeness","q6_link_reachability","q7_harvested_vs_manual","q8_publisher_ranking","q9_theme_ranking","q8b_hvd_vs_rest","q4c_offers_machine_readable ORDER BY dimension, offer_count DESC","q6b_broken_hosts ORDER BY broken DESC"]:
  print("==",v); show("SELECT * FROM "+v)
show("SELECT COUNT(*), ROUND(AVG(quality_score_without_links),1), MIN(quality_score_without_links), MAX(quality_score_without_links) FROM v_dataset_score")
show("SELECT SUM(dataset_count) FROM q1_data_age")
# reasons: Stichprobe und Plausibilität (NULL nur bei vollen 100 Punkten bzw. 75 ohne Links)
show("SELECT reasons, COUNT(*) n FROM v_dataset_score GROUP BY reasons ORDER BY n DESC",12)
show("SELECT COUNT(*) FROM v_dataset_score WHERE reasons IS NULL AND NOT (quality_score = 100)")
show("SELECT SUM(checked_links), SUM(broken) FROM q6b_broken_hosts")
show("SELECT COUNT(DISTINCT dataset_id), COUNT(*) FROM v_dataset_theme")

# Ankerwerte Q4c (Angebote statt Datensätze, Snapshot 13.11.2026), auch in Dashboard und Ergebnisseite.
# Bricht mit Exit-Code 1 ab, wenn ein Wert nicht mehr stimmt.
q4c={(d,g):(n,mr,pct,multi) for d,g,n,mr,pct,multi in con.execute(
  "SELECT dimension, group_name, offer_count, with_machine_readable, machine_readable_pct, multi_dataset_offers FROM q4c_offers_machine_readable")}
anchors=[
  ("HVD 208 Angebote / 113 maschinenlesbar (54,3 %)", q4c[("HVD","High-Value-Angebot")][:3], (208,113,54.3)),
  ("übrige 1764 / 1492 (84,6 %)",                    q4c[("HVD","übrige")][:3],             (1764,1492,84.6)),
  ("FIS-Broker 982 / 664 (67,6 %), 318 ohne",        q4c[("Quelle","FIS-Broker")][:3],      (982,664,67.6)),
  ("alle 1972 / 1605",                               q4c[("gesamt","alle Angebote")][:2],   (1972,1605)),
  ("FIS-Angebote mit > 1 Datensatz",                 q4c[("Quelle","FIS-Broker")][3],       622),
  ("Summe Angebote je Quelle = alle",                sum(v[0] for (d,_),v in q4c.items() if d=="Quelle"), 1972),
  ("Summe Datensätze über Angebote = Datensätze",    con.execute("SELECT dataset_count FROM q4c_offers_machine_readable WHERE dimension='gesamt'").fetchone()[0],
                                                     con.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]),
]
print("== Ankerwerte Q4c")
bad=0
for label,got,want in anchors:
  ok=got==want; bad+=not ok
  print(f"  {'OK    ' if ok else 'FEHLER'} {label}: {got}" + ("" if ok else f" erwartet {want}"))
if bad: sys.exit(1)
