@echo off
rem Chrome discards the host stderr; keep it so startup failures are visible.
set "NVAI_DIR=%LOCALAPPDATA%\nvda-ai-copilot"
if not exist "%NVAI_DIR%" mkdir "%NVAI_DIR%"
rem Redirect first: %* ends in a digit (--parent-window=N), and "N>>" would redirect handle N, leaking the echo to stdout.
>> "%NVAI_DIR%\host-stderr.log" echo %DATE% %TIME% start %*
rem Dev checkout: .venv next to this file. Installed package (build_dist.py): embedded Python in ..\python.
set "NVAI_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%NVAI_PY%" set "NVAI_PY=%~dp0..\python\python.exe"
"%NVAI_PY%" "%~dp0host.py" %* 2>> "%NVAI_DIR%\host-stderr.log"
