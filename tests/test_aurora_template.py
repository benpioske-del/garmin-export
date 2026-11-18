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
import os

import pytest

import garmin_server as G

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(HERE, "flow_outputs", "aurora_dashboard.html")


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
    """Nineteen run charts plus the split chart; losing them was the regression."""
    assert template.count('class="chartbox"') == 23
    for canvas in ("split", "load", "weekly", "monthly", "cumulative", "dist",
                   "pacehr", "tss", "calories", "hrmax", "ascentpace",
                   "cadence", "elevation", "fit", "bubble", "fade",
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


def test_sync_reports_a_missing_token_instead_of_a_bare_status(template):
    """A stale ?tk= used to surface as 'Sync failed: HTTP 403'."""
    assert "dashboard token missing" in template


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
