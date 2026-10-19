@echo off
rem First-time setup: Python packages + frontend packages + frontend build.
cd /d "%~dp0backend"
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
cd /d "%~dp0frontend"
call npm install
call npm run build
echo.
echo Setup done. Run start.bat to open the app.
pause
