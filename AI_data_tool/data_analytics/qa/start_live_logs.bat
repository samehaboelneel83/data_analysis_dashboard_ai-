@echo off
REM Starts Datalytics and streams container logs into qa\live_logs\ so Claude can read them.
cd /d "%~dp0.."
docker compose up -d
start "backend logs"  /min cmd /c "docker logs -f --tail 200 datalytics_backend  > qa\live_logs\backend.log 2>&1"
start "frontend logs" /min cmd /c "docker logs -f --tail 200 datalytics_frontend > qa\live_logs\frontend.log 2>&1"
start "db logs"       /min cmd /c "docker logs -f --tail 50  datalytics_db       > qa\live_logs\db.log 2>&1"
echo.
echo Live logs are streaming to qa\live_logs\ . Close the minimized "logs" windows to stop.
echo App: http://localhost:3001
timeout /t 8
