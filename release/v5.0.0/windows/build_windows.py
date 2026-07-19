# -*- coding: utf-8 -*-
"""
HwMon v5.0.0-20260526  Windows 一键打包脚本
运行: .venv\Scripts\python.exe build_all.py
"""
import os
import sys
import subprocess
import shutil
import json
from pathlib import Path

VERSION = "5.0.0"
TAG = "v5.0.0-20260526"
ROOT = Path(__file__).parent.resolve()
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
VENV_PIP = ROOT / ".venv" / "Scripts" / "pip.exe"

def run(cmd, cwd=None):
    """执行命令并打印输出"""
    print(f"  > {cmd[0]} ...")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        if r.stderr:
            # 只打印最后500字符的错误
            lines = r.stderr.strip().splitlines()
            for line in lines[-10:]:
                print(f"    {line}")
        return False
    return True


def build_client():
    print()
    print("=" * 60)
    print("  [1/2] 打包 Windows 客户端")
    print("=" * 60)

    client_dir = ROOT / "client"

    # 安装依赖
    print("  安装依赖...")
    run([str(VENV_PIP), "install", "pyinstaller", "psutil", "wmi", "pywin32", "requests", "pynvml",
         "-q", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])

    # 清理
    for d in ["build", "dist"]:
        p = client_dir / d
        if p.exists():
            shutil.rmtree(p)

    # 打包
    exe_name = f"HwMonClient_{VERSION}"
    print(f"  PyInstaller 打包 {exe_name}.exe ...")
    ok = run([
        str(VENV_PY), "-m", "PyInstaller",
        "--onefile", "--console",
        f"--name={exe_name}",
        "--add-data=hardware_collector.py;.",
        "--add-data=process_monitor.py;.",
        "--add-data=config.py;.",
        "--hidden-import=wmi",
        "--hidden-import=psutil",
        "--hidden-import=pywin32",
        "--hidden-import=pythoncom",
        "--hidden-import=win32service",
        "--hidden-import=win32serviceutil",
        "--hidden-import=win32event",
        "--hidden-import=servicemanager",
        "--hidden-import=requests",
        "--hidden-import=pynvml",
        "--clean",
        "service.py",
    ], cwd=str(client_dir))

    exe_path = client_dir / "dist" / f"{exe_name}.exe"
    if not exe_path.exists():
        print("  !! 客户端打包失败 !!")
        return False

    mb = exe_path.stat().st_size / 1024 / 1024
    print(f"  OK  {exe_name}.exe  ({mb:.1f} MB)")

    # 创建部署包
    pkg = client_dir / "dist" / f"HwMonClient_{TAG}_Win64"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    shutil.copy2(exe_path, pkg / f"{exe_name}.exe")
    shutil.copy2(client_dir / "config.json", pkg / "config.json")

    # 生成 bat 脚本 (用 GBK 编码写入，避免乱码)
    bats = {
        "start.bat":       f'@echo off\r\nchcp 65001 >nul\r\n{exe_name}.exe\r\npause\r\n',
        "config.bat":      f'@echo off\r\nchcp 65001 >nul\r\n{exe_name}.exe --config\r\npause\r\n',
        "install.bat":     f'@echo off\r\nchcp 65001 >nul\r\n{exe_name}.exe --install\r\npause\r\n',
        "uninstall.bat":   f'@echo off\r\nchcp 65001 >nul\r\n{exe_name}.exe --uninstall\r\npause\r\n',
    }
    for name, content in bats.items():
        with open(pkg / name, "w", encoding="gbk") as f:
            f.write(content)

    with open(pkg / "README.txt", "w", encoding="utf-8") as f:
        f.write(f"HwMon Client {TAG}\n{'='*40}\n\n")
        f.write("start.bat       - Run client (foreground)\n")
        f.write("config.bat      - Config tool\n")
        f.write("install.bat     - Install as Windows service\n")
        f.write("uninstall.bat   - Uninstall service\n\n")
        f.write("Edit config.json before starting.\n")

    print(f"  部署包: {pkg}")
    return True


def build_server():
    print()
    print("=" * 60)
    print("  [2/2] 打包 Windows 服务端")
    print("=" * 60)

    server_dir = ROOT / "server"

    # 安装依赖
    print("  安装依赖...")
    run([str(VENV_PIP), "install", "pyinstaller", "flask", "flask-cors", "waitress",
         "pymysql", "DBUtils", "cryptography", "openpyxl",
         "-q", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])

    # 清理
    for d in ["build", "dist"]:
        p = server_dir / d
        if p.exists():
            shutil.rmtree(p)

    # 打包
    exe_name = f"HwMonServer_{VERSION}"
    print(f"  PyInstaller 打包 {exe_name}.exe ...")
    ok = run([
        str(VENV_PY), "-m", "PyInstaller",
        "--onefile", "--console",
        f"--name={exe_name}",
        "--add-data=templates;templates",
        "--add-data=ai_analyzer.py;.",
        "--hidden-import=flask",
        "--hidden-import=flask_cors",
        "--hidden-import=waitress",
        "--hidden-import=pymysql",
        "--hidden-import=pymysql.cursors",
        "--hidden-import=DBUtils",
        "--hidden-import=DBUtils.pooled_db",
        "--hidden-import=cryptography",
        "--hidden-import=openpyxl",
        "--hidden-import=ai_analyzer",
        "--clean",
        "app.py",
    ], cwd=str(server_dir))

    exe_path = server_dir / "dist" / f"{exe_name}.exe"
    if not exe_path.exists():
        print("  !! 服务端打包失败 !!")
        return False

    mb = exe_path.stat().st_size / 1024 / 1024
    print(f"  OK  {exe_name}.exe  ({mb:.1f} MB)")

    # 创建部署包
    pkg = server_dir / "dist" / f"HwMonServer_{TAG}_Win64"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    shutil.copy2(exe_path, pkg / f"{exe_name}.exe")
    shutil.copy2(server_dir / "config.json", pkg / "config.json")

    bats = {
        "start.bat":    f'@echo off\r\nchcp 65001 >nul\r\n{exe_name}.exe\r\npause\r\n',
        "start_bg.bat": f'@echo off\r\nchcp 65001 >nul\r\nstart /min {exe_name}.exe\r\necho Server started in background\r\npause\r\n',
    }
    for name, content in bats.items():
        with open(pkg / name, "w", encoding="gbk") as f:
            f.write(content)

    with open(pkg / "README.txt", "w", encoding="utf-8") as f:
        f.write(f"HwMon Server {TAG}\n{'='*40}\n\n")
        f.write("start.bat     - Start server (foreground)\n")
        f.write("start_bg.bat  - Start server (background)\n\n")
        f.write("Edit config.json (MySQL connection, login password) before starting.\n")
        f.write("Access: http://localhost:5000\n")

    print(f"  部署包: {pkg}")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print(f"  HwMon {TAG}  Windows Build")
    print("=" * 60)

    if not VENV_PY.exists():
        print(f"  ERROR: {VENV_PY} not found")
        sys.exit(1)

    os.chdir(str(ROOT))

    ok1 = build_client()
    ok2 = build_server()

    print()
    print("=" * 60)
    if ok1 and ok2:
        print("  BUILD SUCCESS")
    else:
        print("  BUILD FAILED - check errors above")
    print("=" * 60)
    print()
    print(f"  Client: client\\dist\\HwMonClient_{TAG}_Win64\\")
    print(f"  Server: server\\dist\\HwMonServer_{TAG}_Win64\\")
    print()
    input("Press Enter to exit...")
