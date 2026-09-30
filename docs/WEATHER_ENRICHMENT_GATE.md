# Weather enrichment gate

Supervisor brief Task 9. Implementation: `weather.py`. No UI was built.

## What the gate does

`weather.gate()` returns one of five states and a reason. It returns
**no observation data** until the gate is `matched`.

| State | Meaning |
| --- | --- |
| `blocked_no_location` | No location policy recorded. |
| `blocked_no_consent` | Consent not recorded for weather enrichment. |
| `unavailable` | Location and consent fine; no provider configured. |
| `no_match` | Too few matched runs for a per-condition claim. |
| `matched` | Enough matched runs; descriptive output only. |

## Coordinates are not stored

`weather_observations` has **no `lat`, `lon`, `latitude` or `longitude`
column**, and none may be added. `test_weather_schema_stores_no_coordinates`
asserts this against `PRAGMA table_info`.

`location_key` is a rounded grid cell:

```python
weather.location_key(40.01, -75.02)  # '+40.00_-75.00'
```

At `GRID_DEGREES = 0.25` that is roughly 25 km — fine enough to group runs by
general climate, far too coarse to reconstruct a route. `weather.py` accepts
coordinates as an argument and persists only the rounded cell;
`test_observation_persists_only_the_coarse_key` asserts the precise values
appear nowhere in the stored row.

## FIT coordinates are not a substitute

This is the part worth being explicit about. The FIT files contain exact GPS for
every activity, and it would have been trivial to derive a location from them.
The gate does not, and returns `blocked_no_location` instead:

> no location policy recorded; FIT coordinates are exact and were not used as a
> substitute

The brief requires a location policy before any enrichment, and reading exact
position data to bypass that requirement would defeat it. Using it to derive a
coarse cell is still using it.

## No personalised predictions

No "you run 8% slower in heat" claim is produced, and none may be built on this
table without further work. Even with consent and a location,
`personalised_claim_state()` gates on observation count:

| Matched runs | Result |
| --- | --- |
| ≥ 20 | `matched` — descriptive only, still not a prediction |
| 15–19 | `matched` — descriptive only, below the recommended split |
| < 15 | `no_match` — claim unsupported |

Fifteen is the floor; twenty is where a per-condition split starts to mean
something. Below the floor the answer is "unsupported", not a weaker version of
the claim. A weather-matched pace comparison is confounded by terrain, effort
and nutrition, and a few observations cannot separate those.

## Provider

None. `gate()` returns `unavailable` once location and consent are satisfied.
Nothing in this repository fetches weather. The local `dashboard/index.html`
has an Open-Meteo call, but that file is gitignored, is not the published
dashboard, and is not a provider for this gate.

## Open decisions

The athlete has not chosen a location policy. The brief allows:

- athlete-provided approximate home location
- a one-off location only for a single activity
- automatic derivation from activity start

Until one is chosen the default is conservative, and `gate()` blocks. When
chosen, it belongs in `profile.json` (currently all nulls) rather than being
inferred.

## Limits

- No provider adapter, so `matched` is unreachable through the gate today.
- `weather_run_matches` pairs a run to an observation by time proximity within
  the same grid cell, with a 1-hour default tolerance. It stores no distance
  between the two.
- `haversine_km()` exists but is not used by any current code path.
- Observation schema is fixed by migration `006`; adding precise location would
  require a new migration **and** reversing a documented decision.
