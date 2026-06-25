@echo off
echo ===================================================
echo   Generative Agents - One-Click Autostart
echo ===================================================

:: 优化 Ollama 运行性能（充分利用多核 CPU 与 RAM）
:: OLLAMA_NUM_PARALLEL=3: 允许 3 个 Agent 同时进行推理，避免排队
:: OLLAMA_MAX_LOADED_MODELS=2: 同时在内存中保留对话与嵌入模型，消除频繁切换导致的磁盘读取延迟
set OLLAMA_NUM_PARALLEL=3
set OLLAMA_MAX_LOADED_MODELS=2

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

echo Checking embedding model (nomic-embed-text)...
ollama list | findstr /i "nomic-embed-text" >nul 2>&1
if %errorlevel% neq 0 (
    echo Model nomic-embed-text is missing. Pulling model...
    ollama pull nomic-embed-text
) else (
    echo Model nomic-embed-text is ready.
)

:: Generate a safe timestamp (handling single-digit hours with spaces)
set "t=%time: =0%"
set "sim_name=sim_%date:~0,4%%date:~5,2%%date:~8,2%_%t:~0,2%%t:~3,2%%t:~6,2%"

echo.
echo [1/2] Launching Django Frontend Server...
start "Generative Agents - Frontend" cmd /k "cd /d G:\generative_agents\environment\frontend_server && ..\..\venv\Scripts\activate.bat && python manage.py runserver"

:: Wait 3 seconds for the frontend to spin up
timeout /t 3 /nobreak >nul

echo [2/2] Launching Reverie Backend Server (Auto-running 8640 steps)...
echo Running simulation: base_the_ville_isabella_maria_klaus -> %sim_name%
start "Generative Agents - Backend" cmd /k "cd /d G:\generative_agents\reverie\backend_server && ..\..\venv\Scripts\activate.bat && python reverie.py base_the_ville_isabella_maria_klaus %sim_name% 8640"

echo.
echo ===================================================
echo   All servers launched automatically!
echo   Open browser: http://localhost:8000/simulator_home
echo   (You can change the number of steps by editing start.bat)
echo ===================================================
pause
