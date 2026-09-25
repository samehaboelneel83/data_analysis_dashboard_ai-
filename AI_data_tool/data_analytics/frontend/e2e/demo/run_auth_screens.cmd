@echo off
rem Double-click: screenshots of the sign-in page into demo_output\auth_redesign\before (first run)
rem or ...\after (once "before" exists). Log: demo_output\auth_redesign\screens.log
setlocal
cd /d "%~dp0..\.."
set "OUTDIR=%CD%\..\demo_output"
if not exist "%OUTDIR%\auth_redesign" mkdir "%OUTDIR%\auth_redesign"
set "LOG=%OUTDIR%\auth_redesign\screens.log"
set PHASE=before
if exist "%OUTDIR%\auth_redesign\before\login_desktop_en.png" set PHASE=after
for /f "tokens=1 delims=v." %%a in ('node -v') do set NODEMAJ=%%a
if %NODEMAJ% GEQ 20 goto run
set "DEMO_PW_DIR=%OUTDIR%\.pw"
if exist "%DEMO_PW_DIR%\node_modules\playwright\package.json" goto run
set PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
call npm install --prefix "%DEMO_PW_DIR%" playwright@1.45.3 --no-audit --no-fund > "%LOG%" 2>&1
:run
echo phase %PHASE% > "%LOG%"
node e2e\demo\auth_screens.mjs %PHASE% >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
endlocal
