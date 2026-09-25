@echo off
rem Double-click: Ask AI button screenshots into demo_output\aibtn_redesign. Log: screens.log there.
setlocal
cd /d "%~dp0..\.."
set "OUTDIR=%CD%\..\demo_output"
if not exist "%OUTDIR%\aibtn_redesign" mkdir "%OUTDIR%\aibtn_redesign"
set "LOG=%OUTDIR%\aibtn_redesign\screens.log"
for /f "tokens=1 delims=v." %%a in ('node -v') do set NODEMAJ=%%a
if %NODEMAJ% GEQ 20 goto run
set "DEMO_PW_DIR=%OUTDIR%\.pw"
:run
node e2e\demo\aibtn_screens.mjs > "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
endlocal
