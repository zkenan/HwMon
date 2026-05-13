@echo off
chcp 65001 >nul
color 0A
cd /d "%~dp0"

echo ============================================
echo   硬件监控系统服务端部署工具 v1.0.0
echo ============================================
echo.

echo [1/3] 检查端口 5000 占用...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000"') do (
    echo   端口5000被占用 (PID: %%a)，正在释放...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 2 /nobreak >nul
)

echo.
echo [2/3] 配置防火墙...
netsh advfirewall firewall delete rule name="硬件监控系统服务端-5000" >nul 2>&1
netsh advfirewall firewall add rule name="硬件监控系统服务端-5000" dir=in action=allow protocol=TCP localport=5000 >nul 2>&1
echo   端口 5000 已放行

echo.
echo [3/3] 启动服务端...
echo.
echo ============================================
echo   访问地址: http://localhost:5000
echo   局域网访问: http://YOUR_IP:5000
echo ============================================
echo.
echo   按 Ctrl+C 停止服务端
echo ============================================
echo.

HardwareMonitorServer.exe

pause
