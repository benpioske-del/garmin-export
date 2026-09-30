"""Shared vocabulary for how a value came to exist and how far to trust it.

Every other module imports its labels from here rather than writing string
literals. That is the point of this file: the same state must read the same way
in the database, in an API response, in a dashboard card and in a report. A
label invented twice eventually disagrees with itself, and then a reader cannot
tell whether "provisional" means the calculation or the input.

Three axes, because conflating them is the usual mistake:

  VALUE_STATE     where the number came from
  CONFIDENCE      how much to trust it
  CONFIRMATION    whether a human has signed it off

An activity can be DEVICE_DERIVED with CONFIDENCE_LOW and still be
CONFIRMED_BY_ATHLETE, which is a perfectly ordinary combination: the watch
recorded it, the number looks wrong, and the athlete said so.
"""

# --------------------------------------------------------------- value state
# Where the value originated. "Missing" is a real state and is stored as NULL
# rather than 0, because 0 is a measurement and absence is not.
OBSERVED = "observed"              # read directly from the source file
DEVICE_DERIVED = "device_derived"  # computed by the Garmin device itself
ALGORITHMIC = "algorithmic"        # computed here, versioned
ATHLETE_REPORTED = "athlete_reported"
ASSUMED = "assumed"                # filled in because nothing better existed
IMPORTED = "imported"              # carried over from another system
MANUAL = "manual"                  # typed by a human
CLINICIAN_PROVIDED = "clinician_provided"
MISSING = "missing"                # absent. Never coerce this to zero.

VALUE_STATES = (
    OBSERVED, DEVICE_DERIVED, ALGORITHMIC, ATHLETE_REPORTED, ASSUMED,
    IMPORTED, MANUAL, CLINICIAN_PROVIDED, MISSING,
)

# ---------------------------------------------------------------- confidence
HIGH = "high"
MEDIUM = "medium"
LOW = "low"
UNVERIFIED = "unverified"          # no evidence yet either way

CONFIDENCE_LEVELS = (HIGH, MEDIUM, LOW, UNVERIFIED)

# Ordered worst-first, so a caller can take the minimum across contributors
# with min(CONFIDENCE_RANK[c]) and get the weakest link rather than the average.
CONFIDENCE_RANK = {UNVERIFIED: 0, LOW: 1, MEDIUM: 2, HIGH: 3}

# -------------------------------------------------------------- confirmation
# A separate axis from confidence. Confirmed means a human decided, not that a
# number looks right.
CONFIRMATION_NOT_REQUIRED = "not_required"
CONFIRMATION_REQUIRED = "confirmation_required"
CONFIRMED_BY_ATHLETE = "confirmed_by_athlete"
CONFIRMED_BY_REVIEWER = "confirmed_by_reviewer"

CONFIRMATION_STATES = (
    CONFIRMATION_NOT_REQUIRED, CONFIRMATION_REQUIRED,
    CONFIRMED_BY_ATHLETE, CONFIRMED_BY_REVIEWER,
)

# A confirmation_required record is one an athlete should actually look at.
NEEDS_REVIEW = frozenset({CONFIRMATION_REQUIRED})

# ------------------------------------------------------------------ timezone
# The FIT spec gives UTC and no offset, so a local date has to come from
# somewhere. Say which somewhere.
TZ_CONFIRMED_OFFSET = "confirmed_offset"          # athlete supplied an offset
TZ_FILENAME_DATE = "filename_date"                # local date from the filename
TZ_ASSUMED_UTC = "assumed_utc"                    # no better source existed
TZ_UTC_ONLY = "utc_only"                          # UTC known, local unknown
TZ_UNKNOWN = "unknown"

TIMEZONE_SOURCES = (
    TZ_CONFIRMED_OFFSET, TZ_FILENAME_DATE, TZ_ASSUMED_UTC, TZ_UTC_ONLY,
    TZ_UNKNOWN,
)

# Only these may be presented as a settled local date.
LOCAL_DATE_IS_CONFIRMED = frozenset({TZ_CONFIRMED_OFFSET})

# -------------------------------------------------------------- completeness
# A gap in the record is one of these five things, and they are not
# interchangeable. The distinction is the whole point: "the watch had no sensor"
# is not "the athlete did not wear it", and neither is "we failed to import".
COMPLETE = "complete"
NOT_IMPORTED = "not_imported"          # no file was ever received
UNAVAILABLE_FROM_SOURCE = "unavailable_from_source"  # the file lacks the field
AWAITING_CONFIRMATION = "awaiting_confirmation"
PRESENT_LOW_CONFIDENCE = "present_low_confidence"
CONFIRMED = "confirmed"

COMPLETENESS_STATES = (
    COMPLETE, NOT_IMPORTED, UNAVAILABLE_FROM_SOURCE, AWAITING_CONFIRMATION,
    PRESENT_LOW_CONFIDENCE, CONFIRMED,
)

# States that mean "we do not know". None of these may be rendered as zero, as
# zero training, or as a rest day.
UNKNOWN_STATES = frozenset({
    NOT_IMPORTED, UNAVAILABLE_FROM_SOURCE, AWAITING_CONFIRMATION,
    PRESENT_LOW_CONFIDENCE, CONFIRMATION_REQUIRED, MISSING, UNVERIFIED,
})

