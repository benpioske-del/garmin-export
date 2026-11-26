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


def test_estimated_load_is_labelled_and_survives_the_normalize_copy(template):
    """A computed HR/duration load must never be presented as Garmin TSS."""
    assert "Estimated HR-based load" in template
    assert "Not Garmin TSS" in template
    assert "never presented as Garmin TSS" in G.AURORA_LIVE_SCRIPT
    assert ("estimatedLoad:r.estimatedLoad==null?null:Number(r.estimatedLoad)"
            in template)
    assert ("estimatedLoad: a.estimated_run_load == null ? null"
            in G.AURORA_LIVE_SCRIPT)
    assert "var loads=RUNS.filter(function(r){return r.estimatedLoad!=null})" \
        in template


def test_fade_onset_is_shown_in_the_fuel_card_and_worst_table(template):
    assert "function fadeOnsetHtml(p)" in template
    assert "fadeOnsetHtml(r.fadePoint)" in template
    assert "estimated onset &middot; mile" in template
    assert "<th>Est. onset</th>" in template
    assert "onsetText=onset?" in template


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


def test_nutrition_setup_links_the_exact_play_store_app():
    """Two similarly named bridge apps exist; link the one we verified.

    The old local-host hint also referred to a laptop tunnel window that no
    longer exists now that the dashboard runs in the cloud.
    """
    script = G.AURORA_LIVE_SCRIPT
    assert ("href='https://play.google.com/store/apps/details?"
            "id=com.hcwebhook.app'") in script
    assert "start-dashboard window" not in script
    assert "Open the public dashboard URL on your phone" in script


def test_signal_heading_uses_the_api_state():
    """A confirmation refusal is not the same refusal as missing history."""
    script = G.AURORA_LIVE_SCRIPT
    assert "String(c.state || (refused ? \"data_insufficient\" : \"unavailable\"))" in script
    assert 'c.refused ? "DATA INSUFFICIENT"' not in script
    assert '(refused ? "refused" : "live") + " /api/coaching<' in script
    # The heading must still carry refusal styling, never advice styling.
    assert '(refused ? "warn" : "good")' in script


def test_paint_signal_uses_the_true_refusal_state():
    """Exercise the injected card with node and the real paint function."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed; JavaScript behaviour check unavailable")
    match = re.search(r"(?m)^  function paintSignal\(\) \{",
                      G.AURORA_LIVE_SCRIPT)
    assert match, "paintSignal not found in the live script"
    start = G.AURORA_LIVE_SCRIPT.index("{", match.start())
    depth = 0
    end = None
    for i in range(start, len(G.AURORA_LIVE_SCRIPT)):
        if G.AURORA_LIVE_SCRIPT[i] == "{":
            depth += 1
        elif G.AURORA_LIVE_SCRIPT[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end, "unbalanced paintSignal"
    function = G.AURORA_LIVE_SCRIPT[match.start():end]
    harness = """
