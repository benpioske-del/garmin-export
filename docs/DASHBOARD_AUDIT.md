# Dashboard data-source audit

GENERATED FILE -- do not edit by hand. Regenerate with:

```
python dashboard_contract.py
```

This exists because `dashboard/index.html` is gitignored and therefore
invisible to the brief process. Every brief has consequently invented its
contents. This file is a faithful, machine-checked description of the real
file, so a brief can read the truth instead of guessing at it.

| | |
| --- | --- |
| Result | PASS |
| Canonical surfaces fetched | 3 of 3 |
| Source registry present | yes |
| Failure path renders visible text | yes |
| Local-only data read by canonical panel | none |

## Canonical surfaces

These are the only authoritative answers for activities, load and
coaching. They are served from `trainloop.db` via `garmin_server.py`.

| Surface | Route | Fetched by canonical panel | Rejection handler |
| --- | --- | --- | --- |
| `activities` | `/api/activities` | yes | yes |
| `load` | `/api/load` | yes | yes |
| `coaching` | `/api/coaching` | yes | yes |

Every surface must handle its own rejection. A fetch with no error
callback leaves the card blank, and a blank card is how a panel grows a
stale-data fallback a few weeks later.

## Local-only data

Hand-entered, private, and never authoritative for the surfaces above.
This is the athlete's own journal -- narrative notes, splits, hydration,
injury flags, body weight, coordinates -- and it contains data that does
not exist in any FIT file. It is not redundant with the canonical corpus
and is not a stale copy of it. It must not be deleted, and it must not be
presented as if the data layer had produced it.

| Declaration | Kind |
| --- | --- |
| `baseLifts` | athlete journal |
| `baseRuns` | athlete journal |
| `baseWeights` | athlete journal |
| `briefLog` | athlete journal |
| `customRuns` | athlete journal |
| `customWeights` | athlete journal |
| `deletedRunKeys` | athlete journal |
| `experiments` | athlete journal |
| `garminFitList` | athlete journal |
| `lifeLoad` | athlete journal |
| `liftEntries` | athlete journal |
| `microByDay` | athlete journal |
| `nutritionLog` | athlete journal |
| `runOverrides` | athlete journal |
| `savedRoutines` | athlete journal |
| `splitOverrides` | athlete journal |
| `trainingLedger` | athlete journal |
| `weeksData` | athlete journal |
| `weightEntries` | athlete journal |
| `AGEF_F` | static table |
| `AGEF_M` | static table |
| `CHASKA` | static table |
| `GEL_SPEC` | static table |
| `GUARD_RAILS` | static table |
| `HISTORICAL_PR` | static table |
| `LAB_HINTS` | static table |
| `T5K_ANCHORS_F` | static table |
| `T5K_ANCHORS_M` | static table |
| `__dashRenderErrors` | scratch/cache |
| `charts` | scratch/cache |
| `tempCache` | scratch/cache |
| `wxCache` | scratch/cache |

Every top-level declaration in the file must appear above. An undeclared
one fails the audit, so inline data cannot be added silently.

