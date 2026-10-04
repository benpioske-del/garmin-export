"""Data-source contract for the private dashboard.

Why this module exists
----------------------
`dashboard/index.html` is gitignored because it contains hand-entered athlete
data: a 52-entry running journal with narrative notes, splits, hydration,
injury flags and coordinates, plus a body-weight series. That data is private
and must never be committed. But the file also holds every bit of the
dashboard's *logic*, and the supervisor brief process can only see what is in
git.

The result was a loop. CrewAI could not read the dashboard at all, so every
brief invented its contents -- it reported "approximately 54 inline JavaScript
arrays" in one run and 133 in the next, and it kept re-issuing
`connect-dashboard-to-data-layer` as top priority after that work was finished
and committed. Nothing the brief said about the dashboard was an observation.

So: the dashboard declares its own data sources, and this module checks that
declaration against the file and writes down the result as a tracked document.
`docs/DASHBOARD_AUDIT.md` is generated from the real file, which gives the brief
process something it can actually read, and keeps giving it an accurate answer.

What "authoritative" means here
-------------------------------
There are two different datasets in that file and conflating them is the actual
defect the brief kept circling:

* The **canonical corpus** is 58 FIT files imported into `trainloop.db`, served
  by `/api/activities`, `/api/load` and `/api/coaching`. It is the only thing
  allowed to answer "what are my activities", "what is my load" and "what
  should I do".

* The **private journal** is `baseRuns` and friends: hand-entered entries with
  subjective fields the FIT files do not contain, layered over localStorage so
  the athlete can edit them. It is a real feature with real data. It is *not*
  the canonical corpus and must never be presented as one -- deleting it would
  destroy data that exists nowhere else.

Neither is a substitute for the other. This module enforces that the canonical
panels read only from the API, and that the journal stays classified as
local-only rather than quietly becoming authoritative.

The check is deliberately structural rather than a matter of trust: if a
canonical panel ever starts reading `baseRuns`, `audit_dashboard` fails.
"""

import re
import sys

CANONICAL_SURFACES = (
    ("activities", "/api/activities"),
    ("load", "/api/load"),
    ("coaching", "/api/coaching"),
)

# Marker the dashboard must carry, and the attribute that opens the canonical
# region. Everything from that attribute to the end of the file is the region
# that is required to be API-only.
PANEL_ANCHOR = 'id="apiPanel"'
REGISTRY_KEY = "window.DASHBOARD_SOURCES"

# Top-level (column 0) declarations, classified. `athlete` holds the private
# journal, `static` holds lookup tables and constants that are not data about
# anyone, `scratch` holds caches and render bookkeeping. Any top-level
# declaration missing from this map makes the audit fail, which is the point: a
# new inline dataset cannot be added without saying what it is.
DECL_KINDS = {
    "baseLifts": "athlete",
    "baseRuns": "athlete",
    "baseWeights": "athlete",
    "customRuns": "athlete",
    "customWeights": "athlete",
    "weightEntries": "athlete",
    "liftEntries": "athlete",
    "runOverrides": "athlete",
    "splitOverrides": "athlete",
    "deletedRunKeys": "athlete",
    "savedRoutines": "athlete",
    "trainingLedger": "athlete",
    "briefLog": "athlete",
    "nutritionLog": "athlete",
    "experiments": "athlete",
    "lifeLoad": "athlete",
    "weeksData": "athlete",
    "microByDay": "athlete",
    "garminFitList": "athlete",
    "AGEF_M": "static",
    "AGEF_F": "static",
    "T5K_ANCHORS_M": "static",
    "T5K_ANCHORS_F": "static",
    "HISTORICAL_PR": "static",
    "GUARD_RAILS": "static",
    "LAB_HINTS": "static",
    "CHASKA": "static",
    "GEL_SPEC": "static",
    "charts": "scratch",
    "__dashRenderErrors": "scratch",
    "tempCache": "scratch",
    "wxCache": "scratch",
}

# The private journal. A canonical panel that reads any of these is a defect.
LOCAL_ONLY = tuple(sorted(n for n, k in DECL_KINDS.items() if k == "athlete"))

_TOP_DECL = re.compile(r"(?m)^(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*[\[{]")
_THEN = re.compile(r"\.then\s*\(")


