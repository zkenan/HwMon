# -*- coding: utf-8 -*-
"""
HwMon v5.0.0  Windows YiJian DaBao JiaoBen
Usage:
  Double-click build_all.bat
  Or: .venv/Scripts/python.exe build_all.py

Output:
  client/dist/HwMonClient_5.0.0_Win64/
  server/dist/HwMonServer_5.0.0_Win64/
"""
import os, sys, subprocess, shutil
from pathlib import Path

VERSION = "5.0.0"
TAG = "v" + VERSION + "-20260528"
ROOT = Path(__file__).parent.resolve()


def find_python():
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python3",
        ROOT / ".venv" / "bin" / "python",
    ]
    for p in candidates:
        if p.exists():
            return p
    for exe in ["python.exe", "python3.exe", "python"]:
        try:
            r = subprocess.run([exe, "--version"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return exe
        except Exception:
            pass
    return None


def find_pip(python):
    p = python.parent / "pip.exe"
    if p.exists():
        return p
    p = python.parent / "pip3"
    if p.exists():
        return p
    return python


def ensure_venv():
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return venv_py
    print("  [!] .venv not found, creating...")
    system_py = shutil.which("python.exe") or shutil.which("python")
    if not system_py:
        print("  [X] Python not found, install Python 3.8+ first")
        return None
    r = subprocess.run([system_py, "-m", "venv", str(ROOT / ".venv")],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print("  [X] venv create failed:", r.stderr)
        return None
    return venv_py


def run_cmd(cmd, cwd=None):
    label = cmd[0]
    if len(cmd) > 3:
        label = cmd[0] + " ... " + cmd[-1]
    print("  >", label)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    if r.returncode != 0:
        if r.stderr:
            for line in r.stderr.strip().splitlines()[-15:]:
                print("   ", line)
        return False
    return True


def build_client(python):
    print()
    print("=" * 60)
    print("  [1/2] Build Windows Client")
    print("=" * 60)

    client_dir = ROOT / "client"
    pip = find_pip(python)

    print()
    print("  Installing dependencies...")
    deps = ["pyinstaller", "psutil", "wmi", "pywin32", "requests", "pynvml"]
    ok = run_cmd([str(pip), "install"] + deps + ["-q"], cwd=str(client_dir))
    if not ok:
        ok = run_cmd([str(pip), "install"] + deps, cwd=str(client_dir))
        if not ok:
            print("  [X] pip install failed")
            return False

    for d in ["build", "dist"]:
        p = client_dir / d
        if p.exists():
            shutil.rmtree(p)

    exe_name = "HwMonClient_" + VERSION
    print()
    print("  PyInstaller ->", exe_name + ".exe ...")
    ok = run_cmd([
        str(python), "-m", "PyInstaller",
        "--onefile", "--console",
        "--name=" + exe_name,
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

    exe_path = client_dir / "dist" / (exe_name + ".exe")
    if not exe_path.exists():
        print("  [X] Client build failed")
        return False

    mb = exe_path.stat().st_size / 1024 / 1024
    print("  [OK]", exe_name + ".exe", "({:.1f} MB)".format(mb))

    pkg = client_dir / "dist" / ("HwMonClient_" + TAG + "_Win64")
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    shutil.copy2(exe_path, pkg / (exe_name + ".exe"))
    cfg = client_dir / "config.json"
    if cfg.exists():
        shutil.copy2(cfg, pkg / "config.json")

    bats = {
        "start.bat":        "@echo off\r\nchcp 65001 >nul\r\n" + exe_name + ".exe\r\npause\r\n",
        "install.bat":      "@echo off\r\nchcp 65001 >nul\r\n" + exe_name + ".exe --install\r\npause\r\n",
        "uninstall.bat":    "@echo off\r\nchcp 65001 >nul\r\n" + exe_name + ".exe --uninstall\r\npause\r\n",
        "start_service.bat":"@echo off\r\nchcp 65001 >nul\r\nsc start HwMon\r\npause\r\n",
        "stop_service.bat": "@echo off\r\nchcp 65001 >nul\r\nsc stop HwMon\r\npause\r\n",
    }
    for name, content in bats.items():
        with open(pkg / name, "w", encoding="gbk") as f:
            f.write(content)

    readme = (
        "HwMon Client " + TAG + "\n" +
        "=" * 40 + "\n\n" +
        "start.bat         - Run in foreground\n" +
        "install.bat       - Install as Windows service\n" +
        "uninstall.bat     - Stop and remove service\n" +
        "start_service.bat - Start the service (if installed)\n" +
        "stop_service.bat  - Stop the service\n\n" +
        "Steps:\n" +
        "  1. Edit config.json, set server.url\n" +
        "  2. Right-click install.bat -> Run as Administrator\n" +
        "  3. Service starts automatically on boot\n\n" +
        "Or double-click start.bat to run in foreground (no install)\n"
    )
    with open(pkg / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme)

    print("  [OK] Package:", pkg)
    return True


def build_server(python):
    print()
    print("=" * 60)
    print("  [2/2] Build Windows Server")
    print("=" * 60)

    server_dir = ROOT / "server"
    pip = find_pip(python)

    print()
    print("  Installing dependencies...")
    deps = ["pyinstaller", "flask", "flask-cors", "waitress",
            "pymysql", "DBUtils", "cryptography", "openpyxl"]
    ok = run_cmd([str(pip), "install"] + deps + ["-q"], cwd=str(server_dir))
    if not ok:
        ok = run_cmd([str(pip), "install"] + deps, cwd=str(server_dir))
        if not ok:
            print("  [X] pip install failed")
            return False

    for d in ["build", "dist"]:
        p = server_dir / d
        if p.exists():
            shutil.rmtree(p)

    exe_name = "HwMonServer_" + VERSION
    print()
    print("  PyInstaller ->", exe_name + ".exe ...")
    ok = run_cmd([
        str(python), "-m", "PyInstaller",
        "--onefile", "--console",
        "--name=" + exe_name,
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

    exe_path = server_dir / "dist" / (exe_name + ".exe")
    if not exe_path.exists():
        print("  [X] Server build failed")
        return False

    mb = exe_path.stat().st_size / 1024 / 1024
    print("  [OK]", exe_name + ".exe", "({:.1f} MB)".format(mb))

    pkg = server_dir / "dist" / ("HwMonServer_" + TAG + "_Win64")
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    shutil.copy2(exe_path, pkg / (exe_name + ".exe"))
    cfg = server_dir / "config.json"
    if cfg.exists():
        shutil.copy2(cfg, pkg / "config.json")

    bats = {
        "start.bat":    "@echo off\r\nchcp 65001 >nul\r\n" + exe_name + ".exe\r\npause\r\n",
        "start_bg.bat": "@echo off\r\nchcp 65001 >nul\r\nstart /min " + exe_name + ".exe\r\necho Server started in background\r\npause\r\n",
    }
    for name, content in bats.items():
        with open(pkg / name, "w", encoding="gbk") as f:
            f.write(content)

    readme = (
        "HwMon Server " + TAG + "\n" +
        "=" * 40 + "\n\n" +
        "start.bat     - Run in foreground (see console logs)\n" +
        "start_bg.bat  - Run in background (minimized)\n\n" +
        "Steps:\n" +
        "  1. Edit config.json, configure MySQL connection\n" +
        "  2. Double-click start.bat\n" +
        "  3. Open http://localhost:5000 in browser\n" +
        "  Default: admin / admin123\n"
    )
    with open(pkg / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme)

    print("  [OK] Package:", pkg)
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("  HwMon " + TAG + "  Windows Build")
    print("=" * 60)

    python = find_python()
    if python is None:
        print("\n  [X] Python not found, install Python 3.8+ first")
        sys.exit(1)
    print("\n  Python:", python)

    # Auto-create venv if using system python
    if ".venv" not in str(python):
        venv_py = ensure_venv()
        if venv_py:
            print("  > Switching to venv:", venv_py)
            r = subprocess.run([str(venv_py), __file__] + sys.argv[1:])
            sys.exit(r.returncode)

    os.chdir(str(ROOT))

    ok1 = build_client(python)
    ok2 = build_server(python)

    print()
    print("=" * 60)
    if ok1 and ok2:
        print("  [OK] BUILD SUCCESS!")
    else:
        if not ok1:
            print("  [X] Client build failed")
        if not ok2:
            print("  [X] Server build failed")
    print("=" * 60)
    print()
    if ok1:
        ctag = "HwMonClient_" + TAG + "_Win64"
        print("  Client: client\\dist\\" + ctag + "\\")
    if ok2:
        stang = "HwMonServer_" + TAG + "_Win64"
        print("  Server: server\\dist\\" + stang + "\\")
    print()

    if ok1 or ok2:
        try:
            input("Press Enter to exit...")
        except Exception:
            pass
