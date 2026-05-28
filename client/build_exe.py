"""
HwMon 客户端打包脚本 v5.0.0-20260526
将客户端打包为 Windows 独立 exe
"""

import os
import sys
import subprocess
import shutil
import json
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

VERSION = "5.0.0"
BUILD_DATE = datetime.now().strftime("%Y%m%d")
BUILD_TAG = f"v{VERSION}-{BUILD_DATE}"


def check_env():
    print("=" * 60)
    print(f"  HwMon Client 打包工具 {BUILD_TAG}")
    print("=" * 60)
    print()

    print(f"Python: {sys.version}")
    print(f"平台:   {sys.platform}")
    print()

    required = [
        "service.py",
        "hardware_collector.py",
        "process_monitor.py",
        "config.py",
    ]
    ok = True
    for f in required:
        if Path(f).exists():
            print(f"  OK  {f}")
        else:
            print(f"  MISSING  {f}")
            ok = False
    print()
    return ok


def install_deps():
    print("[1/3] 安装依赖 ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller",
                           "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt",
                           "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
    print("OK\n")


def build():
    print("[2/3] PyInstaller 打包 ...")

    for d in ["build", "dist"]:
        p = Path(d)
        if p.exists():
            shutil.rmtree(p)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        f"--name=HwMonClient_{VERSION}",
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
        "--hidden-import=json",
        "--hidden-import=threading",
        "--hidden-import=socket",
        "--hidden-import=pynvml",
        "--clean",
        "service.py",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    exe = Path(f"dist/HwMonClient_{VERSION}.exe")
    if exe.exists():
        mb = exe.stat().st_size / 1024 / 1024
        print(f"OK  {exe}  ({mb:.1f} MB)\n")
        return exe
    else:
        print("FAILED")
        print(result.stderr[-2000:] if result.stderr else "")
        sys.exit(1)


def package(exe_path):
    print("[3/3] 创建部署包 ...")

    tag = f"HwMonClient_{BUILD_TAG}_Win64"
    pkg = Path("dist") / tag
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    # exe
    shutil.copy2(exe_path, pkg / exe_path.name)

    # 默认配置
    cfg = {
        "server": {"url": "http://localhost:5000", "timeout": 10, "retry_times": 3, "retry_interval": 60},
        "client": {"report_interval": 120, "auto_start": True, "client_id": "", "group_name": "", "listen_port": 13301},
        "logging": {"enabled": True, "log_file": "client.log", "max_size_mb": 10, "backup_count": 5},
        "advanced": {
            "collect_cpu": True, "collect_memory": True, "collect_disk": True,
            "collect_gpu": True, "collect_network": True, "collect_motherboard": True,
            "collect_bios": True, "collect_temperature": True, "collect_fan": True,
            "collect_voltage": True, "collect_uptime": True, "compress_data": False,
        },
        "process_monitor": {
            "enabled": True, "check_interval": 30,
            "thresholds": {"cpu_percent": 90, "memory_percent": 90, "gpu_percent": 90},
            "duration_seconds": 300,
            "ignore_processes": ["System Idle Process", "System", "idle", "Idle"],
            "gpu_enabled": False,
        },
    }
    with open(pkg / "config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

    # 批处理
    for name, content in [
        ("启动配置工具.bat", '@echo off\r\nchcp 65001 >nul\r\nHwMonClient_{v}.exe --config\r\npause\r\n'),
        ("安装为开机自启.bat", '@echo off\r\nchcp 65001 >nul\r\nHwMonClient_{v}.exe --install\r\npause\r\n'),
        ("卸载程序.bat", '@echo off\r\nchcp 65001 >nul\r\nHwMonClient_{v}.exe --uninstall\r\npause\r\n'),
    ]:
        with open(pkg / name, "w", encoding="gbk") as f:
            f.write(content.format(v=VERSION))

    # 说明
    with open(pkg / "README.txt", "w", encoding="utf-8") as f:
        f.write(f"""HwMon Client {BUILD_TAG}
============================

版本:   {VERSION}
日期:   {BUILD_DATE}
平台:   Windows x64

部署步骤:
1. 将此文件夹复制到目标电脑
2. 编辑 config.json，修改 server.url 为服务端地址
3. 以管理员身份运行 "安装为开机自启.bat"

配置说明:
- server.url          服务端地址 (必填)
- client.report_interval  上报间隔 (秒，默认120)
- client.group_name   分组名称
- process_monitor.enabled 进程监控开关
- process_monitor.thresholds.cpu_percent  CPU 告警阈值 (默认90%)
- process_monitor.duration_seconds  持续时间阈值 (默认300秒)

新功能 (v5.0.0):
- 进程级资源监控 (CPU/GPU/内存)
- 超阈值持续5分钟自动告警上报
- 跨平台支持 (Windows + Linux)
- AI 研判功能 (需服务端配合)
""")

    print(f"OK  {pkg}\n")
    return pkg


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    check_env()
    install_deps()
    exe = build()
    package(exe)
    print("=" * 60)
    print(f"  完成! {BUILD_TAG}")
    print("=" * 60)
    input("\n按回车退出...")
