@echo off
setlocal enableextensions
if not exist .venv\Scripts\activate.bat (
    echo [ERROR] No .venv found. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat

echo.
echo === Running tests with coverage ===
echo.
python -m pytest tests/ --cov=app --cov-report=term-missing
echo.
echo Lint check:
python -m ruff check app tests
endlocal
