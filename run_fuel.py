"""In-run fluid, fuel and electrolyte events, and the fade they explain.

Why this exists
---------------
The dashboard has always had two kinds of data that look similar and are not:

* the canonical corpus in ``trainloop.db``, which says what the watch recorded
  (distance, pace, heart rate, laps), and
* the athlete's own journal, which says what the athlete *did* (drank, ate,
  took electrolytes, cramped, faded).

The journal used to live only inside ``dashboard/index.html``, which is
gitignored because it also holds coordinates and private notes. When Aurora
became the dashboard at ``/``, that journal stopped being rendered anywhere. The
hydration and fueling entries were never deleted; they simply had no route, no
store and no view. This module gives them all three.

What is stored
--------------
One entry per run, keyed by ``activity_id`` when it is known and by local date
otherwise. An entry holds a list of events (mile marker, kind, free text, and
optional measured amounts) plus the athlete's own note for that run. Every
numeric field is optional on purpose: "a gel at mile 5" is a real entry even
when nobody wrote down 100 kcal, and storing 0 there would be a lie.

The file is local-only (``paths.data_dir()/run_fuel.json``), listed in
``paths.DATA_FILES``, bundled by ``backup_data.py`` and never committed. It is
merged into ``/api/activities`` for display and it is not fed to ``loadcalc`` or
``recommend``: intake is context for a human reading the fade, not a training
load.

What "fade" means here
----------------------
``fade()`` compares the mean pace of the first half of the lap splits with the
mean pace of the second half. A positive value is slowing down. It is a
descriptive statistic, not a diagnosis: heat, hills, distance and fueling all
move it. The point is to put the intake next to it so the athlete can see
whether the runs that fell apart are also the runs with no fluid or no carbs.
"""

import datetime
import json
import os
import re
import tempfile

import paths

STORE_FILE = (os.environ.get("GARMIN_RUN_FUEL_FILE")
              or os.path.join(paths.data_dir(), "run_fuel.json"))

# A fuel entry is small. These caps stop a stray upload from growing the store
# without bound or from being used as free-form storage.
MAX_BODY = 256 * 1024
MAX_EVENTS = 40
MAX_TEXT = 120
MAX_NOTE = 4000
MAX_MILE = 200.0

KINDS = ("water", "electrolyte", "fuel", "other")

