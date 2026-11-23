"""Rebuild Aurora's run context from Garmin CSV + archived weather.

Sources
  garmin_export.csv     start time, Source File, Lap Splits (tracked)
  dashboard/index.html  Classic comments + the 3 recorded weather rows (local only)
  Open-Meteo archive    hourly weather, fetched now and stored as values only

Run after a Garmin export refresh. The Classic dashboard must exist locally for
its comments; only values derived here are written to tracked files.

Nothing in the output contains latitude, longitude, or a place name. The local
default coordinates are used only to fetch values during this build.
"""

import csv
import datetime
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CLASSIC = os.path.join(ROOT, "dashboard", "index.html")
CSV_PATH = os.path.join(ROOT, "garmin_export.csv")
OUT_JSON = os.path.join(ROOT, "flow_outputs", "run_context.json")
TEMPLATE = os.path.join(ROOT, "flow_outputs", "aurora_dashboard.html")

FIELDS = (
    "temperature_2m", "apparent_temperature", "relative_humidity_2m",
    "dew_point_2m", "precipitation", "wind_speed_10m",
)


def local_parts(utc_text):
    """Classic's convention: UTC timestamp shifted by a fixed -6 h.

    This reproduces the three recorded Classic weather rows exactly (verified
    against 2026-09-09) and keeps the archived values stable across DST rules.
    """
    dt = datetime.datetime.fromisoformat(
        str(utc_text).strip().replace("Z", "+00:00"))
    shifted = dt - datetime.timedelta(hours=6)
    return shifted.date().isoformat(), shifted.hour


