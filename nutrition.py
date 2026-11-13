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
import hashlib
import json
import os
import secrets
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


# Health Connect uses its own field names and interval records. CalTrak writes
# one NutritionRecord per food entry on Android, so several records can share a
# day. The bridge app can also be set to "Daily" resolution, which sends one
# already-totalled record per local day. Both shapes are accepted.
HC_ALIASES = {
    "calories": ("calories", "kcal", "energy", "energy_kcal"),
    "protein": ("protein_grams", "protein"),
    "carbs": ("carbs_grams", "carbs", "carbohydrates", "carb"),
    "fat": ("fat_grams", "fat"),
}

HC_DATE_KEYS = ("date", "day", "start_time", "startTime", "timestamp",
                "end_time", "endTime", "created_at", "logged_at",
                "consumed_at")


def _parse_iso(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.datetime.fromisoformat(
            value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _hc_date(record, where):
    """Return the local date a Health Connect nutrition record belongs to.

    The payload's start_time is formatted in the bridge app's chosen timezone.
    With the default "Local time" setting the date prefix is already the local
    day. When the bridge is set to UTC, the record metadata still carries the
    original zone offset, so apply it before taking the date.
    """
    for key in HC_DATE_KEYS:
        raw = record.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            value = float(raw)
            if value > 1e11:
                value /= 1000.0
            try:
                return datetime.datetime.fromtimestamp(
                    value, datetime.timezone.utc).date().isoformat()
            except (OverflowError, OSError, ValueError):
                continue
        text = str(raw).strip()
        if len(text) >= 10:
            try:
                return datetime.date.fromisoformat(text[:10]).isoformat()
            except ValueError:
                pass
        try:
            return _normalize_date(text)
        except NutritionError:
            continue
    raise NutritionError("nutrition record has no usable date (%s)" % where)


def _hc_values(record, where):
    """Extract the four daily fields from a Health Connect record."""
    values = {}
    nutrients = record.get("nutrients")
    if not isinstance(nutrients, dict):
        nutrients = {}
    for field in NUMERIC:
        raw = None
        for key in HC_ALIASES[field]:
            if key in record and record[key] not in (None, ""):
                raw = record[key]
                break
            if key in nutrients and nutrients[key] not in (None, ""):
                raw = nutrients[key]
                break
        values[field] = _fmt(_number(raw, field, where))
    return values


def _interval_seconds(record):
    start = _parse_iso(record.get("start_time"))
    end = _parse_iso(record.get("end_time"))
    if start is None or end is None:
        return None
    try:
        return (end - start).total_seconds()
    except TypeError:
        return None


def _synthetic_id(date, record, values):
    """Stable id for a raw record that arrived without Health Connect metadata.

    Health Connect normally supplies metadata.id, but an older bridge build or
    a hand-written payload may not. Hashing the visible fields still lets an
    identical record be retried without double-counting.
    """
    blob = json.dumps({
        "date": date,
        "start": record.get("start_time"),
        "end": record.get("end_time"),
        "name": record.get("name"),
        "values": values,
    }, sort_keys=True, default=str)
    return "synthetic-" + hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _maybe_date(record):
    try:
        return _hc_date(record, "backup entry")
    except NutritionError:
        return None


def _has_nutrition(record):
    keys = {str(key).lower() for key in record}
    names = {alias for aliases in HC_ALIASES.values() for alias in aliases}
    if keys & names:
        return True
    nutrients = record.get("nutrients")
    if isinstance(nutrients, dict):
        nkeys = {str(key).lower() for key in nutrients}
        return bool(nkeys & names)
    return False


def _walk_json(node, out, depth=0, inherited_date=None):
    """Find nutrition-bearing objects in an unknown CalTrak backup shape.

    The backup format is private to the app, so instead of pinning one schema
    this walks the document and treats a dict with a date plus calories or
    macros as one entry. A date on a parent is inherited by a nested food item.
    Walking stops at the first nutrition-bearing dict so a meal total and its
    child items are never counted twice.
    """
    if depth > 16:
        return
    if isinstance(node, list):
        for item in node:
            _walk_json(item, out, depth + 1, inherited_date)
        return
    if not isinstance(node, dict):
        return
    date = _maybe_date(node) or inherited_date
    if _has_nutrition(node):
        if date:
            out.append((date, _hc_values(node, "backup entry")))
        return
    for value in node.values():
        _walk_json(value, out, depth + 1, date)


def parse_caltrak_json(text):
    """Parse a CalTrak JSON backup (or an already-normalized days payload).

    CalTrak does not publish its backup schema. The tolerant walker accepts the
    documented daily shape and the common nested food-log shapes. Raises
    NutritionError when no dated nutrition entries can be found.
    """
    if isinstance(text, str):
        if not text.strip():
            raise NutritionError("JSON is empty")
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise NutritionError("invalid JSON: %s" % exc)
    else:
        payload = text
    if isinstance(payload, dict) and isinstance(payload.get("days"), list):
        return normalize_days(payload["days"])
    found = []
    _walk_json(payload, found)
    if not found:
        raise NutritionError("no nutrition entries found in the JSON backup")
    merged = {}
    for date, values in found:
        record = merged.setdefault(date, {f: 0.0 for f in NUMERIC})
        for field in NUMERIC:
            record[field] += values[field]
    return [dict(date=d, **{f: _fmt(merged[d][f]) for f in NUMERIC})
            for d in sorted(merged)]


def parse_export(text):
    """Parse either a CalTrak CSV export or a JSON backup."""
    if not isinstance(text, str) or not text.strip():
        raise NutritionError("export is empty")
    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped[:1] in ("{", "["):
        return parse_caltrak_json(stripped)
    return parse_caltrak_csv(stripped)


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


def _state_path(path=None):
    """Sidecar that remembers raw Health Connect records between syncs.

    The bridge app normally sends only records new since its last successful
    sync. Keeping the records (keyed by Health Connect id) lets the server
    recompute a correct daily total instead of replacing a day with only the
    newest entry. The file lives next to the local CSV, never in the repo.
    """
    path = path or NUTRITION_FILE
    return os.path.splitext(os.path.abspath(path))[0] + ".records.json"


def _read_state(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return {"records": {}, "daily": {}, "dates": []}
    if not isinstance(state, dict):
        return {"records": {}, "daily": {}, "dates": []}
    records = state.get("records")
    daily = state.get("daily")
    dates = state.get("dates")
    return {
        "records": records if isinstance(records, dict) else {},
        "daily": daily if isinstance(daily, dict) else {},
        "dates": dates if isinstance(dates, list) else [],
        "last_received": state.get("last_received"),
        "last_accepted": state.get("last_accepted"),
    }


def _write_json(payload, path):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".nutrition-", suffix=".json",
                               dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _compose_days(records, daily):
    totals = {}
    for record in records.values():
        date = record.get("date")
        if not date:
            continue
        bucket = totals.setdefault(date, {f: 0.0 for f in NUMERIC})
        for field in NUMERIC:
            bucket[field] += float(record.get(field) or 0)
    for date, record in daily.items():
        totals[date] = {f: float(record.get(f) or 0) for f in NUMERIC}
    return [dict(date=d, **{f: _fmt(totals[d][f]) for f in NUMERIC})
            for d in sorted(totals)]


def ingest_health_connect(payload, path=None):
    """Merge an HC Webhook JSON payload into the local daily log.

    Accepts both raw NutritionRecords (one per food entry, with a Health
    Connect id) and merged Daily records (one total per day, no id). Raw
    records are stored by id so an incremental sync can add one entry without
    losing the rest of that day. Deleted records are applied too.
    """
    path = path or NUTRITION_FILE
    if not isinstance(payload, dict):
        raise NutritionError("Health Connect payload must be an object")
    records = payload.get("nutrition", [])
    if records is None:
        records = []
    if not isinstance(records, list):
        raise NutritionError("'nutrition' must be a list")
    deleted = payload.get("deleted", [])
    if not isinstance(deleted, list):
        deleted = []

    state_path = _state_path(path)
    state = _read_state(state_path)
    raw = state["records"]
    daily = state["daily"]

    for item in deleted:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).lower() != "nutrition":
            continue
        record_id = item.get("id")
        if record_id:
            raw.pop(str(record_id), None)

    accepted = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise NutritionError(
                "nutrition record %d must be an object" % index)
        where = "nutrition record %d" % index
        date = _hc_date(record, where)
        values = _hc_values(record, where)
        metadata = record.get("metadata")
        record_id = None
        if isinstance(metadata, dict):
            record_id = metadata.get("id")
        if not record_id:
            record_id = record.get("id") or record.get("client_record_id")
        if record_id:
            raw[str(record_id)] = dict(date=date, **values)
            daily.pop(date, None)
        elif (_interval_seconds(record) or 0) >= 20 * 3600:
            # A merged Daily record is the authoritative total for that day.
            daily[date] = values
            raw = {key: value for key, value in raw.items()
                   if value.get("date") != date}
        else:
            raw[_synthetic_id(date, record, values)] = dict(
                date=date, **values)
            daily.pop(date, None)
        accepted += 1

    health_days = _compose_days(raw, daily)
    existing = {row["date"]: row for row in read_days(path)}
    # Dates previously managed by Health Connect are replaced wholesale, so a
    # deleted record can remove a day. Manually imported dates are preserved.
    for date in state["dates"]:
        existing.pop(date, None)
    existing.update({row["date"]: row for row in health_days})
    _write_days(list(existing.values()), path)

    received = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _write_json({
        "records": raw,
        "daily": daily,
        "dates": [row["date"] for row in health_days],
        "last_received": received,
        "last_accepted": accepted,
    }, state_path)
    return {
        "accepted": accepted,
        "upserted": len(health_days),
        "total_days": len(existing),
        "source": "health-connect",
        "last_received": received,
    }


def hook_token_path(path=None):
    """The dedicated secret used by the phone webhook.

    It is separate from the dashboard login token so it can be revoked on its
    own and never grants access to any other route.
    """
    path = path or NUTRITION_FILE
    return os.path.splitext(os.path.abspath(path))[0] + ".hook-token"


def load_or_make_hook_token(path=None):
    token_path = hook_token_path(path)
    try:
        with open(token_path, "r", encoding="utf-8") as fh:
            token = fh.read().strip()
        if token:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(24)
    try:
        directory = os.path.dirname(token_path)
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".hook-", suffix=".token",
                                   dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(token)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, token_path)
    except OSError:
        pass
    return token


def hook_info(path=None):
    """The authenticated envelope the dashboard's setup card reads."""
    state = _read_state(_state_path(path))
    return {
        "path": "/api/nutrition/hook",
        "header": "X-Nutrition-Token",
        "token": load_or_make_hook_token(path),
        "last_received": state.get("last_received"),
        "last_accepted": state.get("last_accepted"),
        "managed_days": len(state.get("dates", [])),
        "mode": "health-connect",
    }


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
