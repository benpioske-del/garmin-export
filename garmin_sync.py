#!/usr/bin/env python3
"""
garmin_sync.py - one-command Garmin Connect -> FIT folder sync.

Purpose
-------
Coach Dashboard (Coach Dashboard v1.1.html) already imports .fit files in-browser
(multi-select supported). This script removes the manual "download file, download
file, download file" part of that loop: it logs into Garmin Connect once with
your real account (login is cached on THIS machine only - nothing is sent to the
dashboard or any other service), finds running activities you haven't pulled yet,
and saves their .fit files into ./garmin_fit/.

It also exports your last N nights of sleep (default 14) into garmin_sleep.csv
so you can import them straight into the dashboard's Health Vault vitals.

Then you open the dashboard and use the FIT multi-import, selecting the whole
folder's contents at once.

Requirements (one-time, ~2 minutes)
-----------------------------------
1. Install Python 3.11+ (Microsoft Store or winget is fine):
       winget install -e --id Python.Python.3.12
   (You can also grab the installer from python.org.)
2. Install the two libraries:
       pip install garminconnect
3. Run it:
       py garmin_sync.py
   or:  python garmin_sync.py

Login
-----
Yes - it uses just your Garmin email and password. No third-party app, no
special device auth.

How it works:
- First run: you are asked for your Garmin email and password (or set them once
  in environment variables, see below). Your password is NEVER written to disk.
- If 2FA / MFA is enabled on the account (recommended - Garmin will ask for the
  6-digit code), the script prompts for that code on first login from a new
  machine. One time.
- After the first successful login, Garmin's refresh tokens are cached in the
  .garmin_tokens/ folder, so later runs happen with no prompts at all until the
  tokens eventually expire (typically months later).

To avoid typing credentials every run, set environment variables once:
   Windows PowerShell:
     $env:GARMIN_EMAIL="you@example.com"
     $env:GARMIN_PASSWORD="your-password"
   or set them as system/user environment variables permanently.
Optional: $env:GARMIN_SLEEP_DAYS="14" to change how many nights of sleep are pulled.

Garmin is a third party and this uses their unofficial, community-written API.
Their endpoints can change without notice; if the script breaks, update the
library first:  pip install -U garminconnect garth

Intended for personal, non-commercial use against your own Garmin account only.
It retrieves your own activities and sleep; it does not scrape, index, or build
data about other users. Garmin's developer program and brand guidelines apply
to official integrations; using the community library isn't officially endorsed
by Garmin, so review Garmin's current terms if you publish or distribute this.
Weather lookups in the dashboard use Open-Meteo (CC BY 4.0 - see
https://open-meteo.com/ for attribution requirements). This file is a personal
health record / training decision-support tool and is not medical advice.
"""

from __future__ import annotations

import json
import os
import sys
import datetime
import getpass

PACKAGES = ("garminconnect", "garth")

def _retry_with_user_site() -> bool:
    """Some launchers (e.g. the Windows Store GUI python) exclude the user site
    dir from sys.path; put it back so pip --user installs are importable."""
    try:
        import site as _site
        import os as _os
    except Exception:
        return False
    candidates = []
    try:
        us = _site.getusersitepackages()
    except Exception:
        us = None
    if us:
        candidates.append(us)
        sd = _os.path.dirname(us)
        if _os.path.basename(sd) == "Python313":
            candidates.append(sd)
    for cand in candidates:
        if not cand or not _os.path.isdir(cand):
            continue
        try:
            _site.addsitedir(cand)
        except Exception:
            continue
        try:
            for pkg in PACKAGES:
                __import__(pkg)
            return True
        except Exception:
            continue
    return False

for pkg in PACKAGES:
    try:
        __import__(pkg)
    except ImportError:
        if not _retry_with_user_site():
            sys.exit(
                f"Missing package '{pkg}'.\n\n"
                "Install dependencies first:\n"
                "    pip install garminconnect\n"
                "\nIf 'pip' isn't on PATH, try:  py -m pip install garminconnect\n"
            )

try:
    from garminconnect import Garmin
except Exception:  # pragma: no cover - defensive against API renames
    sys.exit("Could not import garminconnect. Update it:  pip install -U garminconnect")

import garminconnect as _gc

