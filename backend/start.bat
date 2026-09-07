@echo off
echo ========================================
echo  Farm Assist - Backend Setup & Start
echo ========================================
echo.

cd /d "%~dp0"

echo [1/4] Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        exit /b 1
    )
    echo Virtual environment created.
) else (
    echo Virtual environment already exists.
)

echo.
echo [2/4] Checking virtual environment...
if not exist "venv\Scripts\python.exe" (
    echo The virtual environment is incomplete. Delete backend\venv and run this script again.
    exit /b 1
)
set "PYTHON=venv\Scripts\python.exe"
%PYTHON% -m pip --version
if errorlevel 1 (
    echo The virtual environment Python installation is not usable.
    exit /b 1
)

echo.
echo [3/4] Installing dependencies...
%PYTHON% -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo Dependency installation failed.
    exit /b 1
)

echo.
echo [4/4] Starting Farm Assist Backend...
echo.
echo ========================================
echo  Backend URL:  http://localhost:8000
echo  API Docs:     http://localhost:8000/docs
echo  ReDoc:        http://localhost:8000/redoc
echo  Frontend:     http://localhost:8000/
echo  LAN Access:   http://192.168.16.56:8000  (same Wi-Fi)
echo ========================================
echo.

%PYTHON% -m uvicorn app.main:app --app-dir "%~dp0" --host 0.0.0.0 --port 8000 --reload
