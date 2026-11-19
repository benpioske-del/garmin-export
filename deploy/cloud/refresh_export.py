#!/usr/bin/env python3
"""Rebuild garmin_export.csv from the local FIT corpus, without git.

The dashboard reads per-mile lap splits and best-5K times from
``garmin_export.csv`` next to ``garmin_server.py``. The nightly sync downloads
new FIT files but does not rewrite that CSV, so without this step every new run
would appear on the cloud host with no splits.

``export_publish.build_csv()`` writes the CSV and its meta file and then stops.
This calls exactly that function, so the cloud host uses the same builder as the
laptop and needs no repository credentials. The working tree is left with two
modified tracked files on purpose; the next code upgrade resets them and the
following sync rebuilds them.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
# paths.repo_dir() honours this override, so build_csv() writes into the
# checkout even when the script is invoked from somewhere else.
os.environ.setdefault("GARMIN_REPO", REPO)

import export_publish  # noqa: E402


def main():
    try:
        meta, _cols = export_publish.build_csv()
    except SystemExit as exc:
        # build_csv() calls die() when there is no activity data at all. That is
        # a real failure for the timer, but it must not look like a crash.
        print("export refresh skipped: %s" % (exc.code or "no activity data"))
        return 1
    print("export refreshed: %d runs, latest %s"
          % (meta["run_count"], meta["latest_run"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