var card = { innerHTML: "STATIC CARD" };
var document = { querySelector: function(){ return card; } };
var LIVE = { coaching: null, load: null };
function esc(s){ return String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;"); }
function acwr(load){
  var w = (load && load.windows) || {};
  var acute = (w["7d"]||{}).combined_load, chronic = (w["28d"]||{}).combined_load;
  return (isFinite(acute) && isFinite(chronic) && chronic > 0)
    ? acute / (chronic / 4) : null;
}
""" + function + """
LIVE.coaching = { state: "confirmation_required", refused: true,
  blocking_conditions: ["5 recent activities are awaiting confirmation"] };
LIVE.load = { windows: { "7d": { combined_load: 870.7 },
                          "28d": { combined_load: 2719.2 } } };
paintSignal();
if (card.innerHTML.indexOf("CONFIRMATION REQUIRED") < 0)
  throw new Error("confirmation state was masked: " + card.innerHTML);
if (card.innerHTML.indexOf("DATA INSUFFICIENT") >= 0)
  throw new Error("wrong refusal heading");
if (card.innerHTML.indexOf("awaiting confirmation") < 0
    || card.innerHTML.indexOf('class="warn"') < 0
    || card.innerHTML.indexOf("refused /api/coaching") < 0)
  throw new Error("refusal detail lost: " + card.innerHTML);
LIVE.coaching = { state: "data_insufficient", refused: true,
  blocking_conditions: ["only 2 training days with runs in 7 days, need 3"] };
paintSignal();
if (card.innerHTML.indexOf("DATA INSUFFICIENT") < 0)
  throw new Error("data refusal heading lost");
LIVE.coaching = { state: "recover", refused: false, blocking_conditions: [] };
paintSignal();
if (card.innerHTML.indexOf("RECOVER") < 0 || card.innerHTML.indexOf('class="good"') < 0
    || card.innerHTML.indexOf("live /api/coaching") < 0)
  throw new Error("advisory state changed: " + card.innerHTML);
card.innerHTML = "STATIC CARD";
LIVE.coaching = null;
paintSignal();
if (card.innerHTML !== "STATIC CARD")
  throw new Error("static card was overwritten without coaching data");
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "signal.js")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(harness)
        proc = subprocess.run([node, path], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout


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


def test_run_score_adds_a_number_and_reason_to_the_letter(template):
    """A letter alone hid why one run scored differently from another."""
    for marker in (
        "function runScore(r)", "function scoreCard(r)", "+scoreCard(r)",
        "score>=90?\"A\":score>=78?\"B\"", "Math.max(1,Math.min(100,Math.round(score)))",
        "Descriptive only: hills, effort, weather and fatigue",
        "<th>Score</th>", "s.grade+' &middot; '+s.score+'/100",
        "Pace was ", "than your recent ", "no lap splits, so consistency was not scored",
    ):
        assert marker in template, marker
    # The old hero promised a score but displayed none.
    assert "Score computed from pace, heart rate and consistency" not in template


def test_lifting_has_simple_and_advanced_modes_with_prs(template):
    """Simple is one tap plus effort; Advanced keeps every set detail."""
    for marker in (
        "let LIFT_MODE=", "aurora_lift_mode", "function setLiftMode(m)",
        "function liftForm()", "function liftPrFor(s,best)", "function liftPrList(s,index)",
        "setLiftMode(&apos;'+m+'&apos;)", "name=\"effort\"",
        "value=\"easy\"", "value=\"medium\"", "value=\"hard\"",
        "name=\"sets\"", "name=\"rpe\"", "name=\"rest\"", "name=\"notes\"",
        "name=\"prs\"", ">PR '+esc(p)+'", "PR(s) recorded",
    ):
        assert marker in template, marker
    # The form id and inline submit binding are shared by both modes.
    assert 'id="liftform"' in template
    assert 'onsubmit="saveLift(event)"' in template


def _function_source(template, name):
    """Extract one top-level function by brace matching, not by line number."""
    m = re.search(r"(?m)^function " + re.escape(name) + r"\(", template)
    assert m, name
    start = template.index("{", m.start())
    depth = 0
    for i in range(start, len(template)):
        if template[i] == "{":
            depth += 1
        elif template[i] == "}":
            depth -= 1
            if depth == 0:
                return template[m.start():i + 1]
    raise AssertionError("unbalanced function " + name)


def test_run_score_and_lift_modes_behave_in_javascript(template):
    """Exercise the new logic with node, using the committed snapshot."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed; JavaScript behaviour check unavailable")

    stubs = """
var store={};
var localStorage={getItem:function(k){return Object.prototype.hasOwnProperty.call(store,k)?store[k]:null},
                  setItem:function(k,v){store[k]=String(v)}};
var location={search:"",hash:"#home"};
var document={getElementById:function(){return null}};
function render(){}
var window={};
"""
    lines = [ln for ln in template.splitlines() if ln.startswith((
        "const SUMMARY=", "const COACH=", "const RUN_CONTEXT=",
        "const NUTRITION=", "const LIFTS=", "let LIFT_MODE=",
    ))]
    assert len(lines) == 6
    blocks = []
    for name in ("rawMeta", "rawSplits"):
        m = re.search(r"const " + name + r"=`(.*?)`;", template, re.S)
        assert m, name
        blocks.append("const " + name + "=`" + m.group(1) + "`;")
    names = (
        "esc", "paceSec", "pstr", "sec", "band", "card", "commentHtml",
        "contextFor", "contextSplits", "normalizeRun", "fadePct", "runScore",
        "scoreCard", "liftE1rm", "liftBestBefore", "liftPrFor", "liftPrList",
        "setLiftMode", "liftModeButton", "liftRow", "liftForm", "lift", "saveLift",
        "toast", "go",
    )
    iife = re.search(r"const RUNS=\[\];\n\(function\(\)\{.*?\n\}\)\(\);", template, re.S)
    assert iife
    harness = "\n".join(
        [stubs] + lines + blocks + [_function_source(template, n) for n in names]
        + [iife.group(0)] + ["""
var scores=RUNS.map(function(r){return runScore(r)});
if(scores.length<70)throw new Error("snapshot not loaded");
scores.forEach(function(s){
  if(!(s.score>=1&&s.score<=100)||!/^[A-F]$/.test(s.grade)||!s.reason)
    throw new Error("invalid score "+JSON.stringify(s));
});
if(new Set(scores.map(function(s){return s.score})).size<10)
  throw new Error("score is not discriminating between runs");
var card=scoreCard(RUNS[RUNS.length-1]);
if(card.indexOf("/100")<0||card.indexOf("Descriptive only")<0)
  throw new Error("score card missing number or reason");
LIFT_MODE="simple";
var simple=liftForm();
if(simple.indexOf('name="effort"')<0||simple.indexOf('name="prs"')<0||simple.indexOf('name="reps"')>=0)
  throw new Error("simple form wrong");
LIFT_MODE="advanced";
var advanced=liftForm();
["ex","weight","sets","reps","rpe","rest","notes","prs"].forEach(function(f){
  if(advanced.indexOf('name="'+f+'"')<0)throw new Error("advanced missing "+f);
});
function submit(v){global.FormData=function(){return {get:function(k){return v[k]==null?null:v[k]}}};
  saveLift({preventDefault:function(){},target:{}})}
LIFTS.length=0;
submit({mode:"advanced",bw:"180",ex:"Bench press",weight:"135",sets:"3",reps:"5",rpe:"",rest:"",notes:"",prs:""});
submit({mode:"advanced",bw:"",ex:"Bench press",weight:"185",sets:"3",reps:"5",rpe:"8",rest:"120",notes:"ok",prs:""});
if(!LIFTS[1].autoPr||LIFTS[1].autoPr.indexOf("Bench press e1RM")<0)throw new Error("PR not detected");
if(LIFTS[0].rpe!==null||LIFTS[1].restSec!==120)throw new Error("blank/zero handling wrong");
LIFT_MODE="simple";
submit({mode:"simple",bw:"180",effort:"hard",prs:"Squat 225 x 3"});
if(LIFTS[2].prs.length!==1||LIFTS[2].weight!==null)throw new Error("simple record wrong");
if(lift().indexOf("PR Squat 225 x 3")<0)throw new Error("PR not rendered");
setLiftMode("advanced");
if(store["aurora_lift_mode"]!=="advanced")throw new Error("mode not persisted");
"""]
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "features.js")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(harness)
        proc = subprocess.run([node, path], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout


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
