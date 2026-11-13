# Lokaler Smoke-Test: lädt data/tables/*.csv in SQLite und führt alle Views aus sql/analysis aus.
# Aufruf aus dem Repo-Root: python3 tests/test_views_sqlite.py
import sqlite3,csv,glob,os,re,sys
con=sqlite3.connect(":memory:")
con.create_function("year",1,lambda d: int(d[:4]) if d else None)
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
for v in ["q1_data_age ORDER BY source_label, age_bucket","q2_time_conflicts","q3a_series_fragmentation","q3b_possibly_discontinued","q4a_format_distribution ORDER BY resource_count DESC","q4b_machine_readable_by_source","q5_completeness","q6_link_reachability","q7_harvested_vs_manual","q8_publisher_ranking","q9_theme_ranking","q8b_hvd_vs_rest"]:
  print("==",v); show("SELECT * FROM "+v)
show("SELECT COUNT(*), ROUND(AVG(quality_score_without_links),1), MIN(quality_score_without_links), MAX(quality_score_without_links) FROM v_dataset_score")
show("SELECT SUM(dataset_count) FROM q1_data_age")
