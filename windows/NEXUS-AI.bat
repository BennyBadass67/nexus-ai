@echo off
chcp 65001 >nul
cd /d "%~dp0"
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama er ikke installert. Apner nedlastingssiden. Installer, og start NEXUS-AI igjen.
  start https://ollama.com/download/windows
  pause
  exit /b
)
rem Start Ollama hvis den ikke kjorer
powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/version -TimeoutSec 2 | Out-Null}catch{Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden}"
rem Start NEXUS-backend uten konsollvindu
start "" "%~dp0python\pythonw.exe" "%~dp0backend\run.py"
rem Vent til backend svarer (maks 20 sek)
powershell -NoProfile -Command "for($i=0;$i -lt 40;$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/api/health -TimeoutSec 1 | Out-Null; exit 0}catch{Start-Sleep -Milliseconds 500}}; exit 1"
if errorlevel 1 (
  echo NEXUS startet ikke. Se loggen: %USERPROFILE%\.nexus-ai\nexus.log
  pause
  exit /b
)
rem Apne som appvindu (Edge finnes pa alle Windows 10/11), ellers vanlig nettleser
start "" msedge --app=http://127.0.0.1:8765 2>nul || start http://127.0.0.1:8765
