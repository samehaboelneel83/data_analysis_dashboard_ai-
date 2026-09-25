@echo off
rem Double-click: the Arabic-UI demo with NO captions and NO sound.
rem Same steps and pacing as run_demo_ar.cmd (paced by the existing narration clips).
rem Output: demo_output\datalytics_demo_ar_clean.mp4 (needs ffmpeg; otherwise narration\raw_ar_clean.webm)
setlocal
cd /d "%~dp0..\.."
set "OUTDIR=%CD%\..\demo_output"
if not exist "%OUTDIR%\narration" mkdir "%OUTDIR%\narration"
set "LOG=%OUTDIR%\narration\run_ar_clean.log"
set DEMO_CLEAN=1
echo == %DATE% %TIME% > "%LOG%"
for /f "tokens=1 delims=v." %%a in ('node -v') do set NODEMAJ=%%a
if %NODEMAJ% GEQ 20 goto record
set "DEMO_PW_DIR=%OUTDIR%\.pw"
if exist "%DEMO_PW_DIR%\node_modules\playwright\package.json" goto record
set PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
call npm install --prefix "%DEMO_PW_DIR%" playwright@1.45.3 --no-audit --no-fund >> "%LOG%" 2>&1
:record
node e2e\demo\record_demo_ar.mjs >> "%LOG%" 2>&1
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo ffmpeg is not on PATH: the silent recording is demo_output\narration\raw_ar_clean.webm >> "%LOG%"
  goto done
)
ffmpeg -y -loglevel error -i "%OUTDIR%\narration\raw_ar_clean.webm" -filter_complex "[0:v]split[v0][v1];[v1]crop=8:8:1904:1072[p];[v0][p]overlay=1912:1072" -an -c:v libx264 -preset slow -crf 21 -pix_fmt yuv420p -movflags +faststart "%OUTDIR%\datalytics_demo_ar_clean.mp4" >> "%LOG%" 2>&1
:done
echo == finished %TIME% >> "%LOG%"
endlocal
