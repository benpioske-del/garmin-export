# Verification Report

**Date:** 2026-09-29
**Repository:** `benpioske-del/garmin-export`
**Verified revision:** `b3722432f4a985017410baa6384cdda24dc43306` (34 commits)
**Environment:** Windows, Python 3.13.15, git 2.53.0.windows.4

This report records only what was executed and observed. Nothing is marked
complete on the basis of code inspection alone.

## 1. Two live privacy leaks found and fixed

The most significant finding of this run. Both files were **tracked and publicly
served on `main`**, and both were missed by an earlier verification sweep.

| File | Leak | Public status before fix |
|---|---|---|
| `tools/privacy_replacements.txt` | Four real coordinates | HTTP 200, 944 bytes, live |
| `capture_supervisor_brief.py` | Two real coordinates quoted as pattern examples | HTTP 200, live |

`tools/privacy_replacements.txt` was a `git filter-repo` scrub script that
contained the exact values it existed to remove. It had been reintroduced into
tracked files and published.

### Root cause of the guard gap

`guard_gps_content()` in `export_publish.py` only matched **labelled**
coordinates (`"latitude": 44.9`). Both leaks were *unlabelled* values. Worse,
`GUARD_IMPL` fully exempted the scanner's own source and tests, so a real
coordinate quoted in a comment inside a scanner file was never checked at all.

### Fixes applied

1. Deleted `tools/privacy_replacements.txt` from the worktree and from history.
2. Replaced the real coordinates in `capture_supervisor_brief.py` with fabricated
   values, with a comment stating that real positions must never be quoted.
3. Removed the town name from `docs/PRIVACY_INCIDENT.md`.
4. Added an **unlabelled degree-pair** pattern, bounded to plausible latitude so
   that lap times such as `5.0712, 5.0844` are not blocked.
5. Narrowed the `GUARD_IMPL` exemption: those files are still exempt from the
   labelled patterns, which they must spell out, but are **no longer exempt from
   the degree-pair check**. Synthetic values are allowlisted by explicit value in
   `SYNTHETIC_PAIRS`, and the allowlist applies only to those files.
6. Added 5 regression tests, including `test_real_repository_passes_its_own_guard`
   which runs the guard against the real repository.

A first attempt at the new rule produced a false positive on the lap-time example
`5.0712, 5.0844`; that was fixed by bounding the latitude component, and the
over-blocking case is now covered by `test_low_latitude_decimal_pairs_are_not_flagged`.

### History rewrite

Three `git filter-repo` passes, then a force-push (`6c3bd91...a2bbd3d (forced update)`).

Verification scanned **every blob in every commit** rather than trusting a
pickaxe search, which had reported false positives from diff context:

```
CLEAN: no blob in any history contains a real value
```

Checked for: `44.759657`, `93.62763`, `44.9588`, `93.1618`, `44.7016`,
`93.6554`, `Chaska`, `Minneapolis` — all zero occurrences across all 34 commits.

Also deleted: `.git/filter-repo/fast-export.original`, a 417 KB plaintext dump of
the pre-rewrite history that still contained the dashboard and coordinates, and
the temporary scrub expression files.

## 2. Test suite

```
python -m pytest
65 passed in 77.07s (0:01:17)   exit 0
```

Up from 60 tests; 5 new regression tests for the guard gap.

## 3. Public repository state

| Check | Result |
|---|---|
| Public `main` tip | `a2bbd3d…` via API, matching local |
| `tools/privacy_replacements.txt` | Removed from `main` |
| `capture_supervisor_brief.py` | Clean on `main` |
| `export_publish.py`, `tests/test_gps_guard.py`, `docs/PRIVACY_INCIDENT.md` | Clean |
| `garmin_export.csv`, `docs/FIT_DATA_AUDIT.md` | Clean, no coordinates |

## 4. Publisher

```
python export_publish.py
runs        : 56  (2026-04-14 -> 2026-09-26)
committed   : garmin export: 56 runs, latest 2026-09-26
pushed      : origin/main
exit 0
```

Working tree clean after publish. Local `main` and `origin/main` verified in sync.

## 5. Scheduled tasks

`Garmin Export Publish` and `Garmin Export Publish PM` both `Ready`, pointing at
`C:\Users\benpi\Downloads\garmin_publish_task.bat`.

