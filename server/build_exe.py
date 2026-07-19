"""
HwMon 服务端打包脚本 v5.0.0-20260526
将服务端打包为 Windows 独立 exe
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
    print(f"  HwMon Server 打包工具 {BUILD_TAG}")
    print("=" * 60)
    print()

    print(f"Python: {sys.version}")
    print()

    required = ["app.py", "ai_analyzer.py", "templates/index.html", "templates/login.html", "requirements.txt"]
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
        f"--name=HwMonServer_{VERSION}",
        "--add-data=templates;templates",
        "--add-data=ai_analyzer.py;.",
        "--hidden-import=flask",
        "--hidden-import=flask_cors",
        "--hidden-import=waitress",
        "--hidden-import=concurrent.futures",
        "--hidden-import=requests",
        "--hidden-import=pymysql",
        "--hidden-import=pymysql.cursors",
        "--hidden-import=DBUtils",
        "--hidden-import=DBUtils.pooled_db",
        "--hidden-import=cryptography",
        "--hidden-import=openpyxl",
        "--hidden-import=json",
        "--hidden-import=csv",
        "--hidden-import=smtplib",
        "--hidden-import=email.mime.text",
        "--hidden-import=email.mime.multipart",
        "--hidden-import=ai_analyzer",
        "--clean",
        "app.py",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    exe = Path(f"dist/HwMonServer_{VERSION}.exe")
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

    tag = f"HwMonServer_{BUILD_TAG}_Win64"
    pkg = Path("dist") / tag
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    # exe
    shutil.copy2(exe_path, pkg / exe_path.name)

    # 配置文件
    src_cfg = Path("config.json")
    if src_cfg.exists():
        shutil.copy2(src_cfg, pkg / "config.json")
    else:
        # 创建默认配置
        cfg = {
            "database": {"host": "localhost", "port": 3306, "user": "root", "password": "", "database": "hwmon", "charset": "utf8mb4"},
            "login": {"username": "admin", "password": ""},
            "server": {"port": 5000, "host": "0.0.0.0"},
            "collect": {"max_workers": 50, "timeout": 15, "retry_times": 0},
        }
        with open(pkg / "config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)

    # 批处理
    for name, content in [
        ("启动服务端.bat", '@echo off\r\nchcp 65001 >nul\r\nHwMonServer_{v}.exe\r\npause\r\n'),
        ("后台运行.bat", '@echo off\r\nchcp 65001 >nul\r\nstart /min HwMonServer_{v}.exe\r\necho 服务端已在后台启动\r\npause\r\n'),
    ]:
        with open(pkg / name, "w", encoding="gbk") as f:
            f.write(content.format(v=VERSION))

    # 说明
    with open(pkg / "README.txt", "w", encoding="utf-8") as f:
        f.write(f"""HwMon Server {BUILD_TAG}
============================

版本:   {VERSION}
日期:   {BUILD_DATE}
平台:   Windows x64

部署步骤:
1. 将此文件夹复制到服务器
2. 编辑 config.json，配置 MySQL 连接和登录密码
3. 双击 "启动服务端.bat"
4. 浏览器访问 http://服务器IP:5000

配置说明:
- database.host        MySQL 地址
- database.port        MySQL 端口
- database.user        MySQL 用户名
- database.password    MySQL 密码
- database.database    数据库名 (默认 hwmon)
- login.username       Web 登录用户名 (默认 admin)
- login.password       Web 登录密码 (必填)
- server.port          Web 端口 (默认 5000)

MySQL 要求:
- 版本 8.0+
- 需提前创建数据库: CREATE DATABASE hwmon CHARACTER SET utf8mb4;
- 表结构由服务端自动创建，无需手动建表

新功能 (v5.0.0):
- 进程告警接收与展示
- AI 研判引擎 (OpenAI 兼容接口)
- AI 监控主机管理
- AI 配置模块 (API 地址/Key/模型/提示词)
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
