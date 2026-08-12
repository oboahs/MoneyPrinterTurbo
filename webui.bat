@echo off
setlocal EnableExtensions

set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"
cd /d "%CURRENT_DIR%"
if errorlevel 1 (
    echo [ERROR] Failed to enter project directory: %CURRENT_DIR%
    pause
    exit /b 1
)

if not exist "%CURRENT_DIR%\scripts\run_webui.py" (
    echo [ERROR] scripts\run_webui.py was not found.
    echo Run: git pull origin main
    pause
    exit /b 1
)

set "PROJECT_PYTHON=%CURRENT_DIR%\.venv\Scripts\python.exe"
where uv >nul 2>nul
if not errorlevel 1 (
    echo ***** Syncing this checkout from uv.lock... *****
    uv sync --frozen
    if errorlevel 1 (
        echo [ERROR] uv sync failed.
        pause
        exit /b 1
    )
) else if not exist "%PROJECT_PYTHON%" (
    echo [ERROR] uv is required for the first local run but was not found.
    echo Install uv from: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
) else (
    echo ***** WARNING: uv was not found; using the existing .venv without dependency sync. *****
)

if not exist "%PROJECT_PYTHON%" (
    echo [ERROR] Project Python was not created: %PROJECT_PYTHON%
    pause
    exit /b 1
)

"%PROJECT_PYTHON%" "%CURRENT_DIR%\scripts\run_webui.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] WebUI exited with code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
