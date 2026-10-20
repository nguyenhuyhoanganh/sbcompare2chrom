@echo off
rem One-time setup on a Windows test machine: Python venv + packages + config/local.yaml.
rem Needs Python 3.10+ (python.org installer, "py" launcher). Behind a proxy, first run:
rem   set HTTPS_PROXY=http://proxy.company.com:8080
setlocal
cd /d "%~dp0"

rem -- find a real Python (the "python" command can be the Microsoft Store alias) --
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Python 3.10+ not found. Install it from https://www.python.org/downloads/windows/
  echo ^(tick "Add python.exe to PATH"^), or turn off the "python.exe" App execution alias in
  echo Settings ^> Apps ^> Advanced app settings, then run setup.bat again.
  goto :error
)
echo Using: %PY%
%PY% --version

if not exist .venv (
  %PY% -m venv .venv || goto :error
)
.venv\Scripts\python -m pip install --upgrade pip || goto :error
.venv\Scripts\python -m pip install -r requirements.txt || goto :error

if not exist config\local.yaml (
  copy config\local.example.yaml config\local.yaml >nul
  echo Created config\local.yaml - set targets.samsung.browser.exe to the SamsungInternet.exe to test
)
echo.
echo Setup done. Next:
echo   1. notepad config\local.yaml        ^(path of the Samsung exe^)
echo   2. .venv\Scripts\python -m sbtest.tools.doctor
echo See SETUP.md for the whole checklist.
exit /b 0

:error
echo Setup failed.
exit /b 1
