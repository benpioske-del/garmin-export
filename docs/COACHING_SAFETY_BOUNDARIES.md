# Coaching and safety boundaries

Supervisor brief Task 6. Implementation: `recommend.py`, `strength.py`.

## What this system will and will not say

It returns exactly one of six control states, with the evidence behind it:

| State | Meaning |
| --- | --- |
| `build` | Load is in the established band. Progression is optional. |
| `maintain` | Hold. Includes every "ratio too low to act on" case. |
| `recover` | Available state, not currently reachable by rule. |
| `deload` | Acute load is at or above the upper bound. |
| `data_insufficient` | **Refusal.** Not enough recorded history. |
| `confirmation_required` | **Refusal.** Records are awaiting the athlete. |

There is no free-text advice path. That is structural, not stylistic: a
recommendation cannot drift into "you should probably push through this" if
the only thing the function can return is a state plus evidence.

## Refusal outranks analysis

`recommend.recommend()` checks the refusals before it looks at load, in this
order:

1. **`confirmation_required`** — any activity in the 28-day window still has an
   open review item. Numbers derived from unconfirmed records are provisional,
   so this outranks every load figure.
2. **`data_insufficient`** — fewer than 8 runs in 28 days.
3. **`data_insufficient`** — fewer than 3 runs in 7 days. The acute window has
   to be established before it can be compared to the chronic one.
4. **`data_insufficient`** — running load unavailable (no `hr_max`, no
   `avg_hr`).

A rule is never allowed to reach `build` by defaulting an input to zero. The
absence of a heart-rate maximum produces an unavailable load, which produces a
refusal.

## Operating bands

Applied to the 7-day over 28-day acute:chronic ratio.

| Ratio | State |
| --- | --- |
| ≥ 1.5 | `deload` — reduce volume; do not add intensity to compensate |
| ≥ 1.3 | `maintain` — hold volume, add no load this week |
| < 0.8 | `maintain` — **a low ratio is not a reason to add volume** |
| 0.8 – 1.3 | `build` |

The floor deliberately has no route to `build`. Being undertrained is not
itself a reason to increase load, so a low ratio holds. The lower bound only
prevents a deload recommendation; it never authorises progression.

The 1.5 and 1.3 bounds are conventional operating limits, quoted here so the
decision is auditable. They are not thresholds for anything clinical.

## Strength boundaries

From `strength.suggest_progression()`:

- **Rest:** minimum 2.0 minutes between sets. Shorter is flagged, not accepted.
- **Warmups:** tracked separately, excluded from volume and from progression.
  A session of nothing but warmups yields `no_history`.
- **Effort ceiling:** RPE > 8.0 → hold.
- **Reps reserve:** RIR < 2 → hold. Too close to failure to add load.
- **Consistency:** any set short of the session's best rep count → hold before
  considering load.
- **Increment:** +1.25 kg (2.5 lb), reduced to +0.5 kg for light lifts. One
  small step at a time; no function path proposes a jump.

Every suggestion carries `Not medical advice.`

## Heart-rate bands

Any heart-rate band in this system is **provisional** and derived from an
estimated maximum, not a laboratory or clinical measurement:

> Heart-rate bands are provisional. Derived from an estimated maximum, not a
> laboratory or clinical measurement.

## What is never produced

- Injury probability, risk score, or diagnosis
- A "return to training" clearance
- "Safe to run today" as a medical judgement
- A personalised weather-performance claim
- A training decision while records await confirmation
- A training decision from missing data

## Escalation

Displayed wherever a recommendation appears:

> Stop and seek a qualified clinician for pain that persists, altered gait,
> chest pain, or any medical concern. Nothing here is a diagnosis.

## Limits

- No authentication and no multi-athlete separation. The database is local and
  gitignored, so this is a single-athlete tool, not a permission system.
- `recommend()` takes `hr_max` as an argument and does not read a profile. Until
  `profile.json` carries a value, the running-load path returns unavailable and
  the recommendation is `data_insufficient`.
- `recover` is defined and reachable through `available_states()` but no rule
  currently emits it.
- Bands are untuned to this athlete. They are conventional defaults, and the
  docstring says so.
