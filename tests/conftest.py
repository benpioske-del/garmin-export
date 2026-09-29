"""Shared fixtures.

The real FIT files are local-only and are not in the repository, so the tests
that need a genuine Garmin file skip themselves when it is absent. Fixtures
synthesised here cover the negative cases the real corpus cannot: a file with
no GPS, and a malformed file.
"""

import glob
import os

import pytest

import paths

REAL_FIT = sorted(glob.glob(os.path.join(paths.fit_dir(), "*.fit")))

requires_real_fit = pytest.mark.skipif(
    not REAL_FIT,
    reason="no local FIT files; set GARMIN_FIT_DIR to run FIT tests",
)


class FakeField:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class FakeMessage:
    def __init__(self, fields):
        self._fields = [FakeField(n, v) for n, v in fields]

    def __iter__(self):
        return iter(self._fields)

    def get(self, name, default=None):
        for f in self._fields:
            if f.name == name:
                return f.value
        return default


class FakeFitFile:
    """Stands in for fitparse.FitFile to build negative fixtures.

    fitparse cannot write FIT files, so a record message with no position
    fields cannot be produced from a real file. This injects one directly.
    """

    def __init__(self, records=None, laps=None, sessions=None):
        self._records = records if records is not None else [
            FakeMessage([("timestamp", 1000), ("distance", 10.0),
                         ("enhanced_speed", 3.1)]),
        ]
        self._laps = laps or []
        self._sessions = sessions or []

    def get_messages(self, name):
        return {"record": self._records,
                "lap": self._laps,
                "session": self._sessions}.get(name, [])
