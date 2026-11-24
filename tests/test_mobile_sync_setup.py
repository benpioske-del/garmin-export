"""The phone's Garmin sync must run entirely inside the always-on container.

Nothing here contacts Garmin or the tunnel. These tests pin the configuration
that used to make a phone tap look successful while the data never arrived: a
Windows FIT glob in the importer, a nightly job that printed help instead of
importing, and a sync script whose token dependency was missing from the image.
"""

import io
import os
import re

import trainloop

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(relative):
    with io.open(os.path.join(HERE, relative), encoding="utf-8") as fh:
        return fh.read()


def test_fit_glob_follows_the_container_data_dir(monkeypatch):
    monkeypatch.setenv("GARMIN_DATA_DIR", "/data")
    pattern = trainloop.default_fit_glob()
    # paths.data_dir() normalises through abspath, so the expected prefix is
    # platform-specific even though the container always passes an absolute path.
    assert pattern == os.path.join(os.path.abspath("/data"), "garmin_fit", "*.fit")
    assert "\\Users\\" not in pattern
    # Parsing happens after the environment is set, so every subcommand sees it.
    for command in ("bootstrap", "import", "audit"):
        args = trainloop.build_parser().parse_args([command])
        assert args.pattern == pattern


def test_nightly_refresh_imports_after_the_download():
    text = _read("deploy/northflank/start.sh")
    download = text.index("garmin_sync.py")
    importer = text.index("trainloop.py", download)
    assert importer > download
    assert re.search(r'trainloop\.py"\s+bootstrap', text)
    # A bare invocation only prints help and returns 1.
    assert not re.search(r'trainloop\.py"\s*\|\|', text)


def test_container_declares_every_sync_dependency():
    requirements = _read("requirements.txt")
    pyproject = _read("pyproject.toml")
    # garminconnect imports garth at login time; without it /sync exits 1 with
    # no stdout, so the phone only ever sees a generic failure.
    assert re.search(r"(?mi)^garth\b", requirements)
    assert re.search(r'"garth[>=~]', pyproject)


def test_missing_dependency_message_names_all_packages():
    text = _read("garmin_sync.py")
    assert '" ".join(PACKAGES)' in text
    assert "pip install garminconnect\\n" not in text


def test_tunnel_and_loopback_server_are_container_owned():
    text = _read("deploy/northflank/start.sh")
    assert "START_TUNNEL" in text
    assert "127.0.0.1:24567" in text
    assert "foam-tackiness-header.ngrok-free.dev" in text
    assert "--lan" not in text
