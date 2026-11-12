"""Server-side CalTrak nutrition parsing and daily aggregation.

CalTrak exports one row per food entry, so several rows can share a date. The
dashboard wants one daily total per date, which is what this module produces.

Where the rows live: the committed ``nutrition_log.csv`` is a schema template
with headers only. Ingested rows are written to the *local data directory*
(``paths.data_dir()/nutrition_log.csv``) so athlete nutrition is never published
to the public repository. The committed file stays the schema of record. Set
``GARMIN_NUTRITION_FILE`` to point somewhere else (tests do this).
"""

from __future__ import annotations

import csv
import datetime
import os
import tempfile

import paths

FIELDS = ("date", "calories", "protein", "carbs", "fat")
NUMERIC = ("calories", "protein", "carbs", "fat")

# CalTrak and hand-exported headers vary. Match the same aliases the committed
# Aurora app uses, so the server and the browser cannot disagree about a column.
ALIASES = {
    "date": ("date", "day"),
    "calories": ("calories", "kcal", "energy"),
    "protein": ("protein",),
    "carbs": ("carbs", "carbohydrates", "carb"),
    "fat": ("fat",),
}

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y")

NUTRITION_FILE = (os.environ.get("GARMIN_NUTRITION_FILE")
                  or os.path.join(paths.data_dir(), "nutrition_log.csv"))


class NutritionError(ValueError):
    """A CalTrak export or API payload that cannot be trusted."""


def _normalize_date(value):
    text = str(value or "").strip()
    if not text:
        raise NutritionError("date is required")
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise NutritionError(
        "invalid date %r (expected YYYY-MM-DD or M/D/YYYY)" % text)


def _number(value, field, where):
    if value is None or (isinstance(value, str) and not value.strip()):
        return 0.0
    if isinstance(value, bool):
        raise NutritionError("%s must be a number (%s)" % (field, where))
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise NutritionError("%s must be a number (%s)" % (field, where))
    if number != number or number in (float("inf"), float("-inf")):
        raise NutritionError("%s must be finite (%s)" % (field, where))
    if number < 0:
        raise NutritionError("%s cannot be negative (%s)" % (field, where))
    return number


def _fmt(number):
    return int(number) if float(number).is_integer() else round(number, 2)


def _header_index(header):
    """Map each canonical field to its column index, or None when absent."""
    lowered = [str(h).strip().lower() for h in header]
    index = {}
    for field, aliases in ALIASES.items():
        index[field] = next(
            (i for i, h in enumerate(lowered)
             if any(h == a or a in h for a in aliases)),
            None,
        )
    return index


def parse_caltrak_csv(text):
    """Parse a CalTrak CSV export into one aggregated row per date.

    Raises NutritionError on a missing date column, an unparseable date or a
    non-numeric/negative nutrition value. Empty numeric cells count as zero,
    matching the app's importer; a missing column is simply not summed.
    """
    if not isinstance(text, str) or not text.strip():
        raise NutritionError("CSV is empty")
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        raise NutritionError("CSV is empty")
    index = _header_index(rows[0])
    if index["date"] is None:
        raise NutritionError("CSV is missing a date column")

    totals = {}
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(str(cell).strip() for cell in row):
            continue
        date_i = index["date"]
        if date_i >= len(row):
            raise NutritionError("row %d has no date value" % line_no)
        date = _normalize_date(row[date_i])
        record = totals.setdefault(date, {f: 0.0 for f in NUMERIC})
        for field in NUMERIC:
            col = index[field]
            if col is None:
                continue
            value = row[col] if col < len(row) else ""
            record[field] += _number(value, field, "row %d" % line_no)
    return [dict(date=d, **{f: _fmt(totals[d][f]) for f in NUMERIC})
            for d in sorted(totals)]


def normalize_days(days):
    """Validate an API ``days`` list and return one row per date, sorted."""
    if not isinstance(days, list):
        raise NutritionError("'days' must be a list")
    merged = {}
    for i, day in enumerate(days):
        if not isinstance(day, dict):
            raise NutritionError("day %d must be an object" % i)
        date = _normalize_date(day.get("date"))
        record = {"date": date}
        for field in NUMERIC:
            if field == "calories":
                raw = day.get("calories", day.get("kcal", day.get("energy")))
            else:
                raw = day.get(field)
            record[field] = _fmt(_number(raw, field, "day %d" % i))
        merged[date] = record
    return [merged[d] for d in sorted(merged)]


def read_days(path=None):
    """Read daily totals from the local log, oldest first.

    A missing file is an empty log, not an error. A file with a malformed
    header is an error: silently returning [] would hide a corrupt log.
    """
    path = path or NUTRITION_FILE
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return []
    index = _header_index(rows[0])
    if index["date"] is None:
        raise NutritionError("%s is missing a date column" % path)
    out = {}
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(str(cell).strip() for cell in row):
            continue
        date_i = index["date"]
        if date_i >= len(row):
            raise NutritionError("%s row %d has no date" % (path, line_no))
        date = _normalize_date(row[date_i])
        record = {"date": date}
        for field in NUMERIC:
            col = index[field]
            value = row[col] if col is not None and col < len(row) else ""
            record[field] = _fmt(_number(value, field, "row %d" % line_no))
        out[date] = record
    return [out[d] for d in sorted(out)]


def _write_days(rows, path):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".nutrition-", suffix=".csv",
                               dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            for row in sorted(rows, key=lambda r: r["date"]):
                writer.writerow({f: row[f] for f in FIELDS})
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def upsert_days(days, path=None):
    """Merge validated daily totals into the local log, one row per date.

    Returns ``{"accepted": n, "upserted": m}`` where accepted counts validated
    input entries and upserted counts distinct dates written. Repeating the
    same date updates the existing row instead of appending a duplicate.
    """
    path = path or NUTRITION_FILE
    if not isinstance(days, list):
        raise NutritionError("'days' must be a list")
    normalized = normalize_days(days)
    existing = {row["date"]: row for row in read_days(path)}
    for row in normalized:
        existing[row["date"]] = row
    _write_days(list(existing.values()), path)
    return {"accepted": len(days), "upserted": len(normalized),
            "total_days": len(existing)}


def payload(path=None):
    """The GET /api/nutrition envelope."""
    rows = read_days(path)
    return {
        "days": rows,
        "count": len(rows),
        "fields": list(FIELDS),
        "source": "nutrition_log.csv",
        "storage": "local data directory (not published)",
    }
