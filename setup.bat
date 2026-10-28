@echo off
rem Prepare a Windows test machine: install Python packages, then check the machine (doctor:
rem browser exe, Chromium version, chromedriver - downloaded if missing -, browser start, UI).
rem   setup.bat                                        exe from config\local.yaml (asked the first time)
rem   setup.bat --exe "C:\build\SamsungInternet.exe"   check that build
rem Then run the tests on their own:  .venv\Scripts\python run.py --sanity
rem Behind a company proxy, first:  set HTTPS_PROXY=http://proxy.company.com:8080
setlocal
cd /d "%~dp0"
rem colours (Windows 10+ console); set NO_COLOR=1 for plain text, e.g. when saving the output
set "G=" & set "R=" & set "H=" & set "B=" & set "D=" & set "N="
if not defined NO_COLOR (
  for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
)
if defined ESC (
  set "G=%ESC%[32m" & set "R=%ESC%[31m" & set "H=%ESC%[36;1m" & set "B=%ESC%[1m" & set "D=%ESC%[90m" & set "N=%ESC%[0m"
)
set "OK=  %G%[ OK ]%N%"
set "FAIL=  %R%[FAIL]%N%"
set "FIX=         %R%fix:%N%"

echo %H%=================================================%N%
echo %H%  sbtest setup - install and check this machine%N%
echo %H%=================================================%N%

echo.
echo %B%[1/4] Python%N%
rem a working project environment decides the Python; a .venv whose Python was uninstalled
rem or moved does not start and is made again in step 2
set "VENV_OK="
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python -c "import sys" >nul 2>&1 && set "VENV_OK=1"
)
if defined VENV_OK goto :venv_python
rem the "python" command can be the Microsoft Store alias: try the py launcher first
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo %FAIL% Python 3.10 or newer not found
  echo %FIX% install Python 3.12+: winget install -e --id Python.Python.3.12
  echo          or from https://www.python.org/downloads/windows/ - tick "Add python.exe to PATH" -,
  echo          then open a NEW terminal and run setup.bat again. Already installed? Turn off the
  echo          "python.exe" alias: Settings ^> Apps ^> Advanced app settings ^> App execution aliases
  goto :failed
)
for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set "PYV=%%v"
echo %OK% Python %PYV%
goto :packages

:venv_python
for /f "delims=" %%v in ('.venv\Scripts\python -c "import sys; print(sys.version.split()[0])"') do set "PYV=%%v"
echo %OK% Python %PYV% ^(project environment .venv^)

:packages

echo.
echo %B%[2/4] Packages%N%
if exist .venv\Scripts\python.exe if not defined VENV_OK (
  echo          %D%the project environment .venv is broken - making it again%N%
  rmdir /s /q .venv
)
if not exist .venv\Scripts\python.exe (
  echo          %D%creating the project environment .venv%N%
  %PY% -m venv .venv >nul || goto :venv_failed
)
rem install only when requirements.txt changed since the last install
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  echo          %D%installing requirements.txt - the first time takes a minute or two%N%
  rem a recent pip trusts the Windows certificate store - company SSL inspection; not fatal
  .venv\Scripts\python -m pip install -q --disable-pip-version-check --upgrade pip >nul 2>&1
  .venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || goto :pip_failed
  copy /y requirements.txt .venv\requirements.installed >nul
  echo %OK% Packages installed
) else (
  echo %OK% Packages up to date
)

.venv\Scripts\python -m sbtest.tools.setup %*
exit /b %errorlevel%

:venv_failed
echo %FAIL% Could not create .venv
echo %FIX% delete the .venv folder and run setup.bat again
goto :failed

:pip_failed
echo %FAIL% Could not install the packages - the pip message above says why
echo %FIX% behind a company proxy: set HTTPS_PROXY=http://proxy:port, then run setup.bat again.
echo          SSL / certificate error on Python 3.10-3.11: install Python 3.12+ ^(its pip trusts the
echo          Windows certificates^), delete the .venv folder and run setup.bat again
goto :failed

:failed
echo.
echo %R%SETUP FAILED - fix the FAIL line above, then run setup.bat again%N%
exit /b 1
