@echo off
REM ============================================================
REM  API Health Monitor - Windows setup & run helpers
REM  Use this instead of the bash-style commands in the README.
REM ============================================================
REM
REM  setup.bat   - create venv, install deps
REM  run.bat     - start the API server (SQLite, scheduler on)
REM  demo.bat    - seed ~24h of synthetic data for the dashboard
REM  test.bat    - run the test suite with coverage
REM  docker.bat  - build & run the full stack (needs Docker Desktop)
REM
REM  All commands use "python -m ..." so they work even when the
REM  bare pip/uvicorn/pytest commands aren't on your PATH.
REM ============================================================
