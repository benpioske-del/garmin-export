"""Import the athlete's typed classic journal into the Aurora fuel store.

The pre-Aurora page kept free-text post-run notes in browser localStorage. They
were never copied into ``run_fuel.json``, so Aurora showed "not recorded" for
runs the athlete had actually typed into. This module reads only two
localStorage keys from a loopback Edge profile:

* ``season-report-v1:custom-runs`` (maps an internal sequence number to a date)
* ``season-report-v1:run-overrides`` (holds the typed note and fuel rows)

Nothing else in the browser database is decoded into output. The parser is
read-only, and importing is a separate ``--apply`` step after a dry run.
``cramjam`` is needed only here, for LevelDB Snappy blocks; the live server does
not import this module.
"""

import argparse
import json
import os
import re
import struct

import run_fuel

ALLOWED_KEYS = frozenset((
    "season-report-v1:custom-runs",
    "season-report-v1:run-overrides",
))

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEPARATORS = ("\ufffd", "\u00b7")
_SYSTEM_PREFIX = re.compile(
    r"^Imported from Garmin CSV\s*(?:[\ufffd\u00b7]\s*"
    r"[+-]?\d+ft gain,\s*[+-]?\d+ft loss\s*(?:[\ufffd\u00b7]\s*)?)?",
    re.I)
_ZERO_OZ = re.compile(r"^0\s*(?:oz|ounces?)\.?$", re.I)
_LOWER_NONE = re.compile(r"^none\.?$")
_SENSITIVE = re.compile(
    r"ngrok|password|secret|authorization|api[-_ ]?key|cookie|bearer", re.I)


class JournalError(ValueError):
    """A browser journal that cannot be read without guessing."""


def default_ldb():
    """The current Edge profile's Local Storage table, when it is present."""
    override = os.environ.get("EDGE_LOCAL_STORAGE_LDB")
    if override:
        return override
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return ""
    candidate = os.path.join(
        local, "Microsoft", "Edge", "User Data", "Default",
        "Local Storage", "leveldb", "000064.ldb")
    return candidate if os.path.isfile(candidate) else ""


def _varint(data, pos=0):
    result, shift = 0, 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, pos
        shift += 7
        if shift > 70:
            raise JournalError("LevelDB varint is too long")
    raise JournalError("LevelDB varint ended early")


def _block(data, offset, size):
    if size < 0 or offset < 0 or offset + size + 1 >= len(data):
        raise JournalError("LevelDB block points outside the file")
    raw = bytes(data[offset:offset + size])
    kind = data[offset + size]
    if kind == 0:
        return raw
    if kind != 1:
        raise JournalError("unsupported LevelDB block compression")
    try:
        from cramjam import snappy
    except ImportError as exc:
        raise JournalError("cramjam is needed to read this browser table") from exc
    return bytes(snappy.decompress_raw(raw))


def _entries(block):
    """Decode one block's prefix-compressed key/value records."""
    block = bytes(block)
    if len(block) < 4:
        return
    restarts = struct.unpack("<I", block[-4:])[0]
    limit = len(block) - 4 - (4 * restarts)
    if limit < 0:
        limit = len(block)
    pos = 0
    shared_key = b""
    while pos < limit:
        try:
            shared, pos = _varint(block, pos)
            unshared, pos = _varint(block, pos)
            value_len, pos = _varint(block, pos)
            if pos + unshared + value_len > limit:
                return
            key = shared_key[:shared] + block[pos:pos + unshared]
            pos += unshared
            value = block[pos:pos + value_len]
            pos += value_len
        except JournalError:
            return
        shared_key = key
        yield key, value


def _handles(data):
    """Chromium's footer keeps the two handles at the front of its last 48B."""
    if len(data) < 48:
        raise JournalError("browser table is too short")
    footer = data[-48:]
    meta_off, pos = _varint(footer, 0)
    meta_size, pos = _varint(footer, pos)
    index_off, pos = _varint(footer, pos)
    index_size, _ = _varint(footer, pos)
    return (meta_off, meta_size), (index_off, index_size)


def _internal_key(key):
    """Return ``(origin, localStorage_key, sequence, kind)`` for one record."""
    if len(key) < 8:
        return None
    user = bytes(key[:-8])
    tag = struct.unpack("<Q", key[-8:])[0]
    marker = user.find(b"\x01")
    if marker < 0:
        return None
    origin = user.split(b"\x00", 1)[0].decode("utf-8", "replace")
    local_key = user[marker + 1:].decode("utf-8", "replace")
    return origin, local_key, tag >> 8, tag & 0xFF


def _loopback(origin):
    return (origin.startswith("_http://127.0.0.1:")
            or origin.startswith("_http://localhost:"))