# ----------------------------------------------------------- review reasons
# What a review item is about. A gap in the record is represented as a question
# for the athlete, never as a synthesised workout.
REVIEW_TIMEZONE = "timezone_uncertain"
REVIEW_DUPLICATE = "possible_duplicate"
REVIEW_DATE_GAP = "activity_gap"
REVIEW_AMBIGUOUS_TIMESTAMP = "ambiguous_timestamp"
REVIEW_MISSING_FIELDS = "missing_fields"

REVIEW_REASONS = (
    REVIEW_TIMEZONE, REVIEW_DUPLICATE, REVIEW_DATE_GAP,
    REVIEW_AMBIGUOUS_TIMESTAMP, REVIEW_MISSING_FIELDS,
)

OPEN = "open"
CLOSED = "closed"                          # nothing outstanding
RESOLVED = "resolved"
RESOLVED_NO_CHANGE = "resolved_no_change"   # athlete said the gap is real
DISMISSED = "dismissed"

REVIEW_STATES = (OPEN, CLOSED, RESOLVED, RESOLVED_NO_CHANGE, DISMISSED)

# ------------------------------------------------------------- training load
LOAD_VERSION = "load-1.0.0"

# Intensity buckets. Classification is only emitted when the signals for it
# exist; otherwise INTENSITY_UNAVAILABLE says so rather than guessing.
INTENSITY_EASY = "easy"
INTENSITY_STEADY = "steady"
INTENSITY_CONTROLLED_HARD = "controlled_hard"
INTENSITY_INTERVAL = "interval"
INTENSITY_UNAVAILABLE = "unavailable"

INTENSITY_BANDS = (
    INTENSITY_EASY, INTENSITY_STEADY, INTENSITY_CONTROLLED_HARD,
    INTENSITY_INTERVAL, INTENSITY_UNAVAILABLE,
)

# ------------------------------------------------------------- control state
# One of these is the only thing a recommendation is allowed to return.
STATE_BUILD = "build"
STATE_MAINTAIN = "maintain"
STATE_RECOVER = "recover"
STATE_DELOAD = "deload"
STATE_DATA_INSUFFICIENT = "data_insufficient"
STATE_CONFIRMATION_REQUIRED = "confirmation_required"

CONTROL_STATES = (
    STATE_BUILD, STATE_MAINTAIN, STATE_RECOVER, STATE_DELOAD,
    STATE_DATA_INSUFFICIENT, STATE_CONFIRMATION_REQUIRED,
)

# States where the system is saying it does not know. A rule must never fall
# through to an aggressive recommendation from either of these.
NON_ADVISORY_STATES = frozenset({STATE_DATA_INSUFFICIENT, STATE_CONFIRMATION_REQUIRED})

# -------------------------------------------------------------- weather gate
WEATHER_UNAVAILABLE = "unavailable"
WEATHER_BLOCKED_NO_LOCATION = "blocked_no_location"
WEATHER_BLOCKED_NO_CONSENT = "blocked_no_consent"
WEATHER_NO_MATCH = "no_match"
WEATHER_MATCHED = "matched"

WEATHER_STATES = (
    WEATHER_UNAVAILABLE, WEATHER_BLOCKED_NO_LOCATION,
    WEATHER_BLOCKED_NO_CONSENT, WEATHER_NO_MATCH, WEATHER_MATCHED,
)

# Personalised weather-performance claims stay off until enough matched
# observations exist. Fifteen is the floor; twenty is where it gets useful.
WEATHER_MIN_MATCHED_RUNS = 15
WEATHER_RECOMMENDED_MATCHED_RUNS = 20

# ------------------------------------------------------------------- text
# One disclaimer string, imported wherever a provisional number is shown, so
# the wording cannot drift between the dashboard and the report.
NON_MEDICAL = "Not medical advice."
NOT_INJURY_PREDICTION = (
    "Workload ratio, a monitoring signal only. Not an injury probability, "
    "risk score or diagnosis."
)
PROVISIONAL_HR = (
    "Heart-rate bands are provisional. Derived from an estimated maximum, not "
    "a laboratory or clinical measurement."
)
ESCALATION = (
    "Stop and seek a qualified clinician for pain that persists, altered gait, "
    "chest pain, or any medical concern. Nothing here is a diagnosis."
)


def worst(*labels):
    """Return the least trustworthy of several confidence labels.

    Accepts either varargs or a single iterable, so callers can pass a
    generator over a provenance map without unpacking it first.
    """
    if len(labels) == 1 and not isinstance(labels[0], str):
        labels = tuple(labels[0])
    vals = [CONFIDENCE_RANK[l] for l in labels if l in CONFIDENCE_RANK]
    if not vals:
        return UNVERIFIED
    return next(label for label, rank in CONFIDENCE_RANK.items() if rank == min(vals))


def needs_review(confirmation):
    return confirmation in NEEDS_REVIEW


def is_unknown(state):
    return state in UNKNOWN_STATES


def describe(value_state, confidence, confirmation):
    """One line naming state, confidence and review status, for a report."""
    bits = [value_state]
    if confidence and confidence != HIGH:
        bits.append(confidence)
    if confirmation and confirmation != CONFIRMATION_NOT_REQUIRED:
        bits.append(confirmation)
    return " / ".join(bits)
