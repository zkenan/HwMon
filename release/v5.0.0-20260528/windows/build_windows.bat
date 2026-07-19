@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo   HwMon v5.0.0-20260526  Windows 打包
echo ============================================================
echo.

set "ROOT=%~dp0..\..\"
set "VERSION=5.0.0"
set "TAG=v5.0.0-20260526"
set "OUTDIR=%~dp0"

:: ===== 客户端 =====
echo [1/2] 打包客户端 ...
cd /d "%ROOT%client"

"%ROOT%.venv\Scripts\pip.exe" install pyinstaller psutil wmi pywin32 requests pynvml -q -i https://pypi.tuna.tsinghua.edu.cn/simple

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

"%ROOT%.venv\Scripts\python.exe" -m PyInstaller --onefile --console ^
    --name=HwMonClient_%VERSION% ^
    --add-data="hardware_collector.py;." ^
    --add-data="process_monitor.py;." ^
    --add-data="config.py;." ^
    --hidden-import=wmi --hidden-import=psutil --hidden-import=pywin32 ^
    --hidden-import=pythoncom --hidden-import=win32service ^
    --hidden-import=win32serviceutil --hidden-import=win32event ^
    --hidden-import=servicemanager --hidden-import=requests --hidden-import=pynvml ^
    --clean service.py

if not exist "dist\HwMonClient_%VERSION%.exe" (
    echo !! 客户端打包失败 !!
    pause & exit /b 1
)

set "CPKG=%OUTDIR%HwMonClient_%TAG%_Win64"
if exist "%CPKG%" rmdir /s /q "%CPKG%"
mkdir "%CPKG%"
copy /y "dist\HwMonClient_%VERSION%.exe" "%CPKG%\" >nul
copy /y "config.json" "%CPKG%\" >nul

(echo @echo off & echo chcp 65001 ^>nul & echo HwMonClient_%VERSION%.exe & echo pause) > "%CPKG%\启动客户端.bat"
(echo @echo off & echo chcp 65001 ^>nul & echo HwMonClient_%VERSION%.exe --config & echo pause) > "%CPKG%\配置工具.bat"
(echo @echo off & echo chcp 65001 ^>nul & echo HwMonClient_%VERSION%.exe --install & echo pause) > "%CPKG%\安装为服务.bat"
(echo @echo off & echo chcp 65001 ^>nul & echo HwMonClient_%VERSION%.exe --uninstall & echo pause) > "%CPKG%\卸载服务.bat"

echo   OK  %CPKG%
echo.

:: ===== 服务端 =====
echo [2/2] 打包服务端 ...
cd /d "%ROOT%server"

"%ROOT%.venv\Scripts\pip.exe" install pyinstaller flask flask-cors waitress pymysql DBUtils cryptography openpyxl -q -i https://pypi.tuna.tsinghua.edu.cn/simple

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

"%ROOT%.venv\Scripts\python.exe" -m PyInstaller --onefile --console ^
    --name=HwMonServer_%VERSION% ^
    --add-data="templates;templates" ^
    --add-data="ai_analyzer.py;." ^
    --hidden-import=flask --hidden-import=flask_cors --hidden-import=waitress ^
    --hidden-import=pymysql --hidden-import=pymysql.cursors ^
    --hidden-import=DBUtils --hidden-import=DBUtils.pooled_db ^
    --hidden-import=cryptography --hidden-import=openpyxl --hidden-import=ai_analyzer ^
    --clean app.py

if not exist "dist\HwMonServer_%VERSION%.exe" (
    echo !! 服务端打包失败 !!
    pause & exit /b 1
)

set "SPKG=%OUTDIR%HwMonServer_%TAG%_Win64"
if exist "%SPKG%" rmdir /s /q "%SPKG%"
mkdir "%SPKG%"
copy /y "dist\HwMonServer_%VERSION%.exe" "%SPKG%\" >nul
copy /y "config.json" "%SPKG%\" >nul

(echo @echo off & echo chcp 65001 ^>nul & echo HwMonServer_%VERSION%.exe & echo pause) > "%SPKG%\启动服务端.bat"
(echo @echo off & echo chcp 65001 ^>nul & echo start /min HwMonServer_%VERSION%.exe & echo echo 服务端已在后台启动 & echo pause) > "%SPKG%\后台运行.bat"

echo   OK  %SPKG%
echo.

echo ============================================================
echo   全部完成!
echo ============================================================
echo.
echo   客户端: %CPKG%\
echo   服务端: %SPKG%\
echo.
pause
