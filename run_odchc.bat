@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ODCHC data tools
set PYTHONUTF8=1
set RC=0

REM ---- 1. Find Python 3.10 or newer
set "PY="
for %%C in (python py) do (
    if not defined PY (
        %%C -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set "PY=%%C"
    )
)
if not defined PY (
    echo Python 3.10 or newer was not found.
    echo Install it from https://www.python.org/downloads/ and tick "Add Python to PATH", then run this file again.
    set RC=1
    goto :end
)

REM ---- 2. Create the virtual environment on first run
if exist "venv\Scripts\activate.bat" goto :activate
echo Creating a virtual environment (first run only)...
%PY% -m venv venv
if errorlevel 1 (
    echo Could not create the virtual environment.
    set RC=1
    goto :end
)

:activate
call "venv\Scripts\activate.bat"

REM ---- 3. Install requirements when new or changed
if not exist "venv\requirements.installed" goto :install
fc /b requirements.txt venv\requirements.installed >nul 2>&1
if errorlevel 1 goto :install
goto :ports

:install
echo Installing requirements...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Installing requirements failed. Check your internet connection and try again.
    set RC=1
    goto :end
)
copy /y requirements.txt venv\requirements.installed >nul

REM ---- 4. Is something left over on port 5000 (e.g. an earlier web app window)?
:ports
set "PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":5000 .*LISTENING"') do set "PID=%%P"
if not defined PID goto :launch
set "PNAME="
for /f "tokens=1 delims=," %%N in ('tasklist /FI "PID eq %PID%" /FO CSV /NH 2^>nul') do set "PNAME=%%~N"
echo.
echo Port 5000 is already in use by process %PID% (%PNAME%).
echo %PNAME% | findstr /I "python" >nul
if errorlevel 1 goto :notpython
choice /M "Stop this leftover Python process so the web app can use port 5000"
if errorlevel 2 goto :launch
taskkill /PID %PID% /F >nul 2>&1
echo Stopped process %PID%.
goto :launch

:notpython
echo That is not a Python process, so it is left alone. The web app will use the next free port.

REM ---- 5. Start the master launcher (pass any flags straight through)
:launch
echo.
python master.py %*
set RC=%ERRORLEVEL%

:end
echo.
pause
exit /b %RC%
