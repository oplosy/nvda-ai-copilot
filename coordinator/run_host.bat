@echo off
rem Chrome discards the host stderr; keep it so startup failures are visible.
set "NVAI_DIR=%LOCALAPPDATA%\nvda-ai-copilot"
if not exist "%NVAI_DIR%" mkdir "%NVAI_DIR%"
rem Redirect first: %* ends in a digit (--parent-window=N), and "N>>" would redirect handle N, leaking the echo to stdout.
>> "%NVAI_DIR%\host-stderr.log" echo %DATE% %TIME% start %*
"%~dp0.venv\Scripts\python.exe" "%~dp0host.py" %* 2>> "%NVAI_DIR%\host-stderr.log"
