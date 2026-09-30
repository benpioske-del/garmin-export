@echo off
REM Convenience wrapper for trainloop.py.
REM
REM Double-click this file, or run it from cmd:
REM     trainloop.cmd status
REM     trainloop.cmd bootstrap
REM     trainloop.cmd
REM
REM With no arguments it prints status rather than opening a window that
REM vanishes before it can be read.

setlocal
cd /d "%~dp0"

if "%~1"=="" (
    set "CMD=status"
) else (
    set "CMD=%~1"
    shift
)

REM Drop the shift so trainloop.py sees only its own arguments.
set "ARGS=%1 %2 %3 %4 %5 %6 %7 %8 %9"

where python >nul 2>&1
if errorlevel 1 (
    echo python was not found on PATH.
    echo Install Python 3.10+ and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

python trainloop.py %CMD% %ARGS%
set "RC=%ERRORLEVEL%"

if "%CMD%"=="status" pause
if "%CMD%"=="doctor" pause

endlocal & exit /b %RC%