# FIT download format differs between garminconnect versions:
#   new (0.3.13+):  Garmin.ActivityDownloadFormat.ORIGINAL  (enum inside the class)
#   top-level "fit": older builds exposed a dl_fmt helper to pass the string.
def resolve_fit_fmt():
    g = getattr(_gc, "Garmin", None)
    if g is not None:
        adf = getattr(g, "ActivityDownloadFormat", None)
        if adf is not None:
            original = getattr(adf, "ORIGINAL", None)
            if original is not None:
                return original
    for candidate in (getattr(_gc, "dl_fmt", None),):
        if candidate is not None:
            return candidate
    try:
        from garminconnect.constants import dl_fmt
        return dl_fmt
    except Exception:
        return None

FIT_FMT = resolve_fit_fmt()

# Everything this script writes is athlete data or a credential, so it all goes
# to the local data directory. None of it may land in the repository, which is
# public. Previously these paths were relative to the script, which meant moving
# the script into the repo would have put Garmin tokens and garmin_sleep.csv
# inside a published git repository.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

_DATA = paths.data_dir()
os.makedirs(_DATA, exist_ok=True)

OUTPUT_DIR = paths.fit_dir()
os.makedirs(OUTPUT_DIR, exist_ok=True)
MARKER_FILE = os.path.join(_DATA, "garmin_last_sync.json")
TOKEN_DIR = os.path.join(_DATA, ".garmin_tokens")
SLEEP_CSV = os.path.join(_DATA, "garmin_sleep.csv")
HR_CSV = os.path.join(_DATA, "garmin_hr.csv")
LOG_FILE = os.path.join(_DATA, "garmin_sync.log")
RUNNING_HINTS = ("running", "treadmill", "track", "trail", "lap")

EMAIL = os.environ.get("GARMIN_EMAIL", "")
PASSWORD = os.environ.get("GARMIN_PASSWORD", "")

try:
    SLEEP_DAYS = int(os.environ.get("GARMIN_SLEEP_DAYS", "14"))
except ValueError:
    SLEEP_DAYS = 14
SLEEP_DAYS = max(1, min(SLEEP_DAYS, 31))

SLEEP_CSV_COLUMNS = ("date", "total_min", "deep_min", "rem_min", "light_min", "awake_min", "score")
HR_CSV_COLUMNS = ("date", "rhr", "max_hr", "hrv", "hrv_status")


def should_include(activity: dict) -> bool:
    """Keep only running-ish activities; skip lifts, swims, rides, etc."""
    name = str(activity.get("activityName", "") or "").lower()
    sport = str(activity.get("sportType", "") or "").lower()
    act_type = str(activity.get("activityType", {}).get("typeKey", "") if isinstance(
        activity.get("activityType"), dict) else activity.get("activityType", "")).lower()
    hay = f"{name} {sport} {act_type}"
    if sport and "running" in sport:
        return True
    if act_type and "running" in act_type:
        return True
    return any(h in hay for h in RUNNING_HINTS)


def load_marker() -> str:
    try:
        with open(MARKER_FILE, "r", encoding="utf-8") as fh:
            return str(json.load(fh).get("newest_start", "") or "")
    except Exception:
        return ""


def save_marker(newest: str) -> None:
    try:
        with open(MARKER_FILE, "w", encoding="utf-8") as fh:
            json.dump({"newest_start": newest,
                       "saved_at": datetime.datetime.now().isoformat()}, fh)
    except Exception as exc:
        print(f"[warn] could not save sync marker: {exc}")


