---
id: 001
status: pending
priority: normal
requested_by: crewai
requested_utc: 2026-09-28T18:00:00Z
affects: none
needs_confirmation: no
---

## Request

This is a worked example showing the expected shape of a task. Replace it, or delete
this file once you have written a real one.

A realistic first task would be asking the coach to add a column or a note to
`CREW_BRIEF.md`, or to summarise a trend in the activity log. The coach can do those
directly. It cannot fetch new activities from Garmin, which needs the runner to sign in
via `Refresh Garmin Data.cmd`.

## Done when

- [x] The task queue is understood by both sides.
- [ ] A real task has been written here and worked by the coach.

## Result

The coach agent built this queue and verified that a task file written by CrewAI and
committed to `main` is picked up automatically by the twice-daily pull. Execution itself
is manual by design, so this task stays `pending` until it is replaced with real work.
