"""Validate the GPS claim: coordinate ranges, validity, and time fields."""
import glob
import os
import stat
import sys
from collections import Counter

import fitparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

files = sorted(glob.glob(os.path.join(paths.fit_dir(), "*.fit")))
SCALE = 180.0 / (2**31)

bad = Counter()
lats, lons = [], []
time_fields = Counter()
tz_fields = Counter()
first_fit = None

for path in files:
    fit = fitparse.FitFile(path)
    if first_fit is None:
        first_fit = (os.path.basename(path), fit)
    for r in fit.get_messages("record"):
        raw_lat = raw_lon = None
        for f in r:
            if f.name == "position_lat":
                raw_lat = f.value
            elif f.name == "position_long":
                raw_lon = f.value
        if raw_lat is not None and raw_lon is not None:
            lat, lon = raw_lat * SCALE, raw_lon * SCALE
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                bad["out_of_range"] += 1
            if abs(lat) < 1e-6 and abs(lon) < 1e-6:
                bad["null_island_0_0"] += 1
            lats.append(lat)
            lons.append(lon)
        for f in r:
            if "time" in f.name:
                time_fields[f.name] += 1
    for s in fit.get_messages("session"):
        for f in s:
            if "time" in f.name or "zone" in f.name or "utc" in f.name:
                tz_fields[f.name] += 1

print("=== coordinate validity ===")
print("points checked   :", len(lats))
print("out of range     :", bad["out_of_range"])
print("null island 0,0  :", bad["null_island_0_0"])
if lats:
    print("lat range        : %.4f to %.4f" % (min(lats), max(lats)))
    print("lon range        : %.4f to %.4f" % (min(lons), max(lons)))
print()
print("=== time fields in record messages ===")
for k, v in time_fields.most_common(8):
    print("  %-28s %d" % (k, v))
print()
print("=== time/zone fields in session messages ===")
for k, v in tz_fields.most_common(12):
    print("  %-28s %d" % (k, v))
print()
print("=== file_id / manufacturer of first file ===")
if first_fit:
    name, fit = first_fit
    print("file:", name)
    for m in fit.get_messages("file_id"):
        for f in m:
            if f.name in ("type", "manufacturer", "time_created"):
                print("  %-16s %s" % (f.name, f.value))
