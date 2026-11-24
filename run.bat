@echo off
setlocal EnableExtensions

title AI-HOS Launcher (v2.0)
cd /d "%~dp0"

echo ============================================================================
echo   AI-HOS v2.0 - AI Hospital Operating System Launcher
echo   Clinical Documentation AI (:8000) + Prior Auth Engine (:8001) + UI (:5173)
echo ============================================================================
echo.

:: 1. Verify Python is installed
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Please install Python 3.11+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 2. Verify Node.js / npm is installed
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js / npm is not installed or not in PATH.
    echo         Please install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)

:: 3. Setup Python virtual environment on first run
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating Python virtual environment ^(.venv^)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create Python virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Python virtual environment found ^(.venv^).
)

:: 4. Install Python backend dependencies if missing
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, aiosqlite, structlog, openai" >nul 2>&1
if errorlevel 1 (
    echo [2/4] Installing Python dependencies for both microservices...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r "ai-hos\services\clinical-doc-ai\requirements.txt" -r "ai-hos\services\prior-auth-engine\requirements.txt"
    if errorlevel 1 (
        echo [ERROR] Failed to install Python dependencies.
        pause
        exit /b 1
    )
) else (
    echo [2/4] Python backend dependencies already installed.
)

:: 5. Install React frontend dependencies if missing
if not exist "ai-hos\frontend\node_modules" (
    echo [3/4] Installing React frontend packages ^(first run only^)...
    pushd "ai-hos\frontend"
    call npm.cmd install
    if errorlevel 1 (
        popd
        echo [ERROR] Failed to install frontend dependencies.
        pause
        exit /b 1
    )
    popd
) else (
    echo [3/4] Frontend packages already installed.
)

:: 6. Launch all 3 services in dedicated windows
echo [4/4] Starting AI-HOS microservices and dashboard...
echo.

start "AI-HOS Clinical Doc AI (Port 8000)" cmd /k "cd /d "%~dp0ai-hos\services\clinical-doc-ai" && "%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

start "AI-HOS Prior Auth Engine (Port 8001)" cmd /k "cd /d "%~dp0ai-hos\services\prior-auth-engine" && "%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload"

start "AI-HOS Dashboard (Port 5173)" cmd /k "cd /d "%~dp0ai-hos\frontend" && npm.cmd run dev"

echo Waiting for services to initialize...
timeout /t 4 /nobreak >nul

echo.
echo ============================================================================
echo   AI-HOS is running!
echo.
echo   Dashboard UI       : http://localhost:5173
echo   Clinical Doc AI    : http://localhost:8000/docs
echo   Prior Auth Engine  : http://localhost:8001/docs
echo.
echo   Tip: Run stop.bat (or close the 3 spawned windows) to stop all services.
echo ============================================================================
echo.

start "" "http://localhost:5173"
endlocal
