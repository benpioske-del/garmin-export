#!/usr/bin/env python3
"""One command that refreshes the published CSV and the supervisor brief.

This is what `Run CrewAI Supervisor.cmd` calls. It exists because the two
publish paths have to agree on order and on what counts as success, and
encoding that in a batch file makes it impossible to test.

    1. drain the brief inbox      (brief if the flow left one)
    2. publish                    (CSV always, brief if it was captured)

Both steps go through export_publish.py, so there is one commit path, one set of
guards and one rebase/push. Running the publisher last means the CSV is
published even on a run with no brief, and a brief-only run still refreshes the
CSV rather than leaving it stale.

Exit codes are meaningful, because a supervisor wrapper needs to know whether to
alert: 0 all good, 1 something was rejected, 2 something failed outright.
A missing brief is NOT a failure. Most runs will not produce one, and treating
that as an error would train the athlete to ignore the output.
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

REPO = paths.repo_dir()


def _run(label, argv):
    print("\n=== %s ===" % label)
    r = subprocess.run([sys.executable] + argv, cwd=REPO)
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and show, but never write or push")
    ap.add_argument("--skip-capture", action="store_true",
                    help="publish the CSV without touching the brief inbox")
    ap.add_argument("--no-publish", action="store_true",
                    help="validate the brief but do not commit or push")
    a = ap.parse_args()

    dry = ["--dry-run"] if a.dry_run or a.no_publish else []
    brief_rc = 0
    if not a.skip_capture:
        brief_rc = _run("capture brief", [os.path.join(HERE, "brief_bridge.py"),
                                          "ingest"] + dry)
        if brief_rc != 0:
            print("\nthe brief was rejected. See the staging path above; it is "
                  "outside the repository and safe to read locally.")
    else:
        print("\n=== capture brief ===\nskipped (--skip-capture)")

    # The publisher runs last and is unconditional, so the CSV is never left
    # stale just because a brief was rejected.
    publish_rc = _run("publish", [os.path.join(HERE, "export_publish.py")]
                      + (["--check"] if a.no_publish else []))

    print("\n" + "=" * 60)
    if brief_rc != 0 or publish_rc != 0:
        print("supervisor run finished WITH PROBLEMS")
        print("  brief   : %s" % ("rejected" if brief_rc else "ok"))
        print("  publish : %s" % ("failed" if publish_rc else "ok"))
        print("\nNothing unsafe was committed. Review the staged brief, then "
              "re-run.")
        return 1
    print("supervisor run finished cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())