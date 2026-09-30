# Strength data contract

Supervisor brief Task 4. Schema: `migrations/003_strength.sql`. Service:
`strength.py`. Tests: `tests/test_training_data.py`.

## What this domain is for

Strength work is a session containing many exercises, each containing many
sets. The schema reflects that directly:

```
strength_sessions
  └── strength_session_exercises   (many per session, ordered)
        └── strength_sets          (many per exercise, numbered)
strength_exercises                (catalogue, shared across sessions)
```

An earlier design would have collapsed a session into a single volume number.
That is deliberately avoided: one number hides whether the work was legs or
arms, and a training log that cannot answer "what did I actually do" is not much
use.

## Sets

| Field | Notes |
| --- | --- |
| `reps` | Required for a set to count toward volume. |
| `load_kg` | `NULL` for bodyweight. **Never 0** for "no weight" — a zero-kilogram set is meaningless and the distinction matters to volume. |
| `load_display` | The athlete's literal text (`"135"`, `"2 plates"`, `"bodyweight"`). Preserved so nothing is lost when a value is not cleanly parseable. |
| `rpe` / `rir` | Per set. Drives progression. |
| `is_warmup` | Warmups are excluded from volume and from progression. |
| `tempo` | Free text, e.g. `"3-1-1-0"`. |
| `rest_s` | Defaults to **120 s**. Shorter values are flagged. |
| `distance_m` / `duration_s` | For carries, holds and timed work. |
| `value_state` / `confidence` | Distinguishes manual entry from imported. |

Load and `load_display` are both permitted: plates-added bodyweight work has a
bodyweight text and a numeric increment, and rejecting either one would lose
information.

## Provenance

Every set carries `value_state` and `confidence` so an imported set is never
mistaken for one the athlete typed:

- `manual` / `medium` — typed by the athlete
- `observed` / `high` — read from a device source, when one exists

Strength writes its history to the **shared** `activity_import_audit` table with
`strength_`-prefixed events and `strength.`-prefixed field names. There is no
second audit system. `test_strength_history_shares_the_audit_table` enforces
this.

Safety flags go to the shared `review_items` queue under the reason
`strength_safety`, which is why `review_items.activity_id` is not a foreign key:
a `strength:`-prefixed session id is not a row in `activities`.

## Volume

```python
strength.session_volume(conn, session_id)
# {'by_exercise': {'Back Squat': 500.0, ...}, 'total_kg_reps': 900.0}
```

Warmups excluded. Bodyweight sets contribute their reps but no load, which is
why the per-exercise breakdown is returned rather than a single total.

## Safety constraints, enforced in code

These are not left to the caller:

| Constraint | Enforcement |
| --- | --- |
| Rest between sets is at least 2.0 min | `MIN_REST_S = 120`; a shorter recorded rest opens a `strength_safety` review item rather than being silently accepted. |
| Warmup sets tracked separately | `is_warmup`; excluded from `session_volume()` and from `suggest_progression()`. |
| Conservative load increases | `suggest_progression()` holds unless every working set was completed at or under the effort ceiling. |

`test_warmups_alone_do_not_drive_progression` covers the case where a session
contains nothing but warmups: the answer is `no_history`, not a load
recommendation derived from warmup performance.

## Progression

`strength.suggest_progression()` returns a decision with reasoning, never a bare
number.

```
{'decision': 'increase', 'load_kg': 101.25, 'increment_kg': 1.25,
 'reason': 'all 3 working sets completed, RPE within ceiling',
 'confidence': 'medium', 'disclaimer': 'Not medical advice.'}
```

Rules, in evaluation order:

1. **Any set short of the session's best rep count → hold.** Inconsistent
   performance is the first thing to fix, not add load to.
2. **Any set with RPE > 8.0 → hold.**
3. **Any set with RIR < 2 → hold.** Too close to failure to add load.
4. **Bodyweight → add reps**, not load.
5. **Otherwise → +1.25 kg** (2.5 lb, the smallest plate most gyms stock).
   Reduced to +0.5 kg below half bodyweight.

A single small increment is the ceiling. There is no path in this function that
proposes a jump, and no path that recommends load while effort is high or a set
was missed.

## Limits

- No UI, no API, no dashboard. Deliberately out of scope for this task.
- No authentication. The database is local and gitignored; see
  `docs/IMPLEMENTATION_INVENTORY.md`.
- `is_bodyweight` is inferred from `load_kg is None and not load_display` at
  insert time and is not subsequently corrected when a session is edited. This
  is a known rough edge, not a designed behaviour.
- Exercise identity is `lower(trim(name))`. Two genuinely different movements
  sharing a name will merge unless distinguished by `equipment`, and
  `equipment` is not currently exposed on the public helper signature in a way
  that makes that ergonomic.