# field -> (low, high). None means "not recorded", never zero.
NUMERIC = {
    "oz": (0.0, 400.0),
    "kcal": (0.0, 5000.0),
    "carbs_g": (0.0, 500.0),
    "sodium_mg": (0.0, 10000.0),
}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_START = re.compile(r"^\s*(start|begin|pre[- ]?run|0)\b", re.I)
_FINISH = re.compile(r"^\s*(finish|end|post[- ]?run)\b", re.I)
_MID = re.compile(r"\b(mid|middle|halfway|half-way)\b", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_OZ = re.compile(r"(\d+(?:\.\d+)?)\s*(?:oz|ounces?)\b", re.I)

# The words the journal uses. They are deliberately broad: this only proposes
# events in the editor, and a proposal the athlete does not save is not data.
# ``dehydrat*`` and ``bonk`` are included because a run that fell apart from
# dehydration still belongs in the fuel journal even when it records no intake.
_INTAKE_WORDS = re.compile(
    r"\b(water|fluid|fluids|camelback|vest|hydration|dehydrat\w*|bonk|"
    r"drink|drank|electrolytes?|salt|saltstick|nuun|lmnt|lyte|gatorade|coke|"
    r"gels?|gu\b|chews?|snacks?|banana|bars?\b|pb&j|fuel|fueled|fueling|ate|eat)\b",
    re.I)

_SUGGEST_GROUPS = (
    (re.compile(r"\b(water|fluid|fluids|camelback|vest|hydration|drink|drank)\b",
                re.I), "water"),
    (re.compile(r"\b(electrolytes?|salt|saltstick|nuun|lmnt|lyte|gatorade|coke)\b",
                re.I), "electrolyte"),
    (re.compile(r"\b(gels?|gu\b|chews?|snacks?|banana|bars?\b|pb&j|fueled?|"
                r"fueling|ate|eat)\b", re.I), "fuel"),
)

_NEGATION = re.compile(r"\b(no|none|without|zero|0)\s*$", re.I)

# A deliberate zero is different from prose: "hydration 0 oz" and
# "electrolytes none" are observations, while "no water, vest only" is a
# narrative the athlete left for review. Only a value written after the noun
# is promoted into a measured event by the importer. The more general phrase
# "no water" is still offered as a suggestion in the editor, but never stored
# without the athlete saving it.
_EXPLICIT_ZEROS = (
    (re.compile(r"\b(?:hydration|water|fluids?|drink)\s*"
                r"(?::|=|is)?\s*(?:0\s*(?:oz|ounces?)\b|none\b|zero\b)",
                re.I), "water", "oz", "0 oz"),
    (re.compile(r"\belectrolytes?\s*(?::|=|is)?\s*(?:none\b|zero\b|0(?!\.\d)\b)",
                re.I), "electrolyte", "sodium_mg", "none"),
)

# The athlete's own calibration (also encoded in the classic page): a gel or a
# GU is 100 kcal / 21 g carbs, and a full vest is 1.5 L. These only annotate
# editor suggestions; nothing is written to the store until the athlete saves.
_GEL_KCAL = 100.0
_GEL_CARBS_G = 21.0
_VEST_OZ = round(1.5 * 33.814, 1)  # 50.7 US fl oz
_GEL_WORD = re.compile(r"\b(gels?|gu)\b", re.I)
_GENERIC_ELECTROLYTE = re.compile(r"\belectrolytes?\b", re.I)
_VEST_WORD = re.compile(r"\b(vest|camelback)\b", re.I)
_VESSEL_NEGATION = re.compile(
    r"\b(no\s+water|water\s+(?:ran\s+out|is\s+gone)|0\s*oz|none|without|"
    r"under[-\s]?hydrated)\b", re.I)
_TRAILING_ZERO = re.compile(
    r"\s*(?::|=|is)?\s*(?:none\b|zero\b|0(?!\.\d)\b)", re.I)


class FuelError(ValueError):
    """A fuel payload that cannot be stored honestly."""


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _text(value, label, limit=MAX_TEXT):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        raise FuelError("%s must be text" % label)
    text = str(value).strip()
    if len(text) > limit:
        raise FuelError("%s is longer than %d characters" % (label, limit))
    return text


def parse_position(value):
    """Return ``(mile, at)`` from a journal marker.

    Accepts what the journal actually contains: ``5``, ``"5"``, ``"Mile 5"``,
    ``"between 8 and 9"``, ``"start"``, ``"finish"``, ``"mid-run"``, ``"None"``
    and blanks. ``at`` is only set when there is no numeric mile, so a caller
    can tell "at the start" from "at mile 0".
    """
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        raise FuelError("mile must be a number or a marker")
    if isinstance(value, (int, float)):
        mile = float(value)
        if not (0 <= mile <= MAX_MILE):
            raise FuelError("mile must be between 0 and %g" % MAX_MILE)
        return mile, None

    text = str(value).strip()
    if not text:
        return None, None
    if _START.match(text):
        return 0.0, "start"
    if _FINISH.match(text):
        return None, "finish"
    if _MID.search(text):
        return None, "mid"
    match = _NUMBER.search(text)
    if match:
        mile = float(match.group(0))
        if mile > MAX_MILE:
            raise FuelError("mile must be between 0 and %g" % MAX_MILE)
        return mile, None
    return None, None


def _number(value, field):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise FuelError("%s must be a number" % field)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise FuelError("%s must be a number" % field)
    if number != number or number in (float("inf"), float("-inf")):
        raise FuelError("%s must be finite" % field)
    low, high = NUMERIC[field]
    if not (low <= number <= high):
        raise FuelError("%s must be between %g and %g" % (field, low, high))
    return round(number, 1)


def _oz_from_text(text):
    """Only an explicit ounce figure is trusted; millilitres stay prose."""
    match = _OZ.search(text or "")
    if not match:
        return None
    try:
        return _number(match.group(1), "oz")
    except FuelError:
        return None


def explicit_zero_events(text):
    """Events for intake the athlete explicitly recorded as zero.

    Only a value written after the noun ("0 oz", "none", "zero") becomes
    measured data; a narrative "no water" stays prose for the athlete to
    review. The classic journal kept some of these only in ``note2`` (the
    recovery run whose "hydration 0 oz · electrolytes none" never reached
    ``fnotes``), so the importer uses this to stop that deliberate zero being
    lost. One event per kind: a second explicit zero adds no information.
    """
    text = str(text or "")
    out = []
    seen = set()
    for pattern, kind, field, what in _EXPLICIT_ZEROS:
        if kind in seen:
            continue
        if not pattern.search(text):
            continue
        seen.add(kind)
        event = {"mile": None, "at": None, "kind": kind, "what": what,
                 "oz": None, "kcal": None, "carbs_g": None,
                 "sodium_mg": None}
        event[field] = 0.0
        out.append(event)
    return out


def normalize_event(raw):
    """Validate one event and return the record to store.

    ``kind`` is required because it decides which question the event answers:
    fluid volume, sodium, or carbohydrate. The journal's ``mi``/``mile`` key is
    accepted so the recovered entries need no rewriting.
    """
    if not isinstance(raw, dict):
        raise FuelError("each event must be a JSON object")

    kind = str(raw.get("kind") or raw.get("type") or "").strip().lower()
    if kind not in KINDS:
        raise FuelError("kind must be one of %s" % ", ".join(KINDS))

    mile, at = parse_position(
        raw.get("mile", raw.get("mi", raw.get("at"))))
    what = _text(raw.get("what", raw.get("label")), "what")
    event = {
        "mile": mile,
        "at": at,
        "kind": kind,
        "what": what,
    }
    for field in NUMERIC:
        event[field] = _number(raw.get(field), field)

    # The classic page stored "0 oz" as text. Promote it to the numeric field so
    # a deliberate zero is visible in the totals instead of looking unrecorded.
    if event["oz"] is None and kind == "water":
        event["oz"] = _oz_from_text(what)
    return event


def normalize_entry(payload):
    """Validate one run's fuel entry.

    Identity is the local date plus, when known, the canonical ``activity_id``.
    A date is required so an entry can still be found after a re-import that
    changes the device's activity id.
    """
    if not isinstance(payload, dict):
        raise FuelError("payload must be a JSON object")

    date = str(payload.get("date") or "").strip()
    if not _DATE.match(date):
        raise FuelError("date must be YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise FuelError("date is not a real calendar day")

    activity_id = payload.get("activity_id")
    if activity_id in ("", None):
        activity_id = None
    elif not isinstance(activity_id, str) or len(activity_id) > 200:
        raise FuelError("activity_id must be a short string")

    events = payload.get("events")
    if events is None:
        events = []
    if not isinstance(events, list):
        raise FuelError("events must be a list")
    if len(events) > MAX_EVENTS:
        raise FuelError("at most %d events per run" % MAX_EVENTS)
    events = [normalize_event(event) for event in events]

    note = _text(payload.get("note"), "note", MAX_NOTE)

    source = str(payload.get("source") or "manual").strip().lower()
    if source not in ("manual", "journal", "journal-note"):
        source = "manual"

    return {
        "date": date,
        "activity_id": activity_id,
        "events": events,
        "note": note,
        "source": source,
        # A note that was recovered from the journal but never turned into
        # events is visible and editable, and it is labelled as unconfirmed.
        "needs_review": bool(payload.get("needs_review", False)),
        "updated_utc": _now_utc(),
    }


def _same_run(left, right):
    if left.get("activity_id") and right.get("activity_id"):
        return left["activity_id"] == right["activity_id"]
    return left.get("date") == right.get("date")


def load(path=None):
    """Stored entries, oldest first. A missing or corrupt file reads as []."""
    path = path or STORE_FILE
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("runs") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if isinstance(row, dict) and _DATE.match(str(row.get("date") or "")):
            out.append(row)
    out.sort(key=lambda r: (str(r.get("date")), str(r.get("activity_id") or "")))
    return out


def save(rows, path=None):
    """Write the store atomically so a crash cannot leave half a JSON file."""
    path = path or STORE_FILE
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    payload = {"version": 1, "runs": list(rows)}
    fd, tmp = tempfile.mkstemp(prefix=".run-fuel-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return path


def upsert(payload, path=None):
    """Validate, store and return one entry, replacing the same run."""
    entry = normalize_entry(payload)
    rows = load(path)
    for index, existing in enumerate(rows):
        if _same_run(existing, entry):
            # A later sync can supply the activity id a journal import did not
            # have. Keep it rather than dropping back to the date-only key.
            if not entry.get("activity_id") and existing.get("activity_id"):
                entry["activity_id"] = existing["activity_id"]
            rows[index] = entry
            break
    else:
        rows.append(entry)
    rows.sort(key=lambda r: (str(r.get("date")), str(r.get("activity_id") or "")))
    save(rows, path)
    return entry


def delete(date, activity_id=None, path=None):
    """Remove one entry. Returns the number removed (0 or 1)."""
    rows = load(path)
    kept = []
    removed = 0
    for row in rows:
        if row.get("date") != date:
            kept.append(row)
            continue
        if activity_id and row.get("activity_id") and \
                row["activity_id"] != activity_id:
            kept.append(row)
            continue
        removed += 1
    if removed:
        save(kept, path)
    return removed


def fade(splits):
    """First-half versus second-half pace, in seconds per mile.

    ``splits`` is the per-mile list ``/api/activities`` already carries. Fewer
    than four usable splits is not a fade measurement, so it returns None
    rather than a two-point guess.
    """
    values = []
    for value in splits or []:
        if isinstance(value, bool):
            continue
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            continue
        if seconds > 0:
            values.append(seconds)
    if len(values) < 4:
        return None
    half = len(values) // 2
    first = sum(values[:half]) / half
    second = sum(values[half:]) / (len(values) - half)
    if first <= 0:
        return None
    return {
        "splits_used": len(values),
        "first_half_s_per_mi": round(first),
        "second_half_s_per_mi": round(second),
        "fade_s_per_mi": round(second - first),
        "fade_pct": round(100.0 * (second / first - 1.0), 1),
    }


def _total(events, field):
    values = [event[field] for event in events if event.get(field) is not None]
    if not values:
        return None
    return round(sum(values), 1)


def _rate(total, hours):
    if total is None or not hours or hours <= 0:
        return None
    return round(total / hours, 1)


def summary(entry, row=None):
    """Totals, hourly rates and fade for one entry.

    ``row`` is the matching ``/api/activities`` row, used only for the duration
    (rates) and the splits (fade). Passing no row still returns the totals, so a
    run whose device data has not imported yet is not hidden.
    """
    events = entry.get("events") or []
    totals = {field: _total(events, field) for field in NUMERIC}

    seconds = None
    if isinstance(row, dict):
        try:
            seconds = float(row.get("moving_time_s") or 0)
        except (TypeError, ValueError):
            seconds = None
    hours = (seconds / 3600.0) if seconds and seconds > 0 else None

    return {
        "events": len(events),
        # The editor needs the events themselves, not just how many there are.
        "items": events,
        "totals": totals,
        "rates": {field + "_per_h": _rate(totals[field], hours)
                  for field in NUMERIC},
        "duration_h": round(hours, 2) if hours else None,
        "fade": fade(row.get("splits")) if isinstance(row, dict) else None,
        "note": entry.get("note") or "",
        "source": entry.get("source") or "manual",
        "needs_review": bool(entry.get("needs_review")),
        "updated_utc": entry.get("updated_utc"),
    }


def _row_date(row):
    return str(row.get("start_local") or row.get("start_utc") or "")[:10]


def attach(payload, path=None):
    """Add each run's fuel summary to an ``/api/activities`` payload.

    Matching is by ``activity_id`` first and local date second, so an entry
    recovered from the journal (which has no device id) still finds its run,
    and an entry logged against a typed quick-log run keeps working after the
    real activity imports on the same date.

    Idempotent: re-attaching replaces the ``fuel`` key instead of stacking one.
    """
    if not isinstance(payload, dict):
        return payload
    activities = payload.get("activities")
    if not isinstance(activities, list):
        return payload

    entries = load(path)
    by_activity = {}
    by_date = {}
    for entry in entries:
        if entry.get("activity_id"):
            by_activity[entry["activity_id"]] = entry
        by_date[entry["date"]] = entry

    attached = 0
    with_fade = 0
    for row in activities:
        if not isinstance(row, dict):
            continue
        entry = by_activity.get(row.get("activity_id"))
        if entry is None:
            entry = by_date.get(_row_date(row))
        if entry is None:
            continue
        summary_row = summary(entry, row)
        row["fuel"] = summary_row
        attached += 1
        if summary_row["fade"] is not None:
            with_fade += 1

    payload["fuel_count"] = attached
    payload["fuel_with_fade"] = with_fade
    return payload


def suggest_events(note):
    """Propose events from a journal sentence, for the editor only.

    This is the same heuristic the classic page used at render time. It is not
    stored until the athlete saves it, because prose like "water ran out at mile
    14" is a depletion, not an intake. Negated phrases ("no electrolytes",
    "0 oz") become an explicit zero, which is the useful signal for fade.
    """
    text = str(note or "")
    if not text.strip():
        return []
    out = []
    seen = set()
    for pattern, kind in _SUGGEST_GROUPS:
        for match in pattern.finditer(text):
            index = match.start()
            window = text[max(0, index - 100):min(len(text), index + 70)]
            mile, at = parse_position(_mile_from_window(window))
            if mile is None and at is None:
                at = _at_from_window(window)
            key = (kind, mile, at)
            if key in seen:
                continue
            seen.add(key)

            before = text[max(0, index - 20):index]
            after = text[match.end():min(len(text), match.end() + 60)]
            # "no water" negates before the noun; "electrolytes none" and
            # "hydration 0 oz" negate after it. Both are explicit zeros.
            negated = (bool(_NEGATION.search(before))
                       or bool(_TRAILING_ZERO.match(after)))
            event = {"mile": mile, "at": at, "kind": kind,
                     "what": "none" if negated else match.group(0),
                     "oz": None, "kcal": None, "carbs_g": None,
                     "sodium_mg": None}
            if negated:
                if kind == "water":
                    event["oz"] = 0.0
                elif kind == "electrolyte":
                    event["sodium_mg"] = 0.0
                elif kind == "fuel":
                    event["kcal"] = 0.0
            elif kind == "water":
                if _VEST_WORD.search(window):
                    if not _VESSEL_NEGATION.search(window):
                        # The athlete's calibration: a full vest is 1.5 L.
                        event["oz"] = _VEST_OZ
                        event["what"] = "Hydration vest (1.5 L)"
                else:
                    event["oz"] = _oz_from_text(window)
            elif kind == "electrolyte":
                # The athlete's calibration: whenever they wrote
                # "electrolytes" they meant LMNT.
                if _GENERIC_ELECTROLYTE.search(match.group(0)):
                    event["what"] = "LMNT"
            elif kind == "fuel":
                # The athlete's calibration: a gel or GU is 100 kcal / 21 g
                # carbohydrates. Unmeasured snacks and bars stay unmeasured.
                if _GEL_WORD.search(match.group(0)):
                    event["kcal"] = _GEL_KCAL
                    event["carbs_g"] = _GEL_CARBS_G
            out.append(event)
            if len(out) >= MAX_EVENTS:
                return out
    out.sort(key=lambda e: (e["mile"] is None, e["mile"] or 0.0,
                            e["at"] or "", e["kind"]))
    return out


def _mile_from_window(window):
    patterns = (
        r"(?:at|by|around|about|after|before|every|between|~)\s*"
        r"(?:mile|mi|miles?|the)?\s*(\d+(?:\.\d+)?)",
        r"\bmile\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*miles?\s+(?:in|into)",
    )
    for pattern in patterns:
        match = re.search(pattern, window, re.I)
        if match:
            return match.group(1)
    return None


def _at_from_window(window):
    head = window[:60]
    if re.search(r"finish|post-?run|end\b|last mile", head, re.I):
        return "finish"
    if re.search(r"start|begin|warm.?up|pre-?run|before|early", head, re.I):
        return "start"
    if re.search(r"\bmid|middle|halfway", window, re.I):
        return "mid"
    return None


def payload(path=None):
    """The editor's read model: every entry, with suggestions when empty."""
    runs = load(path)
    out = []
    for entry in runs:
        item = dict(entry)
        item["suggested"] = (suggest_events(entry.get("note"))
                             if not entry.get("events") else [])
        out.append(item)
    return {"version": 1, "count": len(out), "runs": out}


def _journal_runs(html_text):
    """The ``baseRuns`` array embedded in the classic dashboard."""
    marker = "const baseRuns"
    if marker not in html_text:
        raise FuelError("this HTML has no baseRuns array")
    start = html_text.index("[", html_text.index(marker))
    decoder = json.JSONDecoder()
    runs, _end = decoder.raw_decode(html_text[start:])
    if not isinstance(runs, list):
        raise FuelError("baseRuns is not a list")
    return runs


# The journal is gitignored and absent on a clean checkout. The cache is keyed
# by mtime and size so an edit to the classic page is picked up without reread-
# ing a ~1 MB file on every /api/activities request.
_JOURNAL_CACHE = {"key": None, "value": {}}


def journal_notes(path=None):
    """Date -> journal note and recorded ``tempF`` from the local classic page.

    Read-only context for fade analysis. A missing or malformed journal yields
    an empty map rather than an error, so clean checkouts and the cloud VM work
    without a file that is deliberately never published.
    """
    html_path = path or os.path.join(paths.repo_dir(), "dashboard", "index.html")
    try:
        stat = os.stat(html_path)
        key = (html_path, stat.st_mtime_ns, stat.st_size)
    except OSError:
        return {}
    if _JOURNAL_CACHE["key"] == key:
        return {date: dict(value) for date, value in _JOURNAL_CACHE["value"].items()}
    try:
        with open(html_path, "r", encoding="utf-8", errors="replace") as fh:
            runs = _journal_runs(fh.read())
    except (OSError, FuelError, ValueError):
        return {}

    out = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        date = str(run.get("date") or "")[:10]
        if not _DATE.match(date):
            continue
        temp = run.get("tempF")
        if isinstance(temp, bool) or not isinstance(temp, (int, float)):
            temp = None
        out[date] = {
            "note": (str(run.get("note") or "") + " "
                     + str(run.get("note2") or "")).strip(),
            "temp_f": temp,
        }
    _JOURNAL_CACHE["key"] = key
    _JOURNAL_CACHE["value"] = out
    return {date: dict(value) for date, value in out.items()}


def import_journal(html_text, path=None, overwrite=False):
    """Recover the journal's fuel entries into the store.

    Structured ``fnotes`` become events. A narrative note that mentions intake
    but has no structured events is stored as a note-only entry flagged
    ``needs_review``; it is not turned into invented events. ``note2`` is
    carried into the stored note as well: the classic page used it for facts
    that never reached ``fnotes``, including deliberate zeros. Existing entries
    that already have events are left alone unless ``overwrite`` is set, so the
    import can be re-run safely after the athlete has edited something.
    """
    runs = _journal_runs(html_text)
    existing = {entry["date"]: entry for entry in load(path)}
    result = {"scanned": len(runs), "seeded": 0, "with_events": 0,
              "notes_only": 0, "skipped": 0}

    for run in runs:
        if not isinstance(run, dict):
            continue
        date = str(run.get("date") or "").strip()
        if not _DATE.match(date):
            continue
        note = str(run.get("note") or "").strip()
        note2 = str(run.get("note2") or "").strip()
        # The classic page kept some intake facts only in note2. Joining it to
        # the primary note keeps the whole observation visible in the editor.
        combined = note
        if note2 and note2 not in combined:
            combined = (combined + " · " + note2).strip(" ·")
        events = []
        for raw in run.get("fnotes") or []:
            try:
                events.append(normalize_event(raw))
            except FuelError:
                continue
        zeros = explicit_zero_events(combined)
        if zeros:
            # A blank fnotes placeholder carries no information. Replace a
            # same-kind blank with the deliberate zero instead of keeping both.
            zero_kinds = {event["kind"] for event in zeros}
            events = [event for event in events
                      if event["kind"] not in zero_kinds
                      or any(event[field] is not None for field in NUMERIC)]
            events.extend(zeros)

        if not events and not _INTAKE_WORDS.search(combined):
            continue

        prior = existing.get(date)
        if prior and prior.get("events") and not overwrite:
            # A prior entry made only of blank fnotes placeholders holds no
            # measured data. Filling it with an explicit zero is an upgrade,
            # not an overwrite of something the athlete saved by hand.
            placeholder = all(
                all(event.get(field) is None for field in NUMERIC)
                for event in prior["events"])
            if not (events and placeholder):
                result["skipped"] += 1
                continue

        upsert({
            "date": date,
            "activity_id": (prior or {}).get("activity_id"),
            "events": events,
            "note": combined,
            "source": "journal" if events else "journal-note",
            "needs_review": not events,
        }, path)
        result["seeded"] += 1
        if events:
            result["with_events"] += 1
        else:
            result["notes_only"] += 1

    return result


def main(argv=None):
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description="In-run fuel and hydration events for the dashboard.")
    ap.add_argument("--file", help="store path (default: data directory)")
    sub = ap.add_subparsers(dest="command")

    imp = sub.add_parser("import-journal",
                         help="seed from the classic dashboard's baseRuns")
    imp.add_argument("html", nargs="?",
                     default=os.path.join(paths.repo_dir(), "dashboard",
                                          "index.html"))
    imp.add_argument("--overwrite", action="store_true",
                     help="replace entries that already have events")

    sub.add_parser("show", help="print the stored entries")

    args = ap.parse_args(argv)
    path = args.file

    if args.command == "import-journal":
        try:
            with open(args.html, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print("could not read %s: %s" % (args.html, exc), file=sys.stderr)
            return 2
        try:
            result = import_journal(text, path, overwrite=args.overwrite)
        except FuelError as exc:
            print("import failed: %s" % exc, file=sys.stderr)
            return 1
        print("journal scanned : %d" % result["scanned"])
        print("entries seeded  : %d" % result["seeded"])
        print("  with events   : %d" % result["with_events"])
        print("  note only     : %d" % result["notes_only"])
        print("  skipped       : %d" % result["skipped"])
        return 0

    if args.command == "show":
        for entry in load(path):
            print("%s  %-12s %2d event(s)  %s" % (
                entry.get("date"), entry.get("activity_id") or "date-key",
                len(entry.get("events") or []), entry.get("note") or ""))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
