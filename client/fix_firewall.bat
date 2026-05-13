@echo off
chcp 65001 >nul
echo ========================================
echo 硬件监控客户端 - 防火墙配置工具
echo ========================================
echo.
echo 正在配置Windows防火墙，允许13301端口入站连接...
echo.

netsh advfirewall firewall add rule name="硬件监控客户端-13301" dir=in action=allow protocol=TCP localport=13301 profile=any >nul 2>&1

if %errorlevel% equ 0 (
    echo [成功] 已添加防火墙规则：允许TCP 13301端口入站
) else (
    echo [失败] 添加防火墙规则失败
    echo 请以管理员身份运行此脚本
)

echo.
echo ========================================
echo 完成！按任意键退出...
pause >nul