def _decode_value(raw):
    raw = bytes(raw)
    if raw[:1] in (b"\x00", b"\x01"):
        raw = raw[1:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # The classic page wrote its separator as a single cp1252 middle dot.
        text = raw.decode("cp1252")
    return json.loads(text)


def _clean_note(note):
    text = str(note or "")
    for mark in _SEPARATORS:
        text = text.replace(mark, "\u00b7")
    return _SYSTEM_PREFIX.sub("", text).strip()


def read(ldb_path=None):
    """Return only the allowlisted athlete entries, newest version first.

    A missing file yields an empty list so a clean machine can dry-run without
    error. An unreadable or malformed file raises ``JournalError`` rather than
    silently producing a partial migration.
    """
    path = ldb_path or default_ldb()
    if not path or not os.path.isfile(path):
        return []
    with open(path, "rb") as fh:
        data = fh.read()
    _meta, index = _handles(data)
    found = {}
    for _index_key, index_value in _entries(_block(data, *index)):
        try:
            offset, pos = _varint(index_value, 0)
            size, _ = _varint(index_value, pos)
        except JournalError:
            continue
        for key, value in _entries(_block(data, offset, size)):
            parsed = _internal_key(key)
            if parsed is None:
                continue
            origin, local_key, seq, kind = parsed
            if local_key not in ALLOWED_KEYS or not _loopback(origin):
                continue
            ident = (origin, local_key, seq)
            if kind == 0:
                found.pop(ident, None)
            elif kind == 1:
                found[ident] = value

    latest = {}
    for (origin, local_key, seq), value in found.items():
        ident = (origin, local_key)
        if ident not in latest or seq > latest[ident][0]:
            latest[ident] = (seq, value)

    by_origin = {}
    for (origin, local_key), (_seq, raw) in latest.items():
        value = _decode_value(raw)
        if local_key.endswith("custom-runs"):
            dates = {}
            if isinstance(value, list):
                for run in value:
                    if isinstance(run, dict) and run.get("seq") is not None:
                        date = str(run.get("date") or "")
                        if _DATE.match(date):
                            dates[str(run["seq"])] = date
            by_origin.setdefault(origin, {})["dates"] = dates
        elif local_key.endswith("run-overrides"):
            by_origin.setdefault(origin, {})["overrides"] = value

    out = []
    for origin in sorted(by_origin):
        dates = by_origin[origin].get("dates") or {}
        overrides = by_origin[origin].get("overrides")
        if not isinstance(overrides, dict):
            continue
        for seq in sorted(overrides, key=lambda x: int(x) if str(x).isdigit() else 0):
            row = overrides[seq]
            if not isinstance(row, dict):
                continue
            date = dates.get(str(seq))
            if not date:
                continue
            note = _clean_note(row.get("note"))
            raw_events = row.get("fnotes") or []
            if not isinstance(raw_events, list):
                raw_events = []
            events = [event for event in raw_events if isinstance(event, dict)]
            if not note and not events:
                continue
            out.append({"origin": origin, "date": date, "note": note,
                        "events": events})
    out.sort(key=lambda item: (item["date"], item["origin"]))
    return out


def _event(raw):
    """Convert one typed fuel row. Returns ``(event, needs_review)``."""
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in run_fuel.KINDS:
        return None, False
    what = str(raw.get("what") or "").strip()
    event = {
        "mile": raw.get("mi", raw.get("mile")),
        "kind": kind,
        "what": what,
        "oz": None,
        "kcal": None,
        "carbs_g": None,
        "sodium_mg": None,
    }
    if kind == "water" and _ZERO_OZ.match(what):
        # A typed "0 oz" is a deliberate observation, not an unrecorded value.
        event["oz"] = 0.0
        return event, False
    if kind == "electrolyte" and _LOWER_NONE.match(what):
        # Lower-case "none" is the athlete's explicit zero. Capital "None" is
        # the word for an unrecorded value and stays unmeasured.
        event["sodium_mg"] = 0.0
        return event, False
    return event, bool(what)


def to_entry(record):
    """Validate one raw journal record as a run_fuel entry."""
    events = []
    needs_review = False
    for raw in record.get("events") or []:
        event, ambiguous = _event(raw)
        if event is None:
            continue
        events.append(event)
        needs_review = needs_review or ambiguous
    # A note with no typed rows is visible for review, never promoted to data.
    if not events:
        needs_review = True
    return run_fuel.normalize_entry({
        "date": record.get("date"),
        "events": events,
        "note": record.get("note") or "",
        "source": "journal" if events else "journal-note",
        "needs_review": needs_review,
    })


def propose(ldb_path=None):
    return [to_entry(record) for record in read(ldb_path)]


def preview(entry):
    """A safe projection for a dry run: no browser origins or unrelated keys."""
    text = entry.get("note") or ""
    if _SENSITIVE.search(text):
        text = "[suppressed]"
    events = []
    for event in entry.get("events") or []:
        what = str(event.get("what") or "")
        if _SENSITIVE.search(what):
            what = "[suppressed]"
        events.append({
            "where": event.get("at") or event.get("mile"),
            "kind": event.get("kind"),
            "what": what,
            "oz": event.get("oz"),
            "sodium_mg": event.get("sodium_mg"),
        })
    return {
        "date": entry.get("date"),
        "source": entry.get("source"),
        "needs_review": entry.get("needs_review"),
        "note": text,
        "events": events,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import allowlisted classic fuel notes from Edge localStorage.")
    parser.add_argument("--ldb", default=default_ldb(),
                        help="Local Storage .ldb to read (default: current Edge profile)")
    parser.add_argument("--store", default=run_fuel.STORE_FILE,
                        help="run_fuel.json to write with --apply")
    parser.add_argument("--apply", action="store_true",
                        help="write the proposed entries; default is a dry run")
    args = parser.parse_args(argv)

    try:
        entries = propose(args.ldb)
    except (JournalError, OSError, ValueError) as exc:
        print("journal import failed: %s" % exc)
        return 1

    if not args.apply:
        print(json.dumps([preview(entry) for entry in entries], indent=2))
        return 0
    for entry in entries:
        run_fuel.upsert(entry, args.store)
    print("Imported %d classic journal entries" % len(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