def split_text(value):
    """Normalise a CSV Lap Splits cell to comma-separated m:ss values."""
    out = []
    for chunk in str(value or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            continue
        if len(nums) == 3:
            seconds = nums[0] * 3600 + nums[1] * 60 + nums[2]
        elif len(nums) == 2:
            seconds = nums[0] * 60 + nums[1]
        else:
            continue
        if seconds <= 0:
            continue
        out.append("%d:%02d" % (seconds // 60, seconds % 60))
    return out


def rounded(value, places=1):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, places)


def fetch_archive(lat, lon, start_date, end_date):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(FIELDS),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "auto",
    }
    query = urllib.parse.urlencode(params)
    urls = (
        "https://archive-api.open-meteo.com/v1/archive?" + query,
        "https://api.open-meteo.com/v1/forecast?" + query,
    )
    last_error = None
    for url in urls:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = json.load(response)
                hourly = data.get("hourly") or {}
                if hourly.get("time"):
                    return hourly
            except Exception as exc:  # network retry; never print coordinates
                last_error = exc
                time.sleep(1 + attempt)
    raise RuntimeError("weather fetch failed: %s" % type(last_error).__name__)


# --- local inputs -----------------------------------------------------------
with open(CLASSIC, encoding="utf-8") as fh:
    classic_html = fh.read()

coord_match = re.search(
    r"const CHASKA\s*=\s*\{\s*lat:\s*([-\d.]+)\s*,\s*lon:\s*([-\d.]+)",
    classic_html)
if not coord_match:
    raise SystemExit("default weather coordinates not found")
default_lat, default_lon = float(coord_match.group(1)), float(coord_match.group(2))

base_match = re.search(r"const baseRuns\s*=\s*(\[.*?\]);\s*\n",
                       classic_html, re.S)
if not base_match:
    raise SystemExit("baseRuns not found")
base_runs = json.loads(base_match.group(1))

classic_by_date = {}
for row in base_runs:
    date = row.get("date")
    if not date:
        continue
    notes = []
    for key in ("note", "note2"):
        text = str(row.get(key) or "").strip()
        if text and text not in notes:
            notes.append(text)
    item = {
        "tempF": row.get("tempF"),
        "weather": row.get("weather") if isinstance(row.get("weather"), dict) else {},
        "comments": notes,
        "lat": row.get("lat"),
        "lon": row.get("lon"),
    }
    if date in classic_by_date:
        prior = classic_by_date[date]
        item["comments"] = list(dict.fromkeys(prior["comments"] + item["comments"]))
        if prior["tempF"] is not None and item["tempF"] is None:
            item["tempF"] = prior["tempF"]
        for key, value in prior["weather"].items():
            item["weather"].setdefault(key, value)
    classic_by_date[date] = item

with open(CSV_PATH, newline="", encoding="utf-8-sig") as fh:
    csv_rows = list(csv.DictReader(fh))

runs = {}
by_activity = {}
for row in csv_rows:
    source_file = row.get("Source File") or ""
    if "_" not in source_file:
        continue
    native = os.path.splitext(source_file.split("_", 1)[1])[0]
    activity_id = "garmin:" + native
    utc_text = row.get("Date (UTC)") or row.get("Date") or ""
    weather_date, hour = local_parts(utc_text)
    live_date = (row.get("Date") or "")[:10]
    if not live_date or not weather_date:
        continue

    classic = classic_by_date.get(weather_date) or classic_by_date.get(live_date) or {}
    lat, lon = default_lat, default_lon
    has_gps = (isinstance(classic.get("lat"), (int, float))
               and isinstance(classic.get("lon"), (int, float)))
    if has_gps:
        lat, lon = float(classic["lat"]), float(classic["lon"])
    location = "GPS recorded at start" if has_gps else "Default weather location"

    runs[live_date] = {
        "activityId": activity_id,
        "startLocal": "%s %02d:00" % (weather_date, hour),
        "location": classic.get("location") or location,
        "tempF": None,
        "weather": {},
        "comments": list(classic.get("comments") or []),
        "splits": split_text(row.get("Lap Splits")),
        "_lat": lat,
        "_lon": lon,
        "_weatherDate": weather_date,
        "_hour": hour,
        "_classicTemp": classic.get("tempF"),
        "_classicWeather": classic.get("weather") or {},
    }
    by_activity[activity_id] = live_date

# --- archived weather -------------------------------------------------------
groups = {}
for item in runs.values():
    key = (item["_lat"], item["_lon"])
    groups.setdefault(key, []).append(item)

for (lat, lon), items in groups.items():
    dates = [it["_weatherDate"] for it in items]
    hourly = fetch_archive(lat, lon, min(dates), max(dates))
    times = hourly.get("time") or []
    index_by_time = {}
    for i, stamp in enumerate(times):
        stamp = str(stamp)
        if len(stamp) >= 13:
            index_by_time[(stamp[:10], int(stamp[11:13]))] = i

    lookup = {
        "temperature_2m": ("tempF", 1, False),
        "apparent_temperature": ("feelsF", 1, False),
        "relative_humidity_2m": ("humidityPct", 0, True),
        "dew_point_2m": ("dewF", 1, False),
        "precipitation": ("precipIn", None, False),
        "wind_speed_10m": ("windMph", 0, True),
    }
    for item in items:
        idx = index_by_time.get((item["_weatherDate"], item["_hour"]))
        fetched = {}
        if idx is not None:
            for field, (name, places, integer) in lookup.items():
                values = hourly.get(field) or []
                if idx >= len(values):
                    continue
                value = values[idx]
                if value is None:
                    continue
                if integer:
                    fetched[name] = int(round(float(value)))
                elif places is None:
                    fetched[name] = float(value)
                else:
                    fetched[name] = rounded(value, places)

        classic_wx = item.pop("_classicWeather")
        merged = {}
        for field in ("tempF", "feelsF", "humidityPct", "dewF",
                      "precipIn", "windMph"):
            value = classic_wx.get(field)
            if value is None:
                value = fetched.get(field)
            if value is not None:
                merged[field] = value

        classic_temp = item.pop("_classicTemp")
        item["tempF"] = classic_temp if classic_temp is not None else merged.get("tempF")
        item["weather"] = merged
        item.pop("_lat")
        item.pop("_lon")
        item.pop("_weatherDate")
        item.pop("_hour")

context = {
    "source": "Garmin CSV start times and Lap Splits; Open-Meteo archive weather; Classic comments",
    "note": "Values only. No raw coordinates, no place names, no live lookup in the page.",
    "runs": {date: runs[date] for date in sorted(runs)},
    "byActivity": {key: by_activity[key] for key in sorted(by_activity)},
}

with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(context, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

compact = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
compact = compact.replace("<", "\\u003c").replace(">", "\\u003e")
line = "const RUN_CONTEXT=" + compact + ";"

with open(TEMPLATE, encoding="utf-8", newline="") as fh:
    text = fh.read()
new_text, count = re.subn(r"(?m)^const RUN_CONTEXT=.*;\n", line + "\n", text, count=1)
if count != 1:
    raise SystemExit("expected one RUN_CONTEXT line in template")
with open(TEMPLATE, "w", encoding="utf-8", newline="") as fh:
    fh.write(new_text)

print("runs", len(runs))
print("activities", len(by_activity))
print("with_temp", sum(1 for r in runs.values() if r["tempF"] is not None))
print("with_weather", sum(1 for r in runs.values() if r["weather"]))
print("with_splits", sum(1 for r in runs.values() if r["splits"]))
print("with_comments", sum(1 for r in runs.values() if r["comments"]))
print("inline_line_chars", len(line))
