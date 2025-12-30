@echo off
REM ============================================================================
REM Library RAG MCP Server - Development Environment Setup (Windows)
REM ============================================================================
REM This script sets up and starts the development environment for the
REM Library RAG MCP Server project.
REM
REM Usage:
REM   init.bat           - Full setup (venv, deps, docker, verify)
REM   init.bat --quick   - Quick start (docker only, assumes deps installed)
REM
REM Requirements:
REM   - Python 3.10+
REM   - Docker Desktop
REM   - Git
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ============================================
echo Library RAG MCP Server - Setup
echo ============================================
echo.

REM Check for quick mode
set QUICK_MODE=false
if "%1"=="--quick" set QUICK_MODE=true

REM Check prerequisites
echo Checking prerequisites...

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    exit /b 1
)
echo [OK] Python is installed

where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not installed or not in PATH
    exit /b 1
)
echo [OK] Docker is installed

REM Check Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running. Please start Docker Desktop.
    exit /b 1
)
echo [OK] Docker is running

if "%QUICK_MODE%"=="false" (
    echo.
    echo Setting up Python virtual environment...

    if not exist "venv" (
        echo Creating virtual environment...
        python -m venv venv
    )
    echo [OK] Virtual environment exists

    REM Activate venv
    call venv\Scripts\activate.bat
    echo [OK] Virtual environment activated

    echo.
    echo Installing Python dependencies...
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo [OK] Dependencies installed
)

REM Check for .env file
echo.
echo Checking environment configuration...
if not exist ".env" (
    if exist ".env.example" (
        echo [WARN] .env file not found. Copying from .env.example...
        copy .env.example .env >nul
        echo [WARN] Please edit .env and add your MISTRAL_API_KEY
    ) else (
        echo [ERROR] .env file not found. Create it with MISTRAL_API_KEY=your-key
        exit /b 1
    )
) else (
    echo [OK] .env file exists
)

REM Start Docker services
echo.
echo Starting Docker services (Weaviate + Transformers)...
docker compose up -d

REM Wait for Weaviate to be ready
echo.
echo Waiting for Weaviate to be ready...
set RETRY_COUNT=0
set MAX_RETRIES=30

:wait_loop
curl -s http://localhost:8080/v1/.well-known/ready >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Weaviate is ready!
    goto weaviate_ready
)

set /a RETRY_COUNT+=1
if %RETRY_COUNT% geq %MAX_RETRIES% (
    echo [ERROR] Weaviate failed to start. Check docker compose logs.
    exit /b 1
)

echo|set /p="."
timeout /t 2 /nobreak >nul
goto wait_loop

:weaviate_ready

REM Initialize Weaviate schema
if exist "schema_v2.py" (
    echo.
    echo Initializing Weaviate schema...
    python schema_v2.py 2>nul
    echo [OK] Schema initialized
)

echo.
echo ============================================
echo Setup Complete!
echo ============================================
echo.
echo Services running:
echo   - Weaviate:     http://localhost:8080
echo   - Transformers: Running (internal)
echo.
echo Quick commands:
echo   - Run MCP server:    python mcp_server.py
echo   - Run Flask app:     python flask_app.py
echo   - Run tests:         pytest tests\ -v
echo   - Type check:        mypy . --strict
echo   - Stop services:     docker compose down
echo.
echo Configuration:
echo   - Edit .env file to configure API keys and settings
echo   - See MCP_README.md for MCP server documentation
echo.
echo Note: For MCP server, configure Claude Desktop with:
echo   %%APPDATA%%\Claude\claude_desktop_config.json
echo.

endlocal
