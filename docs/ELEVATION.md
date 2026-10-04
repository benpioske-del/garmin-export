# Elevation is derived, not measured

Added with `garmin_fit_reader` 1.1.0. This records why the published
`Total Ascent` disagrees with what a watch or Garmin Connect shows, and what the
pipeline now does about it.

## The complaint that prompted this

A run reported as having roughly 1700 ft of ascent. The CSV said 1765 ft for
`2026-09-24`, which is a 16-mile run, not the most recent one. The most recent
run, `2026-09-29`, is 5 miles and the CSV says 495 ft while the watch display
show 442 ft.

Two separate things were going on:

1. **Two different activities.** 1765 ft belongs to 09-24. The most recent run
   is 09-29 at 495 ft. The dashboard could not arbitrate: its newest embedded
   activity is `2026-09-13`.
2. **Two different algorithms** over the same altitude samples for 09-29:
   495 ft in the file, 442 ft on the wrist.

## Why the two algorithms disagree

These files contain **no `barometer_pressure` samples at all**. Altitude is
inferred from GPS, sampled every ~6 seconds, carrying several feet of noise per
sample. Any algorithm that sums upward steps counts that noise as climbing.

`2026-09-29`, 560 samples, 5.0 miles:

| Method | Ascent |
| --- | --- |
| Naive sum of every positive step | 596 ft |
| Device `session.total_ascent` (what we publish) | 495 ft |
| Watch display | 442 ft |
| Smoothed over ~30 s | 470 ft |
| Smoothed over ~2 min | 298 ft |
| Total elevation range | 228 ft |

Roughly **300 ft of the 596 ft naive figure is noise**, not hill. A threshold
sweep in 5 cm steps shows the published 495 ft and the watch's 442 ft landing on
adjacent steps of the same algorithm — 0.60 m gives 473 ft, 0.65 m gives 424 ft.
They are the same computation with a slightly different cutoff, or the same
cutoff against a slightly different series.

`altitude` and `enhanced_altitude` are byte-identical on current firmware, so
there is no separate smoothed series to reconcile against.

## What the reader now does

`Total Ascent` is still the device's own `session.total_ascent`, converted from
metres. It is not replaced by our own figure. Inventing a different number would
be worse than passing through the device's, and the published CSV header has not
changed.

Alongside it the reader attaches internal diagnostics:

| Key | Meaning |
| --- | --- |
| `_ascent_raw_ft` | naive sum of every positive step; the upper bound |
| `_ascent_smoothed_ft` | same after a 5-sample (~30 s) moving average |
| `_elev_range_ft` | max minus min altitude; the scale the climb must fit inside |
| `_ascent_samples` | altitude sample count |

These are **excluded from `garmin_export.csv`**. They are underscore-prefixed
internal keys, and `export_publish.build_csv()` now skips every underscore key
except `_source_file`. This was not theoretical: the first build after adding
them published all four as CSV columns, and
`tests/test_provenance.py::test_internal_diagnostics_never_reach_the_published_csv`
caught it.

They exist so a reviewer can see the band rather than trust a single number. On
the 16-mile run, 1765 ft of climb inside an 84 ft range is 21 traversals of the
range — possible on rolling ground, but not something to assert without the
band beside it.

## Why this is not "fixed"

Ascent has no ground truth. Distance and duration are recorded; elevation is
inferred from a noisy signal. Any number here is an estimate, and a different
estimator will disagree.

The consequence for coaching is the part worth stating plainly: **ascent is the
weakest field in the file and must never drive a load, progression or injury
decision on its own.** It is useful for describing a route, not for quantifying
a training effect. The diagnostics make the uncertainty visible; they do not
remove it.

Reconciling the watch figure exactly would need the official Garmin Connect CSV
row for the activity, which is not in this repository. Until then the file value
stands and the band is published beside it in process.

## Reader 1.1.0 also fixed a latent bug

`read_fit` previously appended **both** `enhanced_altitude` and `altitude` from
the same record into one list. On current firmware they are identical, so
`Min Elevation` and `Max Elevation` were unaffected. On firmware where they
diverge it would have taken a minimum from one series and a maximum from the
other. The reader now takes one sample per record, preferring
`enhanced_altitude`.

Covered by `tests/test_fit_reader_elevation.py`.