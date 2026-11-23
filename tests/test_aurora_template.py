"""Regression tests for the committed Aurora dashboard template.

The dashboard is generated outside this repository and then committed under
``flow_outputs/``. A redesign once replaced it with a static snapshot that
dropped Garmin sync, the nutrition hook and the analysis charts, while the
server kept injecting a bootstrap that expected those hooks -- so the page
rendered stale data and the live script threw partway through.

These tests pin the contract between the template and
``garmin_server.AURORA_LIVE_SCRIPT``. They are deliberately about markers, not
pixels: a new visual design is welcome as long as the features survive.
"""

import io
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

import garmin_server as G

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(HERE, "flow_outputs", "aurora_dashboard.html")
CONTEXT = os.path.join(HERE, "flow_outputs", "run_context.json")


@pytest.fixture(scope="module")
def template():
    with io.open(TEMPLATE, encoding="utf-8") as fh:
        return fh.read()


def test_template_is_committed_and_not_empty(template):
    assert len(template) > 20000
    assert template.lstrip().startswith("<!DOCTYPE html>")


def test_template_has_no_unfilled_placeholders(template):
    """The build injects both data snapshots; a leftover token means it didn't."""
    assert "__RAW_" not in template
    assert "const rawMeta=" in template
    assert "const rawSplits=" in template


def test_template_is_not_a_static_snapshot(template):
    """The pure-static rewrite used ``const raw=`` and no live hooks."""
    assert "const raw=" not in template
    assert "syncGarmin" in template
    assert 'fetch("/sync"' in template


@pytest.mark.parametrize("marker", [
    "const SUMMARY=",
    "const COACH=",
    "const NUTRITION=",
    "const LIFTS=",
    "function render",
    "function show",
    "function navigate",
    "function importCSV",
    "function showNutritionHook",
    "function normalizeRun",
    "function drawAnalysis",
    "function heatmap",
    "function chartOrEmpty",
])
def test_template_defines_the_globals_the_bootstrap_needs(template, marker):
    """The static rewrite omitted COACH, so the injected script threw."""
    assert marker in template


def test_bootstrap_global_references_are_defined_by_the_template(template):
    """Every bare global the bootstrap touches must exist in the template."""
    for name in ("COACH", "SUMMARY", "RUNS", "NUTRITION", "render",
                 "show", "navigate", "importCSV", "showNutritionHook"):
        assert name in G.AURORA_LIVE_SCRIPT, name
        assert name in template, name


def test_bootstrap_dom_targets_exist_in_template(template):
    """paintSignal looks for ``#app .card.signal``; the hook lives at an id."""
    assert "#app .card.signal" in G.AURORA_LIVE_SCRIPT
    assert ',"signal")' in template
    assert 'id="nutrition-hook"' in template


def test_analysis_keeps_all_chart_slots(template):
    """Every run chart plus the split and fuel charts; losing one is the regression."""
    assert template.count('class="chartbox"') == 24
    for canvas in ("split", "load", "weekly", "monthly", "cumulative", "dist",
                   "pacehr", "tss", "calories", "hrmax", "ascentpace",
                   "cadence", "elevation", "fit", "bubble", "fade", "fuelfade",
                   "pacedist", "best5k", "latesplits", "gaps", "monthruns",
                   "bodyweight", "e1rm"):
        assert 'id="%s"' % canvas in template, canvas


def test_charts_draw_synchronously(template):
    """A rAF wrapper silently skipped every chart in a hidden tab."""
    assert "requestAnimationFrame(function" not in template
    assert "drawAnalysis()" in template


def test_quick_log_forms_bind_inline(template):
    """Listeners attached before render() never saw the forms it creates."""
    assert 'id="runform"' in template
    assert 'onsubmit="saveRun(event)"' in template
    assert 'id="liftform"' in template
    assert 'onsubmit="saveLift(event)"' in template


def test_quick_log_persists_on_the_server(template):
    """The old form wrote only to localStorage and vanished on reload."""
    assert 'fetch("/api/runs"' in template
    assert "aurora_last_seen_run" not in template
    assert "Quick logs stay in this browser" not in template


def test_manual_entries_are_labelled_not_presented_as_device_runs(template):
    assert "manual entry" in template
    assert 'manual: a.source_system === "manual"' in G.AURORA_LIVE_SCRIPT
    # normalizeRun() rebuilds each run object, so it must carry the flag or the
    # label is lost on the next render.
    assert "manual:r.manual===true" in template


def test_in_run_fuel_survives_the_normalize_copy(template):
    """normalizeRun() rebuilds every run, so the fuel summary must be carried."""
    assert "activityId:r.activityId||null" in template
    assert "fuel:r.fuel||null" in template
    assert "fuel: a.fuel || null" in G.AURORA_LIVE_SCRIPT
    assert "activityId: a.activity_id || null" in G.AURORA_LIVE_SCRIPT