def _match_paren(text, open_idx):
    """Index of the ')' matching the '(' at open_idx, or -1."""
    depth = 0
    for j in range(open_idx, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _call_args_after(text, needle):
    """Split the top-level arguments of the `.then(` chained onto `needle`.

    Used to tell an actual rejection handler from a hopeful `.then(render)`
    with no second argument. Matching on argument *count* rather than on the
    word "error" is deliberate: the loose version passed even with the failure
    handler deleted, because `catch` and `.catch` appear all over the panel.

    The `.then` must be chained directly onto the call. Scanning forward for
    any later `.then(` lets one surface claim the next surface's handler, which
    is how `apiGet('/api/coaching')` with no handler came to look handled.
    """
    i = text.find(needle)
    if i == -1:
        return None

    # The needle is the quoted argument, so the call's own '(' is behind it.
    open_idx = text.rfind("(", 0, i)
    if open_idx == -1:
        return None
    close_idx = _match_paren(text, open_idx)
    if close_idx == -1:
        return None

    m = _THEN.match(text, close_idx + 1)
    if not m:
        return None

    depth = 1
    args = []
    cur = []
    j = m.end()
    while j < len(text):
        ch = text[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        elif ch == "," and depth == 1:
            args.append("".join(cur))
            cur = []
            j += 1
            continue
        cur.append(ch)
        j += 1
    args.append("".join(cur))
    return args


def _block_after(text, needle):
    """Return the brace-delimited body following `needle`, or ''."""
    i = text.find(needle)
    if i == -1:
        return ""
    start = text.find("{", i)
    if start == -1:
        return ""
    depth = 0
    for j in range(start, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:j]
    return ""


def find_panel_region(html):
    """Return (region_text, problems) for the canonical API panel.

    The panel is appended last, so the region runs from the anchor to the end
    of the file. That is deliberately generous: anything in the tail is held to
    the API-only rule.
    """
    problems = []
    i = html.find(PANEL_ANCHOR)
    if i == -1:
        return "", ["no canonical panel found (expected %s)" % PANEL_ANCHOR]
    region = html[i:]
    if "</body>" not in region:
        problems.append("canonical panel is not inside the document body")
    return region, problems


def find_declarations(html):
    """Every column-0 const/let/var bound to an array or object literal."""
    return sorted(set(_TOP_DECL.findall(html)))


def audit_dashboard(html):
    """Audit a dashboard document. Pure: text in, report dict out.

    Report keys: `ok`, `problems`, `surfaces`, `undeclared`, `stale`,
    `violations`, `unhandled`, `athletes`, `statics`, `scratch`, `registry`.
    """
    problems = []
    region, region_problems = find_panel_region(html)
    problems.extend(region_problems)

    if REGISTRY_KEY not in html:
        problems.append("missing %s declaration" % REGISTRY_KEY)

    surfaces = []
    unhandled = []
    for name, route in CANONICAL_SURFACES:
        args = _call_args_after(region, "'%s'" % route)
        # Matched inside the canonical region only, so a fetch elsewhere in the
        # document cannot stand in for the panel doing the work.
        fetched = args is not None
        # Two arguments means a rejection handler. Without one, a failed
        # request silently leaves the card blank, which is how a panel grows a
        # stale-data fallback later.
        handled = bool(fetched and len(args) >= 2 and args[1].strip())
        surfaces.append({"surface": name, "route": route,
                         "fetched": fetched, "handled": handled})
        if not fetched:
            problems.append("canonical panel does not fetch %s" % route)
        elif not handled:
            problems.append(
                "canonical panel fetches %s with no rejection handler" % route)
            unhandled.append(route)

    # The failure path must actually put something on screen. Checking for the
    # word "Unavailable" anywhere is not enough -- that word survives deleting
    # the handler, which is precisely the regression this guards.
    fail_body = _block_after(region, "function fail(")
    writes_text = bool(re.search(r"(textContent|innerHTML)\s*=", fail_body))
    if not fail_body:
        problems.append("canonical panel has no failure renderer")
    elif not writes_text:
        problems.append(
            "canonical failure renderer does not write visible text")

    declarations = find_declarations(html)

    undeclared = [d for d in declarations if d not in DECL_KINDS]
    if undeclared:
        problems.append(
            "undeclared top-level data: %s -- classify each in DECL_KINDS"
            % ", ".join(undeclared))

    stale = sorted(set(DECL_KINDS) - set(declarations))
    if stale:
        problems.append(
            "classified but no longer declared: %s" % ", ".join(stale))

    # The substantive check: the canonical panel may not read the private
    # journal. Word-bounded so `baseRuns` does not match `baseRunsByDistance`.
    violations = []
    for name in LOCAL_ONLY:
        if re.search(r"\b%s\b" % re.escape(name), region):
            violations.append(name)

    if violations:
        problems.append(
            "canonical panel reads local-only data: %s" % ", ".join(violations))

    return {
        "ok": not problems,
        "problems": problems,
        "surfaces": surfaces,
        "declarations": declarations,
        "undeclared": undeclared,
        "stale": stale,
        "violations": violations,
        "unhandled": unhandled,
        "writes_text": writes_text,
        "athletes": [d for d in declarations if DECL_KINDS.get(d) == "athlete"],
        "statics": [d for d in declarations if DECL_KINDS.get(d) == "static"],
        "scratch": [d for d in declarations if DECL_KINDS.get(d) == "scratch"],
        "registry": REGISTRY_KEY in html,
    }


def render_report(report):
    """Render the audit as the tracked document the brief process can read."""
    out = []
    w = out.append
    w("# Dashboard data-source audit")
    w("")
    w("GENERATED FILE -- do not edit by hand. Regenerate with:")
    w("")
    w("```")
    w("python dashboard_contract.py")
    w("```")
    w("")
    w("This exists because `dashboard/index.html` is gitignored and therefore")
    w("invisible to the brief process. Every brief has consequently invented its")
    w("contents. This file is a faithful, machine-checked description of the real")
    w("file, so a brief can read the truth instead of guessing at it.")
    w("")
    w("| | |")
    w("| --- | --- |")
    w("| Result | %s |" % ("PASS" if report["ok"] else "FAIL"))
    w("| Canonical surfaces fetched | %d of %d |" % (
        sum(1 for s in report["surfaces"] if s["fetched"]),
        len(report["surfaces"])))
    w("| Source registry present | %s |" % ("yes" if report["registry"] else "NO"))
    w("| Failure path renders visible text | %s |" % (
        "yes" if report["writes_text"] else "NO"))
    w("| Local-only data read by canonical panel | %s |" % (
        ", ".join(report["violations"]) if report["violations"] else "none"))
    w("")

    if report["problems"]:
        w("## Problems")
        w("")
        for p in report["problems"]:
            w("- %s" % p)
        w("")

    w("## Canonical surfaces")
    w("")
    w("These are the only authoritative answers for activities, load and")
    w("coaching. They are served from `trainloop.db` via `garmin_server.py`.")
    w("")
    w("| Surface | Route | Fetched by canonical panel | Rejection handler |")
    w("| --- | --- | --- | --- |")
    for s in report["surfaces"]:
        w("| `%s` | `%s` | %s | %s |" % (
            s["surface"], s["route"],
            "yes" if s["fetched"] else "**NO**",
            "yes" if s["handled"] else "**NO**"))
    w("")
    w("Every surface must handle its own rejection. A fetch with no error")
    w("callback leaves the card blank, and a blank card is how a panel grows a")
    w("stale-data fallback a few weeks later.")
    w("")

    w("## Local-only data")
    w("")
    w("Hand-entered, private, and never authoritative for the surfaces above.")
    w("This is the athlete's own journal -- narrative notes, splits, hydration,")
    w("injury flags, body weight, coordinates -- and it contains data that does")
    w("not exist in any FIT file. It is not redundant with the canonical corpus")
    w("and is not a stale copy of it. It must not be deleted, and it must not be")
    w("presented as if the data layer had produced it.")
    w("")
    w("| Declaration | Kind |")
    w("| --- | --- |")
    for n in report["athletes"]:
        w("| `%s` | athlete journal |" % n)
    for n in report["statics"]:
        w("| `%s` | static table |" % n)
    for n in report["scratch"]:
        w("| `%s` | scratch/cache |" % n)
    w("")
    w("Every top-level declaration in the file must appear above. An undeclared")
    w("one fails the audit, so inline data cannot be added silently.")
    w("")
    return "\n".join(out) + "\n"


def main():
    import io
    import os
    import sys

    root = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(root, "dashboard", "index.html")
    dst = os.path.join(root, "docs", "DASHBOARD_AUDIT.md")

    if not os.path.exists(src):
        sys.stderr.write(
            "dashboard/index.html not found. It is gitignored and local-only.\n")
        return 2

    with io.open(src, encoding="utf-8") as fh:
        html = fh.read()

    report = audit_dashboard(html)

    with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_report(report))

    if report["ok"]:
        print("PASS  %d surfaces, %d local-only, %d static, %d scratch"
              % (len(report["surfaces"]), len(report["athletes"]),
                 len(report["statics"]), len(report["scratch"])))
        print("wrote docs/DASHBOARD_AUDIT.md")
        return 0

    print("FAIL")
    for p in report["problems"]:
        print("  - %s" % p)
    print("wrote docs/DASHBOARD_AUDIT.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())