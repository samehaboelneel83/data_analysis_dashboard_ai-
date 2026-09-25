@echo off
rem Double-click: regenerate the Arabic narrated demo.
rem   1) narration clips (edge-tts)   2) recording (Playwright)   3) merge (ffmpeg)
rem Edit e2e\demo\narration_ar.json to change the wording or the voice (_voice).
rem Output: demo_output\datalytics_demo_ar.mp4 + .srt      Log: demo_output\narration\run_ar.log
setlocal
cd /d "%~dp0..\.."
set "OUTDIR=%CD%\..\demo_output"
if not exist "%OUTDIR%\narration" mkdir "%OUTDIR%\narration"
set "LOG=%OUTDIR%\narration\run_ar.log"
set PYTHONIOENCODING=utf-8
set "PYTHONPATH=%OUTDIR%\.pytts"
echo Datalytics Arabic demo: see demo_output\narration\run_ar.log
echo == %DATE% %TIME% > "%LOG%"

if not exist "%OUTDIR%\.pytts\edge_tts" (
  echo installing edge-tts into demo_output\.pytts >> "%LOG%"
  python -m pip install --target "%OUTDIR%\.pytts" edge-tts --quiet >> "%LOG%" 2>&1
)
echo == 1. narration clips >> "%LOG%"
python e2e\demo\tts_ar.py clips >> "%LOG%" 2>&1
if errorlevel 1 goto fail

for /f "tokens=1 delims=v." %%a in ('node -v') do set NODEMAJ=%%a
if %NODEMAJ% GEQ 20 goto record
set "DEMO_PW_DIR=%OUTDIR%\.pw"
if exist "%DEMO_PW_DIR%\node_modules\playwright\package.json" goto record
set PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
call npm install --prefix "%DEMO_PW_DIR%" playwright@1.45.3 --no-audit --no-fund >> "%LOG%" 2>&1
:record
echo == 2. recording >> "%LOG%"
node e2e\demo\record_demo_ar.mjs >> "%LOG%" 2>&1
if errorlevel 1 goto fail

echo == 3. merge >> "%LOG%"
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo ffmpeg is not on PATH: the recording and timeline are in demo_output\narration. >> "%LOG%"
  echo Install it with: winget install ffmpeg   then run: python e2e\demo\merge_ar.py >> "%LOG%"
  goto done
)
python e2e\demo\merge_ar.py >> "%LOG%" 2>&1
if errorlevel 1 goto fail
goto done
:fail
echo FAILED, see the lines above >> "%LOG%"
:done
echo == finished %TIME% >> "%LOG%"
endlocal
