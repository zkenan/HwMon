@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo 硬件监控客户端 - 一键部署工具 v4.0
echo ========================================
echo.
echo 此脚本将：
echo 1. 卸载旧版服务/停止旧进程
echo 2. 配置防火墙允许13301端口
echo 3. 安装 HwMon 服务(开机自启+完全后台)
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请以管理员身份运行此脚本！
    echo 右键此文件 -> "以管理员身份运行"
    pause
    exit /b 1
)

:: 1. 卸载旧版
echo [步骤 1/3] 清理旧版本...
:: 先尝试停止并卸载 HwMon 服务
sc query HwMon >nul 2>&1
if %errorlevel% equ 0 (
    echo   正在停止旧版服务...
    net stop HwMon >nul 2>&1
    sc delete HwMon >nul 2>&1
    echo   已卸载旧版服务
) else (
    echo   未找到 HwMon 服务
)
:: 再尝试停止进程模式
taskkill /F /IM HardwareMonitor.exe >nul 2>&1
if %errorlevel% equ 0 (
    echo   已停止旧版进程
) else (
    echo   未发现运行中的进程
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

:: 3. 安装 HwMon 服务
echo [步骤 3/3] 安装 HwMon Windows 服务...
echo   正在安装服务(需要管理员权限)...

set EXE_PATH=%~dp0HardwareMonitor.exe
set BIN_PATH="%EXE_PATH%" --service

sc create HwMon binPath= %BIN_PATH% start= auto DisplayName= "硬件监控客户端" >nul 2>&1
if %errorlevel% equ 0 (
    echo   ✓ 服务安装成功
) else (
    echo   ✗ 服务安装失败，请手动运行 HardwareMonitor.exe 选择 2 安装
    pause
    exit /b 1
)

:: 配置服务描述
sc description HwMon "硬件监控客户端服务，定时上报硬件信息到服务器，支持服务端主动采集" >nul 2>&1

:: 设置失败自动重启
sc failure HwMon reset= 86400 actions= restart/5000/restart/5000/restart/5000 >nul 2>&1

:: 启动服务
sc start HwMon >nul 2>&1
if %errorlevel% equ 0 (
    echo   ✓ 服务已启动
) else (
    echo   服务已安装，正在启动中...
)

echo.
echo ========================================
echo 部署完成！
echo ========================================
echo.
echo 验证方法：
echo 1. 打开服务管理器(services.msc)，查看 HwMon 服务
echo 2. 在服务端刷新页面，等待1-2分钟
echo 3. 点击"一键采集"，应显示成功
echo.
echo 卸载方法：
echo   运行 HardwareMonitor.exe 选择 3 卸载
echo   或执行: sc stop HwMon ^&^& sc delete HwMon
echo.
pause
