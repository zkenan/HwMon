@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo 硬件监控客户端 - 一键部署工具
echo ========================================
echo.
echo 此脚本将：
echo 1. 停止旧版客户端进程
echo 2. 配置防火墙允许13301端口
echo 3. 启动新版客户端（自动安装+后台运行）
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请以管理员身份运行此脚本！
    echo 右键此文件 -> "以管理员身份运行"
    pause
    exit /b 1
)

:: 1. 停止旧版进程
echo [步骤 1/3] 停止旧版客户端...
taskkill /F /IM HardwareMonitor.exe >nul 2>&1
if %errorlevel% equ 0 (
    echo   已停止旧版客户端
) else (
    echo   未发现运行中的客户端（可能未安装）
)
timeout /t 2 >nul

:: 2. 配置防火墙
echo [步骤 2/3] 配置防火墙...
netsh advfirewall firewall delete rule name="硬件监控客户端-13301" >nul 2>&1
netsh advfirewall firewall add rule name="硬件监控客户端-13301" dir=in action=allow protocol=TCP localport=13301 profile=any >nul 2>&1
if %errorlevel% equ 0 (
    echo   防火墙规则已配置：允许TCP 13301端口入站
) else (
    echo   警告：防火墙配置可能失败
)

:: 3. 启动新版客户端
echo [步骤 3/3] 启动新版客户端...
start "" "%~dp0HardwareMonitor.exe" --silent

if %errorlevel% equ 0 (
    echo   客户端已在后台启动
) else (
    echo   错误：启动失败，请检查HardwareMonitor.exe是否存在
)

echo.
echo ========================================
echo 部署完成！
echo ========================================
echo.
echo 验证方法：
echo 1. 打开任务管理器，查看 HardwareMonitor.exe 进程
echo 2. 在服务端刷新页面，等待1-2分钟
echo 3. 点击"一键采集"，应显示成功
echo.
pause
