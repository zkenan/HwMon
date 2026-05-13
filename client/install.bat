@echo off
chcp 65001 >nul
REM 硬件监控客户端 - 一键安装脚本(管理员权限)

echo ========================================
echo   硬件监控客户端 - 安装程序
echo ========================================
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [√] 已获得管理员权限
) else (
    echo [×] 需要管理员权限,正在请求...
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b
)

echo.
echo 请选择安装选项:
echo 1. 完整安装(安装依赖 + 配置 + 开机自启)
echo 2. 仅安装依赖
echo 3. 仅配置开机自启
echo 4. 卸载
echo 5. 退出
echo.

set /p choice="请输入选项 (1-5): "

if "%choice%"=="1" goto install_full
if "%choice%"=="2" goto install_deps
if "%choice%"=="3" goto install_autostart
if "%choice%"=="4" goto uninstall
if "%choice%"=="5" goto end

:install_full
echo.
echo ========================================
echo   步骤 1: 安装Python依赖
echo ========================================
pip install -r requirements.txt
if %errorLevel% neq 0 (
    echo [×] 依赖安装失败
    pause
    exit /b
)
echo [√] 依赖安装完成

echo.
echo ========================================
echo   步骤 2: 生成配置文件
echo ========================================
if not exist config.json (
    python client.py --config >nul 2>&1
    echo [√] 已创建默认配置文件 config.json
    echo.
    echo 请编辑 config.json 修改服务器地址!
    pause
) else (
    echo [√] 配置文件已存在
)

echo.
echo ========================================
echo   步骤 3: 设置开机自启
echo ========================================
python client.py --install
echo [√] 安装完成!

echo.
echo ========================================
echo   安装成功!
echo ========================================
echo 程序将在后台运行
echo 日志文件: client.log
echo 配置文件: config.json
echo.
pause
goto end

:install_deps
echo.
echo 正在安装Python依赖...
pip install -r requirements.txt
if %errorLevel% equ 0 (
    echo [√] 依赖安装完成
) else (
    echo [×] 依赖安装失败
)
pause
goto end

:install_autostart
echo.
echo 正在设置开机自启...
python client.py --install
pause
goto end

:uninstall
echo.
echo 正在卸载...
python client.py
echo.
echo 如需完全删除,请手动删除以下文件:
echo - client.py
echo - hardware_collector.py
echo - config.py
echo - config.json
echo - client.log
echo.
pause
goto end

:end