def test_fade_points_survive_the_live_and_normalize_copies(template):
    """Aurora rebuilds every run; the canonical fade point must ride along."""
    assert "fadePoint:r.fadePoint||null" in template
    assert "fadePoint: a.fadePoint || null" in G.AURORA_LIVE_SCRIPT
    assert "var p=r&&r.fadePoint;" in template
    assert "window.FADE_ANALYSIS = payload.fade_analysis || null" \
        in G.AURORA_LIVE_SCRIPT
    assert 'id="fadeanalysis"' in template
    assert "Fade intersections" in template


def test_fuel_editor_posts_to_the_server_and_shows_fade(template):
    """The recovered intake must be editable, not read-only."""
    assert 'fetch("/api/fuel"' in template
    assert "function fuelSave" in template
    assert "function fuelClear" in template
    assert 'id="worstfade"' in template
    assert "Fuel &amp; fade" in template


def test_manual_runs_are_editable_with_fuel_in_one_form(template):
    """Quick log and edit share one form, so fuel goes in with the run."""
    assert "function log(editDate)" in template
    assert 'id="fuel-rows-log"' in template
    assert 'data-editing=' in template
    assert 'data-had-fuel=' in template
    # Single quotes inside the single-quoted JS string are HTML-encoded, not
    # backslash-escaped; a stray quote here used to kill the whole script.
    assert 'onclick="fuelAddRow(&apos;log&apos;)"' in template
    assert "payload.fuel={events:events,note:note" in template
    assert "payload.fuel={delete:true}" in template
    assert 'h.indexOf("#log/run/")===0?log(' in template
    assert "Edit run</a>" in template
    # The edit form needs the athlete-reported RPE back from the API.
    assert "rpe:r.rpe==null?null:Number(r.rpe)" in template
    assert "rpe: a.rpe == null ? null : Number(a.rpe)" in G.AURORA_LIVE_SCRIPT


def test_sync_reports_a_missing_token_instead_of_a_bare_status(template):
    """A stale ?tk= used to surface as 'Sync failed: HTTP 403'."""
    assert "dashboard token missing" in template


def test_sync_keeps_a_persistent_status_line(template):
    """A 2.5 s toast cannot cover a 15-90 s sync.

    The button silently returned to its old label, so a finished sync looked
    like nothing had happened and the athlete pressed it again.
    """
    assert 'id="syncstatus"' in template
    assert "function setSyncStatus" in template
    assert "setSyncStatus(" in template
    assert "Syncing - this usually takes" in template
    assert "Sync failed: " in template


def test_sync_status_names_the_run_count(template):
    """The success line must say what the sync did, not just "complete"."""
    assert "new_runs" in template
    assert '"Synced "' in template
    assert 'bits.push(SUMMARY.total_runs+" total")' in template


def test_nutrition_hook_buttons_do_not_terminate_the_script_early():
    """onclick="f('url')" inside a single-quoted JS string is a syntax error.

    A single stray quote here broke the whole injected bootstrap: the page
    stayed on the committed SNAPSHOT (72 runs, ACWR "unavailable") while the
    separate template script kept the Sync button working, so a sync looked
    like a no-op. The quotes are HTML-encoded instead of backslash-escaped.
    """
    script = G.AURORA_LIVE_SCRIPT
    assert "copyNutritionHook(&apos;url&apos;)" in script
    assert "copyNutritionHook(&apos;token&apos;)" in script
    assert "copyNutritionHook('url')" not in script
    assert "copyNutritionHook('token')" not in script


