@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "ROOT=%CD%"
if not defined PYTHON_EXE set "PYTHON_EXE=python"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"

echo [World Cup Oracle] Starting local development environment...

if not exist ".env" (
  if exist ".env.example" (
    echo [setup] .env not found. Copying .env.example to .env
    copy ".env.example" ".env" >nul
  ) else (
    echo [warn] .env and .env.example are both missing.
  )
)

"%PYTHON_EXE%" --version >nul 2>nul
if errorlevel 1 (
  echo [error] Python command failed: %PYTHON_EXE%
  echo Please set PYTHON_EXE before running start.bat if Python is not on PATH.
  pause
  exit /b 1
)

where docker >nul 2>nul
if %ERRORLEVEL%==0 (
  docker info >nul 2>nul
  if !ERRORLEVEL!==0 (
    echo [db] Starting PostgreSQL container...
    docker compose up -d postgres
  ) else (
    echo [warn] Docker is installed but not available. Skipping PostgreSQL container startup.
  )
) else (
  echo [warn] Docker command not found. Assuming PostgreSQL is already running or not required.
)

echo [ports] Releasing backend/frontend dev ports if occupied...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ports=@(%BACKEND_PORT%,%FRONTEND_PORT%); foreach($port in $ports){ $conns=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; foreach($conn in $conns){ if($conn.OwningProcess -and $conn.OwningProcess -ne 0){ Write-Host ('[ports] Killing PID ' + $conn.OwningProcess + ' on port ' + $port); Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue } } }"

echo [backend] Starting FastAPI on http://127.0.0.1:%BACKEND_PORT%
start "WorldCup Oracle API" cmd /k "cd /d ""%ROOT%"" && set PYTHONPATH=backend && ""%PYTHON_EXE%"" -m uvicorn wcpa.api.server:app --host 127.0.0.1 --port %BACKEND_PORT%"

echo [frontend] Starting Vite on http://127.0.0.1:%FRONTEND_PORT%
start "WorldCup Oracle Frontend" cmd /k "cd /d ""%ROOT%\frontend"" && npm.cmd install && npm.cmd run dev -- --host 127.0.0.1 --port %FRONTEND_PORT%"

echo.
echo Started:
echo - API:      http://127.0.0.1:%BACKEND_PORT%
echo - Frontend: http://127.0.0.1:%FRONTEND_PORT%
echo.
echo Keep the opened backend/frontend windows running while using the app.
pause
