"""Tests for the dashboard data-source contract.

The point of these is negative: they must fail when the canonical panel starts
reading the private journal, or when inline data is added without being
classified. A contract test that only asserts the happy path proves nothing.

Nothing here touches the real dashboard. It is gitignored and private, so the
suite runs entirely on synthetic documents; the one test that reads the real
file skips when it is absent.
"""

import io
import os

import pytest

import dashboard_contract as C


def _seed_block():
    """Declarations for every classified name, so the fixture is realistic.

    Built from DECL_KINDS rather than hand-listed: a document with fewer
    top-level declarations than the classification is exactly what the stale
    check is for, so a partial fixture would fail for the wrong reason.
    """
    out = []
    for name in sorted(C.DECL_KINDS):
        kw = "let" if name.startswith("custom") else "const"
        literal = "{}" if name in ("charts", "__dashRenderErrors", "tempCache",
                                   "wxCache") else "[]"
        out.append("%s %s = %s;" % (kw, name, literal))
    return "\n".join(out)


def _document(region_body="", before="", seed=None):
    return (
        "<!doctype html><html><body>\n<script>\n"
        + (seed if seed is not None else _seed_block())
        + "\nwindow.DASHBOARD_SOURCES = {canonical:{}, localOnly:["
        + repr(list(C.LOCAL_ONLY))
        + "]};\n</script>\n"
        + before
        + '<div id="apiPanel">\n<script>\n'
        + "apiGet('/api/activities').then(renderActivities, onErr);\n"
          "apiGet('/api/load').then(renderLoad, onErr);\n"
          "apiGet('/api/coaching').then(renderCoaching, onErr);\n"
          "function fail(panelId, msg) { el(panelId).textContent = 'Unavailable'; }\n"
        + region_body
        + "\n</script>\n</div>\n</body></html>"
    )


GOOD = _document()


def _with(*replacements):
    """Apply flat (old, new, old, new, ...) string swaps to the fixture."""
    assert len(replacements) % 2 == 0, "need old/new pairs"
    out = GOOD
    for i in range(0, len(replacements), 2):
        old, new = replacements[i], replacements[i + 1]
        assert old in out, "fixture edit target missing: %r" % old
        out = out.replace(old, new, 1)
    return out


class TestHappyPath:
    def test_clean_document_passes(self):
        r = C.audit_dashboard(GOOD)
        assert r["ok"], r["problems"]
        assert r["problems"] == []

    def test_all_three_surfaces_found(self):
        r = C.audit_dashboard(GOOD)
        assert [s["surface"] for s in r["surfaces"]] == [
            "activities", "load", "coaching"]
        assert all(s["fetched"] for s in r["surfaces"])

    def test_declarations_are_classified(self):
        r = C.audit_dashboard(GOOD)
        assert r["undeclared"] == []
        assert r["stale"] == []

    def test_surfaces_match_the_live_routes(self):
        assert C.CANONICAL_SURFACES == (
            ("activities", "/api/activities"),
            ("load", "/api/load"),
            ("coaching", "/api/coaching"),
        )