def test_injected_live_script_is_valid_javascript():
    """Parse the injected script with node when it is available.

    The marker tests cannot see a syntax error, and one bad quote disables
    every live feature at once. GitHub's runners ship node, so CI catches it;
    a machine without node skips rather than fails.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed; JavaScript syntax check unavailable")
    body = G.AURORA_LIVE_SCRIPT.split("<script>", 1)[1]
    body = body.rsplit("</script>", 1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "live.js")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        proc = subprocess.run([node, "--check", path],
                              capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_importer_sends_the_shape_the_server_parses():
    """JSON backups must post ``json``; CSV exports must post ``csv``."""
    assert "{ json: text }" in G.AURORA_LIVE_SCRIPT
    assert "{ csv: text }" in G.AURORA_LIVE_SCRIPT


def test_hook_setup_does_not_recommend_sideloading():
    """The athlete only installs from a store; no GitHub-APK path."""
    assert "Play Store" in G.AURORA_LIVE_SCRIPT
    assert "GitHub releases" not in G.AURORA_LIVE_SCRIPT


def test_injection_adds_the_marker_and_vendors_chart_js(template):
    out = G.inject_aurora_live(template.encode("utf-8")).decode("utf-8")
    assert G.AURORA_LIVE_MARK in out
    assert G.CHART_CDN not in out
    assert "/vendor/chart.umd.min.js" in out


def test_injection_is_idempotent(template):
    once = G.inject_aurora_live(template.encode("utf-8"))
    twice = G.inject_aurora_live(once)
    assert once == twice
    assert twice.decode("utf-8").count(G.AURORA_LIVE_MARK) == 1


def test_run_context_is_tracked_and_privacy_filtered():
    """Garmin-derived context is tracked because the source dashboard is local-only.

    Every Garmin run gets a start time, Lap Splits and archived weather values.
    Raw coordinates and the Classic place-name default must never reach the
    public repo, even though the source dashboard contains both.
    """
    with io.open(CONTEXT, encoding="utf-8") as fh:
        data = json.load(fh)
    runs = data["runs"]
    assert len(runs) >= 75
    assert len(data["byActivity"]) == len(runs)
    for date, item in runs.items():
        assert item["activityId"].startswith("garmin:"), date
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:00", item["startLocal"]), date
        assert item["tempF"] is not None, date
        assert item["weather"].get("tempF") is not None, date
        assert item["splits"], date
    hot = runs["2026-09-09"]
    assert hot["tempF"] == 80  # Classic's recorded athlete/heat value wins
    assert hot["weather"]["windMph"] == 14
    assert hot["comments"]
    raw = json.dumps(data)
    for key in ('"lat"', '"lon"', '"latitude"', '"longitude"'):
        assert key not in raw
    assert "Chaska" not in raw


def test_template_embeds_the_tracked_context_verbatim(template):
    """The snapshot must work without the server as well as with it."""
    with io.open(CONTEXT, encoding="utf-8") as fh:
        data = json.load(fh)
    lines = [ln for ln in template.splitlines()
             if ln.startswith("const RUN_CONTEXT=")]
    assert len(lines) == 1
    inline = lines[0][len("const RUN_CONTEXT="):].rstrip(";")
    assert json.loads(inline) == data
    # A literal angle bracket in a comment could close the <script> element.
    assert "<" not in inline and ">" not in inline


def test_run_detail_restores_location_weather_and_comments(template):
    """The Classic run report fields belong on the detail page only."""
    for marker in (
        "function weatherCard(r)", "function commentsCard(r)",
        "+weatherCard(r)", "+commentsCard(r)",
        "Location &amp; weather", "Weather-adjusted time",
        "function contextFor(r)", "esc(c.location", "commentHtml(n)",
        "Weather at start:", "Start location",
    ):
        assert marker in template, marker


def test_garmin_start_time_and_splits_feed_the_report(template):
    """The report uses the Garmin CSV, not Classic's partial weather table."""
    for marker in (
        "function contextSplits(r)", "RUN_CONTEXT.byActivity",
        "var key=r&&r.activityId", "c.startLocal", "Start time (Garmin)",
        "splits=(contextSplits(r)||[]).slice()",
        "else{splits=(contextSplits(r)||[]).slice()}",
    ):
        assert marker in template, marker
    # No stale hard-coded "we have no splits" wording in the detail card.
    assert "This activity source did not provide lap splits." in template
    assert "Splits not recorded" in template  # only for a truly empty run


def test_weather_adjusted_time_uses_recorded_temperature_only(template):
    """No temperature means no number; the Classic heat rule is descriptive."""
    assert "function adjustedSeconds(r)" in template
    assert "if(!c||c.tempF==null)return null" in template
    assert "(t>50?(t-50)*0.2:0)" in template
    assert "raw/(1+" in template
    assert 'adj==null?"not recorded"' in template
    assert "Illustrative only" in template
    assert "does not predict performance" in template
    assert "no live weather lookup" in template


def test_pace_is_shown_as_minutes_seconds(template):
    """Chart axes and fade cells used to print raw seconds per mile."""
    for marker in (
        "function mss(n)", "function paceTick(v){return mss(v)}",
        "function paceAxis(title)", "callback:paceTick",
        "Pace m:ss/mi", "pace m:ss/mi", "m:ss/mi fade",
        "Fade m:ss/mi",
    ):
        assert marker in template, marker
    for stale in ("label:\"pace sec/mi\"", "Pace s/mi", "Seconds per mile",
                  ">s/mi fade", "Fade s/mi"):
        assert stale not in template, stale


def test_template_script_is_valid_javascript(template):
    """A broken quote in the new report cards would kill the whole page."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed; JavaScript syntax check unavailable")
    match = re.search(r"<script>\s*(const SUMMARY=.*?)</script>", template, re.S)
    assert match, "main inline script not found"
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "aurora.js")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(match.group(1))
        proc = subprocess.run([node, "--check", path],
                              capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
