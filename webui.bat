@echo off
setlocal EnableExtensions

rem Always resolve the project from this batch file, not from the caller's current directory.
set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"
cd /d "%CURRENT_DIR%"
if errorlevel 1 (
    echo ***** ERROR: failed to enter project directory: %CURRENT_DIR% *****
    pause
    exit /b 1
)

set "PYTHONPATH=%CURRENT_DIR%"
set "EXPECTED_STREAMLIT_VERSION=1.59.1"
set "PROJECT_PYTHON=%CURRENT_DIR%\.venv\Scripts\python.exe"

echo ***** Project root: %CURRENT_DIR% *****
echo ***** WebUI entry: %CURRENT_DIR%\webui\App.py *****

if not exist "%CURRENT_DIR%\webui\App.py" (
    echo ***** ERROR: webui\App.py was not found. *****
    echo ***** Your local checkout does not contain the new top-navigation WebUI entrypoint. *****
    echo ***** Run: git pull origin main *****
    pause
    exit /b 1
)

if not exist "%CURRENT_DIR%\webui\social_publishing_page.py" (
    echo ***** ERROR: webui\social_publishing_page.py was not found. *****
    echo ***** Your local checkout is missing the Social Publishing page. *****
    echo ***** Run: git pull origin main *****
    pause
    exit /b 1
)

rem set HF_ENDPOINT=https://hf-mirror.com

if not defined MPT_WEBUI_HOST set "MPT_WEBUI_HOST=127.0.0.1"
if not defined MPT_WEBUI_PORT set "MPT_WEBUI_PORT=8501"

rem A previous checkout may already have .venv, so "first run only" dependency setup
rem is not enough after git pull. Verify the locked Streamlit version required by the
rem top navigation and refresh the environment only when it is stale.
where uv >nul 2>nul
set "UV_AVAILABLE=%ERRORLEVEL%"

if exist "%PROJECT_PYTHON%" (
    "%PROJECT_PYTHON%" -c "import streamlit,sys; sys.exit(0 if streamlit.__version__ == '%EXPECTED_STREAMLIT_VERSION%' else 1)" >nul 2>nul
    if errorlevel 1 (
        if "%UV_AVAILABLE%"=="0" (
            echo ***** Existing .venv is stale. Syncing dependencies from uv.lock... *****
            uv sync --frozen
            if errorlevel 1 (
                echo ***** ERROR: dependency sync failed. *****
                pause
                exit /b 1
            )
        ) else (
            echo ***** WARNING: .venv does not contain Streamlit %EXPECTED_STREAMLIT_VERSION%, and uv is unavailable. *****
        )
    )
) else if "%UV_AVAILABLE%"=="0" (
    echo ***** Project .venv was not found. Creating it from uv.lock... *****
    uv sync --frozen
    if errorlevel 1 (
        echo ***** ERROR: dependency sync failed. *****
        pause
        exit /b 1
    )
)

set "STREAMLIT_CMD="
if exist "%PROJECT_PYTHON%" (
    set "STREAMLIT_CMD="%PROJECT_PYTHON%" -m streamlit"
    "%PROJECT_PYTHON%" -c "import streamlit; print('***** Streamlit version: ' + streamlit.__version__ + ' *****')"
) else if exist "%CURRENT_DIR%\lib\python\python.exe" (
    set "STREAMLIT_CMD="%CURRENT_DIR%\lib\python\python.exe" -m streamlit"
    "%CURRENT_DIR%\lib\python\python.exe" -c "import streamlit; print('***** Streamlit version: ' + streamlit.__version__ + ' *****')" 2>nul
) else if "%UV_AVAILABLE%"=="0" (
    set "STREAMLIT_CMD=uv run streamlit"
    uv run python -c "import streamlit; print('***** Streamlit version: ' + streamlit.__version__ + ' *****')" 2>nul
)

if not defined STREAMLIT_CMD (
    where streamlit >nul 2>nul
    if not errorlevel 1 (
        echo ***** Warning: using streamlit from PATH. Project .venv is recommended. *****
        set "STREAMLIT_CMD=streamlit"
        streamlit version
    )
)

if not defined STREAMLIT_CMD (
    echo ***** Neither project Python, uv, nor streamlit was found. Please install dependencies first. *****
    pause
    exit /b 1
)

set "SELECTED_WEBUI_PORT="
for /f %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$hostAddress=$null; foreach ($address in [Net.Dns]::GetHostAddresses($env:MPT_WEBUI_HOST)) { if ($address.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) { $hostAddress=$address; break } }; if ($null -eq $hostAddress) { exit 1 }; $preferred=[int]$env:MPT_WEBUI_PORT; $candidates=New-Object System.Collections.Generic.List[int]; $candidates.Add($preferred); foreach ($candidate in 8502..8599) { if ($candidate -ne $preferred) { $candidates.Add($candidate) } }; foreach ($port in $candidates) { $socket=[Net.Sockets.Socket]::new([Net.Sockets.AddressFamily]::InterNetwork,[Net.Sockets.SocketType]::Stream,[Net.Sockets.ProtocolType]::Tcp); try { $socket.Bind([Net.IPEndPoint]::new($hostAddress,$port)); $socket.Close(); Write-Output $port; exit 0 } catch { try { $socket.Close() } catch {} } }; exit 1"') do set "SELECTED_WEBUI_PORT=%%P"

if not defined SELECTED_WEBUI_PORT (
    echo ***** No available WebUI port found in 8501-8599 for %MPT_WEBUI_HOST%. *****
    echo ***** If Windows reports WinError 10013, check reserved ports: netsh interface ipv4 show excludedportrange protocol=tcp *****
    pause
    exit /b 1
)

if not "%SELECTED_WEBUI_PORT%"=="%MPT_WEBUI_PORT%" (
    echo ***** Port %MPT_WEBUI_PORT% is already in use. The NEW WebUI will use %SELECTED_WEBUI_PORT%. *****
    echo ***** Make sure you open the URL printed below instead of an older tab on %MPT_WEBUI_PORT%. *****
)
set "MPT_WEBUI_PORT=%SELECTED_WEBUI_PORT%"

echo ***** WebUI address: http://%MPT_WEBUI_HOST%:%MPT_WEBUI_PORT% *****
echo ***** Expected top navigation: Video Generation ^| Social Publishing *****
%STREAMLIT_CMD% run .\webui\App.py --server.address=%MPT_WEBUI_HOST% --server.port=%MPT_WEBUI_PORT% --browser.serverAddress=%MPT_WEBUI_HOST% --browser.gatherUsageStats=False --client.toolbarMode=minimal --logger.hideWelcomeMessage=True --server.showEmailPrompt=False --server.enableCORS=True