class TestMissingStructure:
    def test_no_panel_fails(self):
        r = C.audit_dashboard("<html><body>nothing here</body></html>")
        assert not r["ok"]
        assert any("no canonical panel" in p for p in r["problems"])

    def test_missing_registry_fails(self):
        r = C.audit_dashboard(
            _with("window.DASHBOARD_SOURCES", "window.SOMETHING_ELSE"))
        assert not r["ok"]
        assert any(C.REGISTRY_KEY in p for p in r["problems"])

    @pytest.mark.parametrize("route", ["/api/activities", "/api/load",
                                       "/api/coaching"])
    def test_missing_surface_fetch_fails(self, route):
        r = C.audit_dashboard(_with("apiGet('%s')" % route, "/* gone */"))
        assert not r["ok"]
        assert any(route in p for p in r["problems"])

    @pytest.mark.parametrize("route,renderer", [
        ("/api/activities", "renderActivities"),
        ("/api/load", "renderLoad"),
        ("/api/coaching", "renderCoaching"),
    ])
    def test_fetch_without_rejection_handler_fails(self, route, renderer):
        # Fetched and chained, but with a single .then argument: a failed
        # request leaves the card blank instead of reporting anything.
        r = C.audit_dashboard(_with(
            "apiGet('%s').then(%s, onErr)" % (route, renderer),
            "apiGet('%s').then(%s)" % (route, renderer)))
        assert not r["ok"]
        assert route in r["unhandled"]
        assert any("no rejection handler" in p for p in r["problems"])

    @pytest.mark.parametrize("route,renderer", [
        ("/api/activities", "renderActivities"),
        ("/api/load", "renderLoad"),
        ("/api/coaching", "renderCoaching"),
    ])
    def test_detached_call_is_not_treated_as_handled(self, route, renderer):
        # The .then must be chained onto this call. Scanning forward for any
        # later .then( let one surface claim the next surface's handler.
        r = C.audit_dashboard(_with(
            "apiGet('%s').then(%s, onErr)" % (route, renderer),
            "apiGet('%s')" % route))
        assert not r["ok"]

    def test_missing_failure_renderer_fails(self):
        r = C.audit_dashboard(
            _with("function fail(panelId, msg) { el(panelId).textContent = 'Unavailable'; }",
                  ""))
        assert not r["ok"]
        assert any("no failure renderer" in p for p in r["problems"])

    def test_failure_renderer_that_writes_nothing_fails(self):
        r = C.audit_dashboard(
            _with("function fail(panelId, msg) { el(panelId).textContent = 'Unavailable'; }",
                  "function fail(panelId, msg) { return msg; }"))
        assert not r["ok"]
        assert any("visible text" in p for p in r["problems"])

    def test_fetch_outside_the_panel_does_not_count(self):
        # A fetch earlier in the document cannot stand in for the panel doing it.
        html = _document(before="<script>apiGet('/api/load');</script>")
        html = html.replace("apiGet('/api/load').then(renderLoad, onErr);", "")
        r = C.audit_dashboard(html)
        assert not r["ok"]

    def test_panel_outside_body_fails(self):
        r = C.audit_dashboard(_with("</div>\n</body></html>", "</div>"))
        assert not r["ok"]


class TestInlineDataGovernance:
    def test_undeclared_top_level_array_fails(self):
        r = C.audit_dashboard(
            _with("const AGEF_M = [];", "const AGEF_M = [];\nconst sneakyData = [];"))
        assert not r["ok"]
        assert "sneakyData" in " ".join(r["problems"])

    def test_stale_classification_fails(self):
        # Declared in DECL_KINDS but gone from the document: the map has drifted.
        r = C.audit_dashboard(_with("const baseLifts = [];\n", ""))
        assert not r["ok"]
        assert "baseLifts" in " ".join(r["problems"])

    def test_every_classified_name_has_a_kind(self):
        kinds = set(C.DECL_KINDS.values())
        assert kinds == {"athlete", "static", "scratch"}

    def test_local_only_is_exactly_the_athlete_data(self):
        assert set(C.LOCAL_ONLY) == {
            n for n, k in C.DECL_KINDS.items() if k == "athlete"}
        for expected in ("baseRuns", "baseLifts", "baseWeights", "customRuns"):
            assert expected in C.LOCAL_ONLY


class TestCanonicalPanelIndependence:
    """The substantive guarantee: the canonical panel is API-only."""

    def test_reading_the_private_journal_fails(self):
        r = C.audit_dashboard(
            _with("apiGet('/api/activities').then(renderActivities, onErr);",
                  "renderActivities(baseRuns); apiGet('/api/activities').then(renderActivities, onErr);"))
        assert not r["ok"]
        assert r["violations"] == ["baseRuns"]
        assert any("local-only" in p for p in r["problems"])

    def test_reading_base_weights_fails(self):
        r = C.audit_dashboard(
            _with("apiGet('/api/load').then(renderLoad, onErr);",
                  "renderLoad(baseWeights);"))
        assert not r["ok"]
        assert "baseWeights" in r["violations"]

    def test_multiple_violations_are_all_reported(self):
        r = C.audit_dashboard(
            _with("apiGet('/api/activities').then(renderActivities, onErr);",
                  "render(baseRuns, baseLifts, trainingLedger);"))
        assert set(r["violations"]) == {"baseRuns", "baseLifts", "trainingLedger"}

    def test_word_boundaries_are_respected(self):
        # baseRunsByDistance is a different identifier and must not trip.
        r = C.audit_dashboard(
            _with("apiGet('/api/load').then(renderLoad, onErr);",
                  "var baseRunsByDistance = 1; apiGet('/api/load').then(renderLoad, onErr);"))
        assert r["violations"] == []
        assert r["ok"], r["problems"]

    def test_journal_use_before_the_panel_is_allowed(self):
        # The legacy features may keep using the journal; only the canonical
        # panel is API-only. Deleting the journal is not the fix here.
        r = C.audit_dashboard(
            _document(before="<script>renderLegacy(baseRuns, baseLifts);</script>"))
        assert r["violations"] == []
        assert r["ok"], r["problems"]

    def test_missing_unavailable_state_fails(self):
        # A panel with no failure path invites a silent fallback later. The
        # check is structural (does the fetch have a rejection handler, does
        # the renderer write text), because matching the word "Unavailable"
        # passed even with the handler deleted.
        r = C.audit_dashboard(_with(", onErr)", ")"))
        assert not r["ok"]
        assert r["unhandled"]


