# Data quality terminology

Supervisor brief Task 7. Definitions live in `terms.py`; this file explains why
they are three separate axes rather than one field.

## The core mistake this avoids

"Provisional", "estimated" and "unconfirmed" get used interchangeably. They
mean three different things, and a system that uses one word for all three
cannot answer "should I trust this?".

An activity can be **device-derived**, **low confidence**, and
**confirmed by the athlete** all at once — the watch recorded it, the number
looks wrong, and the athlete has said so. A single status field cannot express
that.

## Three axes

### 1. Value state — where the number came from

| State | Meaning |
| --- | --- |
| `observed` | Read directly from the source file. |
| `device_derived` | Computed by the Garmin device itself (TSS, avg HR). |
| `algorithmic` | Computed here, versioned (pace from distance/time). |
| `athlete_reported` | Stated by the athlete. |
| `assumed` | Filled in because nothing better existed. |
| `imported` | Carried over from another system. |
| `manual` | Typed by a human. |
| `clinician_provided` | Supplied by a clinician. |
| `missing` | **Absent.** Never coerced to zero. |

`assumed` and `missing` are the pair most often conflated. The local date is
`assumed` — it exists but its source is a filename. A field the watch never
recorded is `missing`. Both are `unknown`, but only one has a value that could
be wrong.

### 2. Confidence — how much to trust it

`high` · `medium` · `low` · `unverified`

Ordered worst-first in `CONFIDENCE_RANK` so a caller can take the **weakest
contributor** across a record with `terms.worst()` rather than averaging. A
record with fifteen high-confidence fields and one unverified field is not a
high-confidence record.

`worst()` accepts either varargs or a single iterable, so a provenance map can
be passed without unpacking.

### 3. Confirmation — whether a human signed it off

`not_required` · `confirmation_required` · `confirmed_by_athlete` ·
`confirmed_by_reviewer`

Separate from confidence. **Confirmed means a human decided, not that a number
looks right.** A value can be high-confidence and unconfirmed (the watch was
certain; nobody has checked it), or low-confidence and confirmed (the number
looked wrong; the athlete confirmed it anyway).

## Timezone sources

| Source | Local date status |
| --- | --- |
| `confirmed_offset` | Settled. Only state presentable as a real local date. |
| `filename_date` | Assumed from the FIT filename. |
| `assumed_utc` | UTC assumed with no better source. |
| `utc_only` | UTC known, local unknown. |
| `unknown` | Neither. |

`terms.LOCAL_DATE_IS_CONFIRMED` contains only `confirmed_offset`. An evening run
crossing midnight UTC is why this matters: the UTC date and the local date can
differ, and the two are exported in separate columns rather than one being
silently labelled as the other.

## Completeness

| State | Means |
| --- | --- |
| `complete` | Present from a trustworthy source. |
| `not_imported` | No file received. **Not** "did not train". |
| `unavailable_from_source` | File exists, field absent. |
| `awaiting_confirmation` | Value exists, unconfirmed. |
| `present_low_confidence` | Value exists, unverified. |
| `confirmed` | Human signed it off. |

`terms.UNKNOWN_STATES` collects everything that means "we do not know". No
member of that set may be rendered as zero, as zero training, or as a rest day.

`not_imported` and `unavailable_from_source` are the pair that must not be
merged: a watch with no HR sensor is not a watch left in a drawer.

## Review reasons

`timezone_uncertain` · `possible_duplicate` · `activity_gap` ·
`ambiguous_timestamp` · `missing_fields` · `strength_safety`

Review states: `open` · `closed` · `resolved` · `resolved_no_change` ·
`dismissed`

`resolved_no_change` exists because sometimes the correct outcome is that
nothing was wrong — the athlete confirms a gap is real, and the record stands
as it is.

## A gap is a question, not a row

The strongest rule in the system: **a data gap becomes a review item, never an
invented activity.** No code path creates a placeholder session, and none
synthesises a workout for a day with no file. `test_date_gap_is_reported_and_nothing_is_invented`
enforces that the activity count is unchanged after gap detection.

## Where each label appears

| Surface | Source |
| --- | --- |
| Database | `activities.value_state/confidence/confirmation`, `activity_field_provenance` |
| API-shaped output | same three fields, names unchanged |
| Reports | `terms.describe()` |
| Dashboard | `docs/METRIC_LABELING.md` |

`terms.describe(value_state, confidence, confirmation)` produces the one-line
form used in reports, so a label cannot read one way in the database and
another way in a document.

## Limits

- These are English string constants, not an enum type or an i18n layer. There
  is no display-name translation table, so the stored value is also the
  user-facing value.
- `clinician_provided` is defined but nothing currently produces it. The health
  module accepts only `athlete_reported` and `manual`.
- `recover` is a defined control state that no rule currently emits.
- There is no validation that a stored label is a member of its axis. A bad
  value written directly to SQLite would not be caught at read time.
