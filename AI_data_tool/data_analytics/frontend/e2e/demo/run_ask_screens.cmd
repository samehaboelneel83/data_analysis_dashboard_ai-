@echo off
rem Double-click: Ask AI screenshots into demo_output\ask_redesign\before (first run)
rem or ...\after (once "before" exists). Log: demo_output\ask_redesign\screens.log
setlocal
cd /d "%~dp0..\.."
set "OUTDIR=%CD%\..\demo_output"
if not exist "%OUTDIR%\ask_redesign" mkdir "%OUTDIR%\ask_redesign"
set "LOG=%OUTDIR%\ask_redesign\screens.log"
set PHASE=before
if exist "%OUTDIR%\ask_redesign\before\a_hero_en_dark.png" set PHASE=after
for /f "tokens=1 delims=v." %%a in ('node -v') do set NODEMAJ=%%a
if %NODEMAJ% GEQ 20 goto run
set "DEMO_PW_DIR=%OUTDIR%\.pw"
:run
echo phase %PHASE% > "%LOG%"
node e2e\demo\ask_screens.mjs %PHASE% >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
endlocal