class TestReport:
    def test_report_states_the_verdict(self):
        md = C.render_report(C.audit_dashboard(GOOD))
        assert "| Result | PASS |" in md
        assert "GENERATED FILE" in md

    def test_report_lists_surfaces_and_local_only(self):
        md = C.render_report(C.audit_dashboard(GOOD))
        for route, _ in C.CANONICAL_SURFACES:
            assert route in md
        assert "baseRuns" in md

    def test_report_marks_failure(self):
        md = C.render_report(C.audit_dashboard("<html></html>"))
        assert "| Result | FAIL |" in md
        assert "## Problems" in md

    def test_report_explains_why_the_journal_is_not_deleted(self):
        md = C.render_report(C.audit_dashboard(GOOD))
        assert "must not be deleted" in md


class TestRealDashboard:
    """Runs against the real file when present, skips when it is not.

    This is the only test that can catch a regression introduced by editing the
    actual dashboard, and it is expected to skip in any environment where the
    private file does not exist.
    """

    def _path(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(here, "dashboard", "index.html")

    def _read(self):
        p = self._path()
        if not os.path.exists(p):
            pytest.skip("dashboard/index.html is gitignored and not present")
        with io.open(p, encoding="utf-8") as fh:
            return fh.read()

    def test_real_dashboard_satisfies_the_contract(self):
        report = C.audit_dashboard(self._read())
        assert report["ok"], report["problems"]
        assert len(report["athletes"]) >= 19


class TestRealDashboardMutations:
    """Mutate the real document and require every regression to be caught.

    A contract check that passes on the real file proves the file is currently
    clean. It does not prove the check works. These mutations are the part that
    proves it: each one is a realistic regression, and each must fail the
    audit. Two of them exist because the first version of this audit let them
    through.
    """

    def _read(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(here, "dashboard", "index.html")
        if not os.path.exists(p):
            pytest.skip("dashboard/index.html is gitignored and not present")
        with io.open(p, encoding="utf-8") as fh:
            return fh.read()

    def _mutations(self, html):
        act = "apiGet('/api/activities').then("
        load = "apiGet('/api/load').then("
        coach = "apiGet('/api/coaching').then("
        return [
            ("panel reads baseRuns", act,
             "renderRows(baseRuns); " + act),
            ("panel reads baseWeights", load,
             "renderLoad(baseWeights); " + load),
            ("panel reads trainingLedger", coach,
             "showLedger(trainingLedger); " + coach),
            ("undeclared dataset added", "const AGEF_M = [",
             "const sneaky = [{a:1}];\nconst AGEF_M = ["),
            ("activities fetch removed", act, ""),
            ("load fetch removed", load, ""),
            ("coaching fetch removed", coach, ""),
            ("registry removed", "window.DASHBOARD_SOURCES",
             "window.SOMETHING_ELSE"),
            ("failure renderer gutted",
             "function fail(panelId, msg) {",
             "function fail() { return 0; } //"),
            ("panel removed", '<div id="apiPanel"', '<div id="gonePanel"'),
        ]

    def test_every_mutation_is_caught(self):
        html = self._read()
        base = C.audit_dashboard(html)
        if not base["ok"]:
            pytest.fail("baseline already failing: %s" % base["problems"])

        survived = []
        for label, old, new in self._mutations(html):
            if old not in html:
                continue
            mutated = html.replace(old, new, 1)
            if mutated == html:
                continue
            if C.audit_dashboard(mutated)["ok"]:
                survived.append(label)

        assert not survived, "audit failed to catch: %s" % ", ".join(survived)

    def test_all_mutations_applied(self):
        # Guards the test above: if every mutation silently stopped matching,
        # it would pass vacuously.
        html = self._read()
        applied = sum(1 for _, old, _ in self._mutations(html)
                      if old in html)
        assert applied >= 8, "only %d mutation targets still match" % applied