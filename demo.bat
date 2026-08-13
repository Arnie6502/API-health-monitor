@echo off
setlocal enableextensions
if not exist .venv\Scripts\activate.bat (
    echo [ERROR] No .venv found. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat

echo.
echo === Seeding ~24h of synthetic demo data for the Grafana dashboard ===
echo (2 endpoints x 1440 checks, with 2 injected failure bursts + resolved alerts)
echo.
python -m app.cli seed-demo
echo.
echo Done. Now run 'docker.bat' (or point Grafana at /metrics) and refresh the dashboard.
endlocal
