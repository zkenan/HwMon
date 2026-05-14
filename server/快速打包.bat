@echo off
chcp 65001 >nul
echo.
echo ========================================================================
echo   硬件监控系统服务端 - 快速打包脚本
echo ========================================================================
echo.
echo 正在检查环境...
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.7或更高版本
    pause
    exit /b 1
)

echo [✓] Python已安装
echo.

REM 清理旧的构建文件
echo 正在清理旧的构建文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo [✓] 清理完成
echo.

REM 执行打包
echo 开始打包，这可能需要几分钟时间...
echo.
python build_exe.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请检查上述错误信息
    pause
    exit /b 1
)

echo.
echo ========================================================================
echo   打包完成！
echo ========================================================================
echo.
echo 部署包位置: dist\HardwareMonitorServer_部署包
echo.
echo 下一步:
echo   1. 测试运行: dist\HardwareMonitorServer.exe
echo   2. 部署到服务器: 复制 dist\HardwareMonitorServer_部署包
echo   3. 启动服务: 双击 启动服务端.bat
echo.
pause
