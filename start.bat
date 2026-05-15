@echo off
chcp 65001 >nul
echo ============================================
echo   小红书 AI Studio — 可靠启动脚本
echo ============================================
echo.

:: 1. 干掉所有旧 streamlit 进程（僵尸清除）
echo [1/3] 清除旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do (
    echo   终止 PID %%a...
    taskkill /F /PID %%a /T >nul 2>&1
)
taskkill /F /IM streamlit.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: 2. 验证端口已释放
netstat -ano | findstr ":8501" | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo   [WARN] 端口 8501 仍被占用，强制杀...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a /T >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)
echo   [OK] 端口已释放

:: 3. 启动 Streamlit
echo.
echo [2/3] 启动 Streamlit...
cd /d "%~dp0"
start "" http://localhost:8501
echo [3/3] 浏览器已打开，等待服务就绪...
echo.
streamlit run app.py --server.port 8501 --server.headless true

pause
