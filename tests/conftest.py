"""Shared fixtures.

The real FIT files are local-only and are not in the repository, so the tests
that need a genuine Garmin file skip themselves when it is absent. Fixtures
synthesised here cover the negative cases the real corpus cannot: a file with
no GPS, and a malformed file.
"""

import glob
import os
import sqlite3

import pytest

import paths
import trainingdb

REAL_FIT = sorted(glob.glob(os.path.join(paths.fit_dir(), "*.fit")))

requires_real_fit = pytest.mark.skipif(
    not REAL_FIT,
    reason="no local FIT files; set GARMIN_FIT_DIR to run FIT tests",
)


def _real_db_is_migrated():
    """True when the local training database exists and has the schema.

    CI checks out the code only: trainloop.db is athlete data and is never
    committed. Tests that assert against the real corpus must skip there rather
    than fail on a table that was never created.
    """
    path = trainingdb.db_path()
    if not os.path.isfile(path):
        return False
    try:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("SELECT COUNT(*) FROM activities").fetchone()
            conn.execute("SELECT COUNT(*) FROM review_items").fetchone()
            return True
        finally:
            conn.close()
    except sqlite3.Error:
        return False


REAL_DB_READY = _real_db_is_migrated()

requires_real_db = pytest.mark.skipif(
    not REAL_DB_READY,
    reason="no migrated trainloop.db; run trainloop.py bootstrap to run these",
)

# Some checks compare the committed brief against both the FIT corpus and the
# database. Both are local-only, so a clean checkout skips them.
requires_live_corpus = pytest.mark.skipif(
    not REAL_FIT or not REAL_DB_READY,
    reason="live FIT corpus and migrated trainloop.db are both required",
)


@pytest.fixture
def migrated_db(tmp_path, monkeypatch):
    """A migrated, empty database isolated from the athlete's real one.

    Wire-level tests need the schema, not the data. Without this they only pass
    on a machine that happens to have trainloop.db, which is how the dashboard
    HTTP tests were silently coupled to the real corpus.
    """
    db = tmp_path / "migrated.db"
    monkeypatch.setenv(trainingdb.DB_ENV, str(db))
    conn = trainingdb.connect(db)
    trainingdb.migrate(conn, verbose=False)
    try:
        yield conn
    finally:
        conn.close()


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
