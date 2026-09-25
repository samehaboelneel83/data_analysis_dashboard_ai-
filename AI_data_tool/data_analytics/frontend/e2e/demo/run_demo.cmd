@echo off
rem Double-click to record the Datalytics demo video.
rem Output: <data_analytics>\demo_output\datalytics_demo.webm (+ .mp4 if ffmpeg is on PATH)
rem Log:    <data_analytics>\demo_output\run.log
setlocal
cd /d "%~dp0..\.."
set "OUTDIR=%CD%\..\demo_output"
if not exist "%OUTDIR%" mkdir "%OUTDIR%"
set "LOG=%OUTDIR%\run.log"
echo Recording the Datalytics demo... (log: demo_output\run.log)

for /f "tokens=1 delims=v." %%a in ('node -v') do set NODEMAJ=%%a
echo node major version: %NODEMAJ% > "%LOG%"

if %NODEMAJ% GEQ 20 goto run
rem Node older than 20: use a private, Node-18-compatible playwright (no browser download;
rem the script uses the installed Chromium or falls back to Edge).
set "DEMO_PW_DIR=%OUTDIR%\.pw"
if exist "%DEMO_PW_DIR%\node_modules\playwright\package.json" goto run
echo installing playwright@1.45.3 into demo_output\.pw >> "%LOG%"
set PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
call npm install --prefix "%DEMO_PW_DIR%" playwright@1.45.3 --no-audit --no-fund >> "%LOG%" 2>&1

:run
node e2e\demo\record_demo.mjs >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
type "%LOG%"
endlocal
