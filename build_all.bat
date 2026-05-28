@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title HwMon v5.0.0 一键打包

echo ============================================================
echo   HwMon v5.0.0  一键打包 (Windows)
echo ============================================================
echo.

set "ROOT=%~dp0"

:: 优先用 .venv 里的 Python
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "!PYTHON!" (
    set "PYTHON=python.exe"
)

echo  使用: !PYTHON!
echo.

:: 执行 Python 打包脚本
"!PYTHON!" "%ROOT%build_all.py"

if errorlevel 1 (
    echo.
    echo 打包失败，请检查上方错误信息
    pause
    exit /b 1
)

echo.
pause
