@echo off
chcp 65001 >nul
rem Copies the coordinator to %LOCALAPPDATA%\Programs\nvda-ai-copilot and registers it with Chrome.
set "TARGET=%LOCALAPPDATA%\Programs\nvda-ai-copilot"
if not exist "%~dp0python\python.exe" (
  echo Önce zip dosyasını bir klasöre çıkarın, sonra install.bat dosyasını oradan çalıştırın.
  pause
  exit /b 1
)
echo NVDA AI Copilot koordinatörü kuruluyor. Chrome kapalı olmalı.
robocopy "%~dp0." "%TARGET%" /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo Dosyalar kopyalanamadı. Chrome'u kapatıp tekrar deneyin.
  pause
  exit /b 1
)
"%TARGET%\python\python.exe" "%TARGET%\app\install_host.py"
if errorlevel 1 (
  echo Chrome kaydı yapılamadı.
  pause
  exit /b 1
)
echo Kurulum tamam. Chrome'u açın, sonra API anahtarını NVDA menüsü, Tercihler, Ayarlar, NVDA AI Copilot bölümüne girin.
pause
