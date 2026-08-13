@echo off
setlocal enableextensions
if not exist .venv\Scripts\activate.bat (
    echo [ERROR] No .venv found. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat

echo.
echo === Starting API Health Monitor (SQLite, scheduler on, polls every 60s) ===
echo Server:  http://127.0.0.1:8000
echo Docs:    http://127.0.0.1:8000/docs
echo Metrics: http://127.0.0.1:8000/metrics
echo.
echo Press Ctrl+C to stop.
echo.

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

endlocal
