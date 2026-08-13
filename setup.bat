@echo off
setlocal enableextensions
echo.
echo === API Health Monitor: setup ===
echo.

REM Try the Windows "py" launcher first (recommended), fall back to "python".
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3.11"
    goto :found
)
where python >nul 2>nul
if %errorlevel%==0 (
    set "PY=python"
    goto :found
)

echo [ERROR] Python 3.11 was not found on your PATH.
echo.
echo Fix: install Python 3.11 from https://www.python.org/downloads/windows/
echo   IMPORTANT: in the installer, tick "Add python.exe to PATH".
echo   Then close and reopen this terminal and re-run setup.bat.
echo.
exit /b 1

:found
echo Using Python: %PY%
%PY% --version

echo.
echo Creating virtual environment (.venv)...
%PY% -m venv .venv
if %errorlevel% neq 0 (
    echo [ERROR] venv creation failed.
    exit /b 1
)

echo.
echo Upgrading pip inside the venv...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo.
echo Installing dependencies...
python -m pip install -r requirements-dev.txt
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Full install failed (often psycopg2-binary on some Windows setups).
    echo That's OK for local SQLite use. Trying runtime-only deps without psycopg2...
    echo.
    python -m pip install fastapi==0.137.2 "uvicorn[standard]==0.34.0" SQLAlchemy==2.0.52 aiosqlite==0.22.1 httpx==0.28.1 pydantic==2.11.0 pydantic-settings==2.14.1 APScheduler==3.11.3 prometheus-client==0.21.1 pytest==9.1.1 pytest-asyncio==1.4.0 pytest-cov==7.1.0 ruff==0.16.2
    if %errorlevel% neq 0 (
        echo [ERROR] dependency installation failed.
        exit /b 1
    )
    echo.
    echo [OK] Installed without psycopg2-binary. Local SQLite mode will work.
    echo      For Docker/Postgres mode, psycopg2 is bundled in the image already.
)

echo.
echo === Setup complete! ===
echo.
echo Next steps:
echo   run.bat     - start the API server
echo   demo.bat    - seed demo data for the Grafana dashboard
echo   test.bat    - run tests
echo.
endlocal
