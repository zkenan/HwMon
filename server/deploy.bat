@echo off
chcp 65001 >nul
echo ====================================
echo 硬件监控系统服务端部署工具
echo ====================================
echo.

cd /d "%~dp0"

echo [1/4] 检查端口占用...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000"') do (
    echo  发现端口5000被占用(PID: %%a)，正在释放...
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo [2/4] 配置防火墙...
netsh advfirewall firewall add rule name="硬件监控系统服务端" dir=in action=allow protocol=TCP localport=5000 >nul 2>&1
echo  已放行端口5000

echo.
echo [3/4] 启动服务端...
echo  访问地址: http://localhost:5000
echo  局域网地址: http://YOUR_IP:5000
echo.
echo ====================================
echo 按 Ctrl+C 停止服务端
echo ====================================
echo.

HardwareMonitorServer.exe

pause