An earlier AM run reported `2147946720` (`0x800710E0`, "request refused"). This
was **not a fault**: the task is configured `MultipleInstances: IgnoreNew` and was
skipped because a manual run held the lock. Re-run manually, it returns `0` and
publishes correctly.

## 6. Static analysis, build, and CI

| Check | Command | Result |
|---|---|---|
| Lint | — | **Cannot run.** Not configured in the repository. |
| Format | — | **Cannot run.** No formatter configured. |
| Type check | — | **Cannot run.** No type checker configured. |
| Build | `python -m build` | Configured via setuptools; no lockfile, never run in CI. |
| Migrations | — | **Not applicable.** No database exists. |
| CI | — | **None.** No `.github/workflows`. |
| Dependency audit | — | **Not configured.** |

These are recorded as unavailable rather than passed. Task 12's full suite is
therefore limited to pytest plus the publisher and the privacy checks above.

## 7. Representative workflows

| Workflow | Evidence | Status |
|---|---|---|
| Running activity import | 56 rows, 2026-04-14 to 2026-09-26 | **Verified** |
| Duplicate re-import | CSV duplicate collapsed; publisher is idempotent ("data unchanged") | **Verified** |
| Timestamp discrepancy review | Documented in `docs/PROVENANCE.md`; **still unresolved by design** | **Open** |
| Data-completeness confirmation | No implementation exists | **Not built** |
| Strength session creation | No implementation exists | **Not built** |
| Consent grant/revocation | No implementation exists | **Not built** |
| Running/strength load calculation | No implementation exists | **Not built** |
| Recommendation generation | No implementation exists | **Not built** |
| Blocked weather enrichment | No implementation exists | **Not built** |
| Mocked weather enrichment | No implementation exists | **Not built** |

## 8. Security and privacy checks

- No `.env`, credential file, or raw FIT file is tracked.
- `C:\Users\benpi\Downloads\garmin_fit\` (56 GPS-bearing files) is outside the
  repository and untracked.
- `dashboard/` is gitignored; it embeds exact per-run GPS and is local-only.
- `profile.json` is tracked but every athlete value is `null`.
- The publication guard now catches unlabelled degree pairs and checks its own
  source files, closing the gap that allowed both leaks.

## 9. Open risks

1. **GitHub retains the old leaking commit.** `6c3bd91` is no longer on `main`,
   but the API still returns it and the raw URL still serves the file. Unreachable
   objects are retained server-side. Only deleting and recreating the repository
   guarantees removal; that changes the URL and requires updating the CrewAI
   polling configuration.
2. **The 26 July timestamp discrepancy remains unresolved**, deliberately. It is
   recorded rather than silently corrected, pending athlete confirmation.
3. **The dashboard is unversioned.** Its Task 11 labelling fixes exist only in a
   gitignored local file and would be lost if that file were lost. Making it
   durable requires splitting code from embedded GPS data.
4. **No lint, format, type-check, or CI exists**, so the guard that caught these
   leaks is enforced only by one developer running pytest locally.

## 10. Task status against the supplied brief

| Task | Status |
|---|---|
| 1. Repository inventory | **Complete.** `docs/IMPLEMENTATION_INVENTORY.md` |
| 2. Canonical records and provenance | **Partially present.** CSV-level provenance, timezone status, and source-file identity exist. No database, so no migration, no API, and no schema layer. |
| 3. Completeness and confirmation | **Not built.** No implementation. |
| 4. FIT audit and provenance | **Substantially complete.** `docs/FIT_DATA_AUDIT.md`; GPS deliberately excluded, so lap/session GPS provenance is not retained by policy. |
| 5. Strength structures | **Not built.** No schema, no importer, no UI. |
| 6. Consent-gated recovery | **Not built.** No auth, no consent model. |
| 7. Versioned load calculations | **Not built.** |
| 8. Training-control states | **Not built.** |
| 9. Provisional labelling | **Partially complete.** `docs/METRIC_LABELING.md`; dashboard edits local-only. |
| 10. Weather enrichment boundary | **Not built.** Weather remains **blocked**: no usable location or consent state. |
| 11. Weather analysis | **Not built.** Correctly has no output without matched observations. |
| 12. Verification suite | **This report.** Limited to what the repository can run. |

**Weather remains blocked.** There is no usable GPS/location state and no consent
model, so no weather provider is called and no weather record is created.

**The 26 July timestamp remains unresolved**, as a confirmation-required item
rather than a silent correction.
