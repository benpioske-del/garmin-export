# Running it from cmd

Everything built in this repository is reachable through one entry point.
There is no server to start and no service to install.

## The short version

```
trainloop.cmd
```

Run that with no arguments and it prints where things stand. That is the
command to use when you just want to know whether things are working.

If a command produces output you want to read, `status` and `doctor` will
pause before closing so a double-click does not flash past.

## First run

The database is deliberately **not** committed. It is built from your FIT
files, so a fresh clone starts with nothing and fills itself in:

```
trainloop.cmd bootstrap
```

That applies the six migrations and imports every `*.fit` in your FIT
directory. On a fresh database it takes a minute or two. It is safe to run
again: a second run reports the files as unchanged and inserts nothing.

Verify:

```
trainloop.cmd status
```

Expected on a healthy machine:

```
FIT files on disk    : 69
  activities in database: 69
  open review items     : 1
```

If `activities in database` is lower than `FIT files on disk`, run
`bootstrap`. If it is higher, something outside the importer wrote to the
database and you should look before trusting the numbers.

## Everyday commands

| Command | What it does |
| --- | --- |
| `trainloop.cmd` or `trainloop.cmd status` | Counts, migrations, and anything needing attention |
| `trainloop.cmd doctor` | Checks Python, sqlite3, fitparse, FIT directory, and that the database is gitignored |
| `trainloop.cmd bootstrap` | Migrations plus full import. Safe to re-run |
| `trainloop.cmd migrate` | Applies pending migrations only |
| `trainloop.cmd import` | Re-reads FIT files and reports inserted/updated/unchanged |
| `trainloop.cmd audit` | Per-file FIT parse report with hashes, no coordinates |
| `trainloop.cmd load` | 7/14/28-day training load table |
| `trainloop.cmd recommend` | Conservative training-control state |
| `trainloop.cmd strength --set ...` | Records a strength session and suggests the next session |
| `trainloop.cmd test` | Runs the whole test suite |
| `trainloop.cmd publish` | Regenerates `garmin_export.csv` from the database |

## Two values you have to supply

The system will not guess either of these, because a wrong value produces
confident nonsense rather than an obvious error.

**Maximum heart rate.** Running load and recommendations are unavailable
until you set it. Pass it per command:

```
trainloop.cmd load --hr-max 185
```

Or add it once to `profile.json`:

```json
{ "hr_max": 185 }
```

It is never estimated from your age.

**UTC offset.** Your recorded start times are in UTC. The athlete confirmed US
Central on 2026-11-07, so every activity now has a confirmed local date
(`timezone_source=confirmed_offset`) and the `timezone_uncertain` reviews are
closed. The remaining open review is the calendar gap (2026-06-26 to
2026-07-05), which does not block recent-state advice.

The current refusal is a different one, and an honest one:

```
state: data_insufficient
reasons:
  - only 1 training days with runs in 7 days, need 3
```

The acute window holds one run day (2026-11-06); the method needs three to
compare against the chronic window. That clears as more runs are recorded.

## What `status` will keep telling you

```text
needs attention:
  - 1 review item open, none in the last 28 days -> does not block a recommendation
```

That is the honest state, not a bug.

## Recording strength

Set format is `Exercise,reps,load_kg,RPE`, repeated for each set:

```
trainloop.cmd strength --at 2026-09-25T18:00:00Z ^
  --set "Back Squat,5,100,7" --set "Back Squat,5,100,7" ^
  --set "Romanian Deadlift,8,60,7"
```

Progression is reported **per exercise**. A 5-rep squat and an 8-rep deadlift
are different progressions, so they are never compared against each other.

## If something looks wrong

```
trainloop.cmd doctor
```

This is the first thing to run. It reports problems and notes separately, and
distinguishes "broken" from "not configured yet".

`doctor` needs `git` only to confirm the database is gitignored. On this
machine `git` is not on `PATH`; `doctor` finds the GitHub Desktop copy
automatically. If neither is found it says so and skips that one check rather
than reporting a false problem. Set `GIT_TRAINLOOP` to point at a specific
`git.exe` if you want to override the search.

## Environment

- `TRAINLOOP_DB` overrides the database location.
- `FIT_PATTERN` overrides which files are imported.
- `GIT_TRAINLOOP` overrides git discovery.

## A note on the database

`trainloop.db` is gitignored on purpose. Your activity data and health-adjacent
fields are local. Nothing in this repository publishes them, and the
coordination columns were removed from the audit output entirely. See
`docs/PRIVACY_INCIDENT.md` for what went wrong before and what changed.
