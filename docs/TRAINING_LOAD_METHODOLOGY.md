# Training load methodology

Supervisor brief Task 5. Implementation: `loadcalc.py`.
Current formula version: **`load-1.0.0`** (also in `terms.LOAD_VERSION`).

## The rule this module exists to enforce

Running load and strength load measure different things. They are **never**
returned as a bare total without their components. Every result carries:

- `version` — the formula that produced it
- `run_load` and `strength_load` — separately, always
- `combined_load` — only when at least one component is real
- the exact activity ids and calendar days included
- the inputs needed, so it can be recomputed or challenged

## Windows

7, 14 and 28 days, all three computed on every call. Each window reports its
own `run_days` and `strength_days`, and the activity ids that fell inside it.

## Running load

Heart-rate intensity bucket, scaled by duration. TRUMP-like: the ratio of
average heart rate to a maximum estimate selects a multiplier.

| `hr_avg / hr_max` | multiplier |
| --- | --- |
| ≤ 0.50 | 1.0 |
| ≤ 0.65 | 1.5 |
| ≤ 0.80 | 2.5 |
| ≤ 0.90 | 4.0 |
| > 0.90 | 5.0 |

```
run_load = (moving_time_s / 60) × multiplier
```

### `hr_max` is never estimated

There is no age-based or default maximum anywhere in this codebase. A
`hr_max` that is not supplied produces an **unavailable** running load, not a
guess:

```python
{'activity_id': 'garmin:24487279921', 'reason': 'no hr_max supplied'}
```

This is a deliberate refusal. An estimated maximum silently changes every load
number in the system, and 220 − age is a population heuristic rather than a
measurement. The athlete supplies a value or the column stays empty.

`hr_max` is not in the `activities` table. It is a caller input to
`loadcalc.compute()`. A profile field is the obvious home for it and
`profile.json` currently holds nulls — see `docs/IMPLEMENTATION_INVENTORY.md`.

## Strength load

Session-RPE method:

```
strength_load = (Σ load_kg × reps over working sets) × session_rpe / 100
```

`session_rpe` is the mean of recorded per-set RPE. Confidence is `high` when
every working set has an RPE, `medium` when some do, and `low` when none do and
the fallback of 5.0 was used. An assumed RPE is labelled as an assumption
rather than presented as a measurement.

Warmups are excluded, matching `strength.session_volume()`.

## Unavailable is not zero

When inputs are missing, the component is `None` and the reason is recorded in
`unavailable`:

| Missing input | Result |
| --- | --- |
| `avg_hr` | `None`, `"no avg_hr in source"` |
| `hr_max` | `None`, `"no hr_max supplied"` |
| `moving_time_s` | `None`, `"no moving_time_s"` |
| no working sets | `None`, `"no working sets"` |
| no loaded volume | `None`, `"no loaded volume"` |

`combined_load` is `None` only when **both** components are unavailable.

## Acute:chronic ratio

```
acwr = combined_load(7d) / combined_load(28d)
```

Returns `None` when chronic is missing or zero, never `0.0` and never infinity.

**This is a monitoring signal. It is not an injury probability, not a risk score,
and not a clinical measure.** It is a ratio of two load windows, and a number in
a high band is a reason to reduce volume — not a prediction that something will
happen. `terms.NOT_INJURY_PREDICTION` is attached to every recommendation.

## Snapshots

`loadcalc.save_snapshot()` persists a computed result with its `version` and its
full `inputs_json`. A number quoted today remains explainable after the formula
changes, because the row names the formula that produced it and carries the
evidence.

## Known limitations

- The heart-rate buckets are conventional, not clinically derived, and are not
  tuned to this athlete.
- `combined_load` sums a heart-rate-weighted duration figure with a
  volume-weighted RPE figure. The components are always returned so the sum can
  be decomposed, but the sum itself is a convenience, not a physical quantity.
- No tapering, no long-term fitness model, no cross-validation of the buckets.
- Load windows are calendar windows, not rolling sessions-ago windows.