def iso_to_ts(iso: str) -> float:
    try:
        # startTimeLocal arrives as e.g. "2026-09-07 06:43:06"
        if "T" in iso:
            iso = iso.replace("T", " ")
        return datetime.datetime.strptime(iso[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        return 0.0


def login() -> Garmin:
    store = os.environ.get("GARMINTOKENS") or TOKEN_DIR

    # 1) Reuse cached tokens from a previous login if they exist — this skips
    #    the SSO login endpoint entirely (no prompts, no login, no 429 risk).
    token_files = []
    try:
        if os.path.isdir(store):
            token_files = [
                p for p in (os.path.join(store, f) for f in os.listdir(store))
                if p.lower().endswith(".json") and os.path.isfile(p)
            ]
    except Exception:
        pass
    if token_files:
        try:
            client = Garmin()  # credentials not needed; tokens are loaded from store
            client.login(tokenstore=store)
            print("Restored session from cached Garmin tokens (no re-login needed).")
            return client
        except Exception as exc:
            print(f"[info] cached token restore failed ({exc}); logging in fresh.")

    # 2) Fresh credential login. Garmin login is IP rate-limited (429) if you
    #    retry too fast, so the client is configured for a single attempt.
    email = EMAIL or input("Garmin email: ").strip() or None
    if not email:
        sys.exit("No email given.")
    password = PASSWORD or getpass.getpass("Garmin password: ")

    def mfa_prompt() -> str:
        return input("Enter your Garmin 2FA code: ").strip()

    client = Garmin(email, password, prompt_mfa=mfa_prompt,
                    retry_attempts=1, retry_min_wait=1.0, retry_max_wait=2.0)
    try:
        client.login(tokenstore=store)
    except Exception as exc:
        msg = str(exc).lower()
        if "mfa" in msg or "totp" in msg or "tfa" in msg or "code" in msg:
            # prompt_mfa above re-asks for a fresh code on the next attempt.
            print("A fresh Garmin 2FA code is needed.")
            client.login(tokenstore=store)
        else:
            raise
    print("Logged into Garmin Connect (tokens cached locally).")
    return client


def secs_to_min(seconds) -> int:
    """Garmin reports sleep durations in seconds; round to whole minutes."""
    try:
        return int(round(float(seconds or 0) / 60.0))
    except (TypeError, ValueError):
        return 0


def parse_sleep_payload(payload, date: str) -> dict:
    """Reduce a get_sleep_data() response to one CSV row, tolerating API shape changes."""
    data = payload
    # Newer library versions return a SleepData model; older ones a plain dict.
    if hasattr(data, "data"):
        data = data.data
    dto = data
    if isinstance(dto, dict):
        dto = data.get("dailySleepDTO") or data.get("dailySleep") or data
    if not isinstance(dto, dict):
        return {"date": date, **{k: 0 for k in SLEEP_CSV_COLUMNS[1:3]},
                "rem_min": 0, "light_min": 0, "awake_min": 0, "score": ""}

    levels = dto.get("sleepLevels") or {}
    summary = levels.get("summary") if isinstance(levels, dict) else None
    if not isinstance(summary, dict):
        summary = {}
    # Seconds may sit directly on the DTO (new API) or under summary (older API).
    deep = dto.get("deepSleepSeconds") or summary.get("deep") or summary.get("deepSleepSeconds") or 0
    rem = dto.get("remSleepSeconds") or summary.get("rem") or summary.get("remSleepSeconds") or 0
    light = dto.get("lightSleepSeconds") or summary.get("light") or summary.get("lightSleepSeconds") or 0
    awake = dto.get("awakeSleepSeconds") or summary.get("awake") or 0

    total = dto.get("sleepTimeSeconds") or dto.get("sleepTime") or dto.get("sleepTimeTotal") or 0
    score = dto.get("averageSleepScore") or dto.get("sleepScore") or dto.get("sleepQualityScore")
    return {
        "date": date,
        "total_min": secs_to_min(total),
        "deep_min": secs_to_min(deep),
        "rem_min": secs_to_min(rem),
        "light_min": secs_to_min(light),
        "awake_min": secs_to_min(awake),
        "score": int(score) if score else "",
    }


def fetch_sleep(client, days: int):
    """Pull the last `days` nights from Garmin and upsert them into garmin_sleep.csv."""
    if not hasattr(client, "get_sleep_data"):
        print("[warn] this garminconnect version lacks get_sleep_data(); skipping sleep export.")
        return
    today = datetime.date.today()
    existing = read_csv_map(SLEEP_CSV)
    changed = 0
    for offset in range(days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        date_str = day.isoformat()
        try:
            payload = client.get_sleep_data(date_str)
        except Exception as exc:
            msg = str(exc).lower()
            # 204 / "no data" is a normal no-sleep response, not a failure.
            if "204" in msg or "no data" in msg or "not found" in msg:
                continue
            print(f"  ! sleep for {date_str} failed: {exc}")
            continue
        row = parse_sleep_payload(payload, date_str)
        if row["total_min"] <= 0 and row["score"] == "":
            continue  # genuinely empty night
        existing[date_str] = row
        changed += 1

    if changed:
        total = write_csv_map(SLEEP_CSV, existing, SLEEP_CSV_COLUMNS)
        print(f"Sleep    : {changed} night(s) updated -> garmin_sleep.csv ({total} total)")
    else:
        print("Sleep    : no new sleep rows in that window (nothing written).")


def read_csv_map(path: str) -> dict:
    """Load any of our export CSVs into {date: row}; missing file -> empty."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            header = fh.readline()
            cols = [c.strip() for c in header.strip().strip(",").split(",")]
            rows: dict = {}
            for line in fh:
                parts = [p.strip() for p in line.strip().strip(",").split(",")]
                if len(parts) < 2:
                    continue
                row = dict(zip(cols, parts))
                if row.get("date"):
                    rows[row["date"]] = row
            return rows
    except Exception:
        return {}


def write_csv_map(path: str, rows: dict, columns) -> int:
    """Persist {date: row} to `columns`-headed CSV; returns row count."""
    ordered = [rows[d] for d in sorted(rows)]
    try:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(",".join(columns) + "\n")
            for r in ordered:
                fh.write(",".join(str(r.get(c, "")) for c in columns) + "\n")
        return len(ordered)
    except Exception as exc:
        print(f"[warn] could not write {path}: {exc}")
        return 0


def parse_hr_payload(hr: dict, hrv, date: str) -> dict:
    """Build one garmin_hr.csv row from get_heart_rates() + get_hrv_data()."""
    row = {"date": date}
    rhr = hr.get("restingHeartRate")
    maxhr = hr.get("maxHeartRate")
    row["rhr"] = rhr if rhr is not None else ""
    row["max_hr"] = maxhr if maxhr is not None else ""
    hrv_val = ""
    status = ""
    if isinstance(hrv, dict):
        day = hrv.get("day")
        if isinstance(day, dict):
            hrv_val = day.get("lastNightAvg") or day.get("weeklyAvg") or ""
            status = day.get("lastNightStatus") or day.get("weeklyAvgStatus") or ""
        if not hrv_val:
            for k in ("lastNightAvg", "weeklyAvg", "mostRecentReading"):
                v = hrv.get(k)
                if v is not None:
                    hrv_val = v
                    break
        if not status:
            status = hrv.get("lastNightStatus") or hrv.get("weeklyAvgStatus") or ""
    if isinstance(hrv_val, (int, float)):
        hrv_val = int(round(hrv_val))
    row["hrv"] = hrv_val
    row["hrv_status"] = status
    return row


def fetch_hr(client, days: int):
    """Pull resting/max HR + overnight HRV for the last `days` nights into garmin_hr.csv."""
    if not hasattr(client, "get_heart_rates"):
        print("[warn] this garminconnect version lacks get_heart_rates(); skipping HR export.")
        return
    today = datetime.date.today()
    existing = read_csv_map(HR_CSV)
    changed = 0
    for offset in range(days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        date_str = day.isoformat()
        try:
            hr = client.get_heart_rates(date_str)
        except Exception as exc:
            msg = str(exc).lower()
            if "204" in msg or "no data" in msg or "not found" in msg:
                continue
            print(f"  ! HR for {date_str} failed: {exc}")
            continue
        if not isinstance(hr, dict) or hr.get("restingHeartRate") is None:
            continue  # day has no HR data (watch not worn)
        try:
            hrv = client.get_hrv_data(date_str)
        except Exception:
            hrv = None
        existing[date_str] = parse_hr_payload(hr, hrv, date_str)
        changed += 1

    if changed:
        total = write_csv_map(HR_CSV, existing, HR_CSV_COLUMNS)
        print(f"HR       : {changed} day(s) updated -> garmin_hr.csv ({total} total)")
    else:
        print("HR       : no new HR rows in that window (nothing written).")


def main() -> None:
    marker = load_marker()
    print(f"Output folder : {OUTPUT_DIR}")
    print(f"Last sync     : {marker or 'none (will sync from the newest activity back)'}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client = login()

    try:
        activities = client.get_activities(0, 200)
    except Exception as exc:
        sys.exit(f"Could not list activities: {exc}")

    if not activities:
        print("No activities returned - nothing to do.")
        return

    runs = [a for a in activities if should_include(a)]

    print(f"Found {len(activities)} recent activities, {len(runs)} look like running.")
    if not runs:
        print("Nothing that looks like a run in the recent window.")
        return

    newest_seen = ""
    saved = 0
    skipped = 0
    for act in runs:
        start = str(act.get("startTimeLocal", "") or "")
        act_id = act.get("activityId")
        if not act_id:
            continue
        if not newest_seen or start > newest_seen:
            newest_seen = start
        if start and marker and start <= marker:
            skipped += 1
            continue
        out_path = os.path.join(OUTPUT_DIR, f"{start[:10]}_{act_id}.fit")
        if os.path.exists(out_path):
            skipped += 1
            continue
        try:
            payload = client.download_activity(act_id, dl_fmt=FIT_FMT) if FIT_FMT else \
                client.download_activity(act_id, dl_fmt="fit")
            if isinstance(payload, str):
                # some versions return a path; copy the file
                import shutil
                shutil.copyfile(payload, out_path)
            else:
                data = payload or b""
                if data[:2] == b"PK":
                    # the endpoint sometimes wraps the .fit inside a zip
                    import io as _io
                    import zipfile as _zipfile
                    import contextlib as _ctx
                    with _ctx.closing(_zipfile.ZipFile(_io.BytesIO(data))) as _z:
                        names = _z.namelist()
                        pick = next((n for n in names if n.lower().endswith(".fit")), names[0])
                        data = _z.read(pick)
                with open(out_path, "wb") as fh:
                    fh.write(data)
            print(f"  + {start[:10]}  activity {act_id}  ->  {os.path.basename(out_path)}")
            saved += 1
        except Exception as exc:
            print(f"  ! activity {act_id} failed: {exc}")

    if newest_seen:
        save_marker(newest_seen)

    print(f"\nDone: {saved} new run(s) downloaded, {skipped} already current.")
    try:
        fetch_sleep(client, SLEEP_DAYS)
    except Exception as exc:
        print(f"[warn] sleep export failed (runs were still fine): {exc}")
    try:
        fetch_hr(client, SLEEP_DAYS)
    except Exception as exc:
        print(f"[warn] HR export failed (runs were still fine): {exc}")
    print(f"Next: open Coach Dashboard v1.1.html -> Log a new run -> pick {OUTPUT_DIR}\\*\n"
          "      (you can select all the files at once in the FIT import), or just\n"
          "      run this script on a schedule and sync the newest each time.\n"
          f"Sleep CSV: {SLEEP_CSV}\n"
          f"HR CSV   : {HR_CSV}\n"
          "      In the dashboard: Health Vault -> Vitals -> 'Import Garmin sleep (.csv)'\n"
          "      and 'Import Garmin heart rate (.csv)' to fold these into the vitals log.")


if __name__ == "__main__":
    import datetime as _dt
    import sys as _sys
    class _Tee:
        def __init__(self, *handles):
            self.handles = handles
        def write(self, text):
            for h in self.handles:
                try:
                    h.write(text)
                except Exception:
                    pass
        def flush(self):
            for h in self.handles:
                try:
                    h.flush()
                except Exception:
                    pass
    _logfh = open(LOG_FILE, "a", encoding="utf-8")
    _logfh.write("\n===== run at %s =====\n" % _dt.datetime.now().isoformat())
    _sys.stdout = _Tee(_sys.stdout, _logfh)
    _sys.stderr = _Tee(_sys.stderr, _logfh)
    try:
        main()
    except SystemExit:
        pass
    except Exception:
        import traceback as _tb
        _logfh.write("FAILED:\n%s\n" % _tb.format_exc())
        _logfh.flush()
        _sys.exit(1)
    finally:
        try:
            _logfh.flush()
        except Exception:
            pass
        # Optional: republish the normalised export to the GitHub repo.
        # Set GARMIN_PUBLISH=1 to enable. Inert and silent when unset, or when
        # git/repo are not available - a publish failure never fails the sync.
        if os.environ.get("GARMIN_PUBLISH") == "1":
            try:
                import subprocess as _sp
                _r = _sp.run([sys.executable, os.path.join(os.path.dirname(
                    os.path.abspath(__file__)), "export_publish.py")],
                    capture_output=True, text=True, timeout=180)
                print(_r.stdout.strip() or _r.stderr.strip())
                if _r.returncode != 0:
                    print("[warn] export_publish did not complete; sync data is fine")
            except Exception as exc:
                print("[warn] export_publish skipped: %s" % exc)