@echo off
rem Runs the whole app (API + built frontend) on http://127.0.0.1:8000
cd /d "%~dp0backend"
start "" http://127.0.0.1:8000
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
