@echo off
chcp 65001 >nul
rem Unregisters the native host and deletes this folder. The saved API key and logs stay in
rem %LOCALAPPDATA%\nvda-ai-copilot; the NVDA settings panel can delete the key.
"%~dp0python\python.exe" "%~dp0app\install_host.py" --uninstall
if errorlevel 1 (
  echo Chrome kaydı silinemedi.
  pause
  exit /b 1
)
echo Koordinatör kaldırıldı. Kayıtlı API anahtarını NVDA ayarlarından silebilirsiniz.
pause
rem This script lives in the folder it deletes: leave the batch context first.
(goto) 2>nul & rmdir /s /q "%~dp0"
