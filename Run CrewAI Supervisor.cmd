@echo off
REM Refresh the published Garmin CSV and capture the CrewAI supervisor brief.
REM
REM   "Run CrewAI Supervisor.cmd"            capture any brief, then publish
REM   "Run CrewAI Supervisor.cmd" --dry-run  validate everything, change nothing
REM
REM The brief is only produced if the flow left one in the inbox, or if
REM CREWAI_FLOW_CMD is set. A run with no brief is normal, not a failure.

setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo python was not found on PATH.
    echo Install Python 3.10+ and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

python supervisor_publish.py %1 %2 %3
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo Done. CSV published, brief handled.
) else (
    echo Finished with problems - see the output above.
    echo A rejected brief is staged OUTSIDE the repo; nothing was pushed.
)

REM So a double-click does not vanish before it can be read.
pause
endlocal & exit /b %RC%