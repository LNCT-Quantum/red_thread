@echo off
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is required. Install the current LTS from https://nodejs.org/ and run this file again.
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo npm is missing. Reinstall Node.js from https://nodejs.org/.
  pause
  exit /b 1
)
if not exist node_modules (
  echo Installing frontend packages...
  call npm ci
  if errorlevel 1 (
    echo Installation failed. Check the message above.
    pause
    exit /b 1
  )
)
echo Starting Red Thread...
start "Red Thread Dev Server" cmd /k npm run dev -- --host 127.0.0.1
timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:5173/"
echo Leave the server window open while playing.
