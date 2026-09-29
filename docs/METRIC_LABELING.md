# Metric Labelling

Supervisor brief Task 11. Audit of every screen, report and calculation that
presents heart-rate zones, load ratios, recovery, weather, or training
completeness. Findings and the vocabulary to use going forward.

The rule this document exists to enforce: **a measurement, an algorithmic
indicator, and medical advice are three different things and must never be
presented as the same thing.**

## What was changed

| Location | Before | After |
| --- | --- | --- |
| Section heading | "Week at a glance + **injury risk**" | "Week at a glance + **load balance**" |
| Section description | ACWR is "the sports-science gauge that flags when a volume spike is pushing injury risk up" | Describes it as a load-balance ratio, labelled **Provisional**, with an explicit statement that it is not a validated injury predictor |
| ACWR verdict, 0.8–1.3 | "**Sweet spot** … the range associated with the lowest injury risk in the sports-science literature" | "**Balanced** … the range the current plan keeps you in" |
| ACWR verdict, 1.5–1.8 | "**High risk** … most strain injuries happen in or just after windows like this" | "**Stretched** … a cutback week or two would bring it back toward the band above" |
| ACWR verdict, >1.8 | "**Very high risk**" | "**Well above baseline**" |
| Recovery debt heading | bare name | suffixed "(algorithmic composite - not a diagnosis)" |
| Recovery debt panel | no caveat | added a Provisional note and a "Not medical advice" note |

## Findings that did not require a change

**The 195 bpm figure is a measurement, not an estimate.** The supervisor brief
assumed heart-rate zones are derived from a 195 bpm maximum and asked that
definitive zone claims be replaced. Inspection found no such derivation anywhere
in the dashboard:

- There is no max-HR variable, and no percentage-of-maximum zone maths.
- `195` appears only as `HISTORICAL_PR.peakHr` and on a PR card, both labelled
  "peak HR (bpm)".
- That is the *observed peak* on the 2026-06-16 breakout run, taken from the
  `Max HR` column of the export. It is a recorded value.

So no zone classification is being asserted. The brief's concern is satisfied
already, though see the limitation below.

**Peak and average HR are present and are real.** Both come from the Garmin
export's `Max HR` and `Avg HR` columns.

## Remaining weaknesses

1. **The ACWR label is a caveat, not a fix.** The ratio is still computed and
   still drives plan adjustments. Labelling it honestly is the minimum; the
   deeper problem is that arbitrary weights feed real training decisions.

2. **Recovery debt remains an arbitrary composite.** The weights
   (ACWR 30–50, TSB 8–35, weight 8–15, injury recency 14–28) were chosen by
   hand and have no validation behind them. It is now labelled, but a labelled
   arbitrary number is still an arbitrary number.

3. **No zone vocabulary exists yet.** The brief asks for support for future
   threshold or field-test inputs "without requiring them now". Nothing is
   implemented for that, and no zone claim is being made, so this is a
   prerequisite rather than a defect.

4. **The dashboard is not version controlled.** It embeds an exact latitude and
   longitude per run, so it is gitignored and cannot be committed. Every change
   made to it in Task 11 is therefore **unrecoverable if the file is lost.** This
   is the most significant structural problem in this repository and is recorded
   in `IMPLEMENTATION_INVENTORY.md`.

5. **Weather is displayed without a completeness marker.** The dashboard fetches
   historical conditions from Open-Meteo using per-run coordinates. Runs with no
   successful retrieval do not appear to be distinguished from runs with one.

## Vocabulary

Use these labels consistently across every report, screen and API response.

| Label | Meaning |
| --- | --- |
| **Provisional** | Derived from assumptions or arbitrary weights. Adjustable, not validated. |
| **Athlete-reported** | Entered by the athlete. Subjective. |
| **Device-derived** | Read from a wearable or the activity file. |
| **Algorithmic** | Computed by a documented formula. Record the formula version. |
| **Missing / unavailable** | Not present. Never substitute an estimate silently. |
| **Low confidence** | Present, but matched or derived unreliably. |
| **Requires athlete confirmation** | The system cannot tell. The athlete decides. |
| **Not medical advice** | Required wherever anything touches injury, pain or recovery. |

### Prohibited phrasings

- "lowest injury risk", "safest range", "injury risk band" — asserts a validated
  causal relationship that ACWR does not support.
- "overreach band", "high risk" as a verdict — presents an indicator as a
  diagnosis.
- "diagnostic", "detect", "predict injury" — outside what any of these metrics
  can do.
- Any unqualified "risk" or "readiness" score.
- Any number presented as a target without stating it is provisional.

## Weather labelling, for the pipeline

The published CSV has no weather columns and Garmin does not record weather, so
any future enrichment must distinguish:

- **Historical** enrichment, keyed to a completed activity's timestamp/location.
- **Forecast** retrieval, which requires a *planned* location and time.

These are different things and must not be conflated in a schema or a UI. A
failed lookup is **unavailable**, never a zero, never a seasonal average, and
never a value attributed to a provider that was not actually called.
