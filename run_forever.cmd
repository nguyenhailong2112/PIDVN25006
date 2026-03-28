@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=py -3"

echo [PIDVN25006] Starting forever supervisor...
echo [PIDVN25006] Project root: %~dp0
echo [PIDVN25006] Logs: outputs\runtime\supervisor\supervisor.log

%PYTHON_EXE% tools\run_forever.py %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [PIDVN25006] Supervisor exited with code %EXIT_CODE%.
) else (
    echo [PIDVN25006] Supervisor stopped cleanly.
)

exit /b %EXIT_CODE%
