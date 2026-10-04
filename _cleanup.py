import trainingdb

conn = trainingdb.connect()
c = conn.cursor()

print("=== rows I inserted (source_system='test') ===")
rows = list(c.execute(
    "SELECT activity_id, title, distance_mi, avg_hr, first_seen_utc"
    " FROM activities WHERE source_system='test' ORDER BY activity_id"))
for r in rows:
    print("  %s" % dict(r))
print("  total: %d" % len(rows))

print()
print("=== any other table touched? ===")
for t in ("review_items", "load_snapshots", "strength_sessions",
          "activity_raw_refs", "profile"):
    try:
        n = c.execute("SELECT COUNT(*) c FROM %s" % t).fetchone()["c"]
        print("  %-20s %d" % (t, n))
    except Exception:
        print("  %-20s (absent)" % t)

if rows:
    c.execute("DELETE FROM activities WHERE source_system='test'")
    conn.commit()
    print()
    print("deleted %d test rows" % len(rows))

print()
print("=== after ===")
print("  activities            %d" % c.execute(
    "SELECT COUNT(*) c FROM activities").fetchone()["c"])
print("  open reviews          %d" % c.execute(
    "SELECT COUNT(*) c FROM review_items WHERE state='open'").fetchone()["c"])
print("  stray test rows       %d" % c.execute(
    "SELECT COUNT(*) c FROM activities WHERE source_system='test'").fetchone()["c"])

conn.close()