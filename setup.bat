@echo off
rem One-time setup on the Windows test machine (Python 3.10+ on PATH).
setlocal
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
rem Behind the company proxy: set HTTPS_PROXY=http://proxy:port before running this script
python -m pip install -r requirements.txt || goto :error
if not exist config\local.yaml (
  copy config\local.example.yaml config\local.yaml >nul
  echo Created config\local.yaml - set browser.exe to your SamsungInternet.exe
)
echo.
echo Next: edit config\local.yaml, then run:  .venv\Scripts\python -m sbtest.tools.doctor
exit /b 0
:error
echo Setup failed.
exit /b 1
