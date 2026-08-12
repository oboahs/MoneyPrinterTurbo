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

set "PROJECT_PYTHON=%CURRENT_DIR%\.venv\Scripts\python.exe"
where uv >nul 2>nul
if not errorlevel 1 (
    echo ***** Syncing MoneyPrinterTurbo from uv.lock... *****
    uv sync --frozen
    if errorlevel 1 (
        echo [ERROR] uv sync failed.
        pause
        exit /b 1
    )
) else if not exist "%PROJECT_PYTHON%" (
    echo [ERROR] uv is required for the first local setup but was not found.
    echo Install uv from: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
) else (
    echo ***** WARNING: uv was not found; using the existing .venv. *****
)

if not exist "%PROJECT_PYTHON%" (
    echo [ERROR] Project Python was not created: %PROJECT_PYTHON%
    pause
    exit /b 1
)

echo ============================================================
echo MoneyPrinterTurbo - Local Social Publishing Runtime Setup
echo ============================================================
echo This installs a separate uploader runtime under:
echo   storage\social-auto-upload\
echo It does NOT modify the MoneyPrinterTurbo project environment.
echo.

"%PROJECT_PYTHON%" "%CURRENT_DIR%\scripts\setup_social_auto_upload.py"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [OK] Local social publishing runtime is ready.
    echo Restart webui.bat, then open Social Publishing.
) else (
    echo [ERROR] Setup failed. Review the messages above.
)

pause
exit /b %EXIT_CODE%
