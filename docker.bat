@echo off
setlocal enableextensions
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker was not found on your PATH.
    echo Install Docker Desktop: https://www.docker.com/products/docker-desktop/
    echo Start Docker Desktop, then re-run this script.
    exit /b 1
)

echo.
echo === Building and starting the full stack ===
echo   app          : http://localhost:8000  (API + /metrics)
echo   Grafana      : http://localhost:3000  (admin / admin)
echo   Prometheus   : http://localhost:9090
echo   PostgreSQL   : localhost:5432
echo.
echo Press Ctrl+C to stop. First build may take a few minutes.
echo.
docker compose up --build

endlocal
