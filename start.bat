@echo off
echo ===================================================
echo   Generative Agents - One-Click Autostart
echo ===================================================

:: Ollama performance settings (also set permanently via setx)
:: OLLAMA_NUM_PARALLEL=3: Allow 3 agents to run LLM inference in parallel
:: OLLAMA_MAX_LOADED_MODELS=2: Keep chat + embedding models loaded simultaneously
:: OLLAMA_KEEP_ALIVE=-1: Never unload models from VRAM (avoid cold start)
set OLLAMA_NUM_PARALLEL=3
set OLLAMA_MAX_LOADED_MODELS=2
set OLLAMA_KEEP_ALIVE=-1

echo Cleaning up any previously running servers...
powershell -Command "Get-CimInstance Win32_Process -Filter \"name = 'python.exe'\" | Where-Object { $_.CommandLine -like '*manage.py*' -or $_.CommandLine -like '*reverie.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Cleanup complete.

echo.
echo [Checking Dependencies]
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Ollama is not installed or not in the system PATH.
    echo Please install Ollama from https://ollama.com/ and try again.
    pause
    exit /b 1
)

echo Checking Ollama server status...
powershell -Command "try { (New-Object System.Net.Sockets.TcpClient).Connect('localhost', 11434); exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 (
    echo Ollama server is not running. Starting Ollama in the background...
    start "Ollama Server" /min cmd /c ollama serve
    echo Waiting for Ollama server to spin up...
    :wait_ollama
    timeout /t 2 /nobreak >nul
    powershell -Command "try { (New-Object System.Net.Sockets.TcpClient).Connect('localhost', 11434); exit 0 } catch { exit 1 }" >nul 2>&1
    if %errorlevel% neq 0 (
        goto wait_ollama
    )
    echo Ollama server started successfully!
) else (
    echo Ollama server is already running.
)

echo.
echo [Checking Ollama Configuration]
echo ---------------------------------------------------
echo   OLLAMA_NUM_PARALLEL      = %OLLAMA_NUM_PARALLEL%
echo   OLLAMA_KEEP_ALIVE        = %OLLAMA_KEEP_ALIVE%
echo   OLLAMA_MAX_LOADED_MODELS = %OLLAMA_MAX_LOADED_MODELS%
echo ---------------------------------------------------

:: Auto-fix missing settings
if "%OLLAMA_NUM_PARALLEL%"=="" (
    echo [WARN] OLLAMA_NUM_PARALLEL not set, defaulting to 1. Agents will queue!
    set OLLAMA_NUM_PARALLEL=3
    echo         Auto-fixed: OLLAMA_NUM_PARALLEL=3
)
if "%OLLAMA_KEEP_ALIVE%"=="" (
    echo [WARN] OLLAMA_KEEP_ALIVE not set. Models may unload during idle!
    set OLLAMA_KEEP_ALIVE=-1
    echo         Auto-fixed: OLLAMA_KEEP_ALIVE=-1
)

echo.
echo [Checking Models]
echo Checking chat model (qwen2.5:7b)...
ollama list | findstr /i "qwen2.5:7b" >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Chat model qwen2.5:7b is missing. Pulling model...
    ollama pull qwen2.5:7b
) else (
    echo   [OK] qwen2.5:7b
)

echo Checking embedding model (nomic-embed-text)...
ollama list | findstr /i "nomic-embed-text" >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Embedding model nomic-embed-text is missing. Pulling model...
    ollama pull nomic-embed-text
) else (
    echo   [OK] nomic-embed-text
)

echo.
echo [GPU Status]
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu --format=csv,noheader 2>nul
if %errorlevel% neq 0 (
    echo [WARN] nvidia-smi not found. Cannot check GPU status.
)

echo.
echo [Currently Loaded Models]
ollama ps

:: Generate a safe timestamp using PowerShell to avoid locale-dependent spaces or special characters
for /f %%i in ('powershell -NoProfile -Command Get-Date -Format yyyyMMdd_HHmmss') do set "sim_name=sim_%%i"


echo.
echo [1/2] Launching Django Frontend Server...
start "Generative Agents - Frontend" cmd /k "cd /d G:\generative_agents\environment\frontend_server && ..\..\venv\Scripts\activate.bat && python manage.py runserver"

:: Wait 3 seconds for the frontend to spin up
timeout /t 3 /nobreak >nul

echo [2/2] Launching Reverie Backend Server (Auto-running 8640 steps)...
echo Running simulation: base_the_ville_isabella_maria_klaus -^> %sim_name%
start "Generative Agents - Backend" cmd /k "cd /d G:\generative_agents\reverie\backend_server && ..\..\venv\Scripts\activate.bat && python reverie.py base_the_ville_isabella_maria_klaus %sim_name% 8640"

echo.
echo ===================================================
echo   All servers launched automatically!
echo   Open browser: http://localhost:8000/simulator_home
echo   (You can change the number of steps by editing start.bat)
echo ===================================================
pause
