@echo off
rem Development mode: API with auto-reload on :8000, React dev server on :5173
cd /d "%~dp0backend"
start "API" cmd /k .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
cd /d "%~dp0frontend"
start "Frontend" cmd /k npm run dev
start "" http://localhost:5173
