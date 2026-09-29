"""Path resolution for the Garmin pipeline.

Code lives in the repository and is version controlled. Athlete data, Garmin
credentials and raw FIT files live in a local-only directory and are never
committed. Keeping those two concerns in one place stops a future edit from
dropping a token or a sleep export into a public repository.

Override the local data location with the GARMIN_DATA_DIR environment variable.
"""

import os

# Local-only data: raw FIT, tokens, downloaded CSVs, logs, sync markers.
# Never committed. The publisher's .gitignore also blocks these as a second line
# of defence, in case someone points GARMIN_DATA_DIR at the repo by mistake.
DATA_SUBDIRS = (".garmin_tokens", "garmin_fit")
DATA_FILES = ("garmin_sleep.csv", "garmin_hr.csv", "garmin_last_sync.json",
              "garmin_sync.log", "garmin_tokens.json")


def _default_data_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads")


def data_dir():
    """Local-only directory for athlete data, credentials and logs."""
    d = os.environ.get("GARMIN_DATA_DIR")
    return os.path.abspath(d) if d else _default_data_dir()


def repo_dir():
    """The git repository holding published output and code."""
    override = os.environ.get("GARMIN_REPO")
    if override:
        return os.path.abspath(override)
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.isdir(os.path.join(here, ".git")):
        return here
    base = os.path.join(os.path.dirname(here), "garmin-export")
    if os.path.isdir(os.path.join(base, ".git")):
        return base
    if os.path.isdir(base):
        kids = [d for d in sorted(os.listdir(base))
                if os.path.isdir(os.path.join(base, d, ".git"))]
        if len(kids) == 1:
            return os.path.join(base, kids[0])
    return base


def fit_dir():
    return os.environ.get("GARMIN_FIT_DIR") or os.path.join(data_dir(), "garmin_fit")
