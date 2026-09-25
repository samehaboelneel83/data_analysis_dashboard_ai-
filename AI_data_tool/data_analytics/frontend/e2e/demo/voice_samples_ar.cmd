@echo off
rem Double-click: 10-second samples of both Egyptian voices -> demo_output\narration\sample_*.mp3
setlocal
cd /d "%~dp0..\.."
set "OUTDIR=%CD%\..\demo_output"
if not exist "%OUTDIR%\narration" mkdir "%OUTDIR%\narration"
set "LOG=%OUTDIR%\narration\tts.log"
set PYTHONIOENCODING=utf-8
set "PYTHONPATH=%OUTDIR%\.pytts"
if not exist "%OUTDIR%\.pytts\edge_tts" (
  echo installing edge-tts into demo_output\.pytts > "%LOG%"
  python -m pip install --target "%OUTDIR%\.pytts" edge-tts --quiet >> "%LOG%" 2>&1
)
python e2e\demo\tts_ar.py samples >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
endlocal
