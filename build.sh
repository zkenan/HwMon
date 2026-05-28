#!/bin/bash
# ============================================================
#  HwMon v5.0.0-20260526 统一打包脚本
#  包含: Linux 客户端/服务端 .deb + Windows 打包脚本生成
#  用法: cd HwMon && bash build.sh
# ============================================================
set -e

VERSION="5.0.0"
BUILD_DATE="20260528"
TAG="v${VERSION}-${BUILD_DATE}"
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "  HwMon ${TAG} 统一打包"
echo "============================================================"
echo ""

# 创建统一输出目录
OUTPUT="${ROOT}/release/${TAG}"
rm -rf "${OUTPUT}"
mkdir -p "${OUTPUT}/linux"
mkdir -p "${OUTPUT}/windows"

# ============================================================
#  1/4  Linux 客户端 .deb
# ============================================================
echo "[1/4] Linux 客户端 .deb ..."
echo ""

CLIENT_DIR="${ROOT}/client"
BUILD_ROOT="/tmp/hwmon-client-pkg"
rm -rf "${BUILD_ROOT}"

mkdir -p "${BUILD_ROOT}/DEBIAN"
mkdir -p "${BUILD_ROOT}/opt/hwmon"
mkdir -p "${BUILD_ROOT}/etc/systemd/system"

# 程序文件
cp "${CLIENT_DIR}/service_linux.py"        "${BUILD_ROOT}/opt/hwmon/"
cp "${CLIENT_DIR}/hardware_collector.py"   "${BUILD_ROOT}/opt/hwmon/"
cp "${CLIENT_DIR}/process_monitor.py"      "${BUILD_ROOT}/opt/hwmon/"
cp "${CLIENT_DIR}/config.py"               "${BUILD_ROOT}/opt/hwmon/"

# 默认配置
cp "${CLIENT_DIR}/config.json"             "${BUILD_ROOT}/opt/hwmon/config.json.default"

# 启动脚本
cat > "${BUILD_ROOT}/opt/hwmon/hwmon_client" << 'EOF'
#!/bin/bash
cd /opt/hwmon
exec python3 service_linux.py "$@"
EOF
chmod 755 "${BUILD_ROOT}/opt/hwmon/hwmon_client"

# systemd
cat > "${BUILD_ROOT}/etc/systemd/system/hwmon.service" << 'EOF'
[Unit]
Description=HwMon Hardware Monitor Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/hwmon/service_linux.py
WorkingDirectory=/opt/hwmon
Restart=always
RestartSec=30
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# control
cat > "${BUILD_ROOT}/DEBIAN/control" << EOF
Package: hwmon-client
Version: ${VERSION}-${BUILD_DATE}
Section: utils
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.8), python3-pip, python3-psutil, lm-sensors, dmidecode, pciutils
Maintainer: HwMon Team <admin@hwmon.local>
Description: HwMon Hardware Monitor Client ${TAG}
 硬件监控客户端 - 进程资源监控 - 阈值告警上报
EOF

cat > "${BUILD_ROOT}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e
pip3 install --break-system-packages psutil pynvml 2>/dev/null || pip3 install psutil pynvml 2>/dev/null || true
[ ! -f /opt/hwmon/config.json ] && cp /opt/hwmon/config.json.default /opt/hwmon/config.json
systemctl daemon-reload
echo ""
echo "  HwMon Client 安装完成"
echo "  1. vim /opt/hwmon/config.json"
echo "  2. systemctl start hwmon && systemctl enable hwmon"
echo ""
POSTINST
chmod 755 "${BUILD_ROOT}/DEBIAN/postinst"

cat > "${BUILD_ROOT}/DEBIAN/prerm" << 'EOF'
#!/bin/bash
systemctl stop hwmon 2>/dev/null || true
systemctl disable hwmon 2>/dev/null || true
EOF
chmod 755 "${BUILD_ROOT}/DEBIAN/prerm"

cat > "${BUILD_ROOT}/DEBIAN/postrm" << 'EOF'
#!/bin/bash
[ "$1" = "purge" ] && rm -rf /opt/hwmon/config.json /opt/hwmon/client.log
systemctl daemon-reload 2>/dev/null || true
EOF
chmod 755 "${BUILD_ROOT}/DEBIAN/postrm"

DEB_CLIENT="hwmon-client_${VERSION}-${BUILD_DATE}_amd64.deb"
dpkg-deb --build "${BUILD_ROOT}" "${OUTPUT}/linux/${DEB_CLIENT}"
echo "  OK  linux/${DEB_CLIENT}  ($(du -h "${OUTPUT}/linux/${DEB_CLIENT}" | cut -f1))"
rm -rf "${BUILD_ROOT}"
echo ""

# ============================================================
#  2/4  Linux 服务端 .deb
# ============================================================
echo "[2/4] Linux 服务端 .deb ..."
echo ""

SERVER_DIR="${ROOT}/server"
BUILD_ROOT="/tmp/hwmon-server-pkg"
rm -rf "${BUILD_ROOT}"

mkdir -p "${BUILD_ROOT}/DEBIAN"
mkdir -p "${BUILD_ROOT}/opt/hwmon-server/templates"
mkdir -p "${BUILD_ROOT}/etc/systemd/system"

# 程序文件
cp "${SERVER_DIR}/app.py"                   "${BUILD_ROOT}/opt/hwmon-server/"
cp "${SERVER_DIR}/ai_analyzer.py"           "${BUILD_ROOT}/opt/hwmon-server/"
cp "${SERVER_DIR}/templates/index.html"     "${BUILD_ROOT}/opt/hwmon-server/templates/"
cp "${SERVER_DIR}/templates/login.html"     "${BUILD_ROOT}/opt/hwmon-server/templates/"
cp "${SERVER_DIR}/requirements.txt"         "${BUILD_ROOT}/opt/hwmon-server/"
cp "${SERVER_DIR}/config.json"              "${BUILD_ROOT}/opt/hwmon-server/config.json.default"

# 启动脚本
cat > "${BUILD_ROOT}/opt/hwmon-server/start.sh" << 'EOF'
#!/bin/bash
cd /opt/hwmon-server
exec python3 app.py "$@"
EOF
chmod 755 "${BUILD_ROOT}/opt/hwmon-server/start.sh"

# systemd
cat > "${BUILD_ROOT}/etc/systemd/system/hwmon-server.service" << 'EOF'
[Unit]
Description=HwMon Hardware Monitor Server
After=network.target mysql.service
Wants=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/hwmon-server/app.py
WorkingDirectory=/opt/hwmon-server
Restart=always
RestartSec=10
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# control
cat > "${BUILD_ROOT}/DEBIAN/control" << EOF
Package: hwmon-server
Version: ${VERSION}-${BUILD_DATE}
Section: utils
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.8), python3-pip
Maintainer: HwMon Team <admin@hwmon.local>
Description: HwMon Hardware Monitor Server ${TAG}
 硬件监控系统服务端 - Web管理 - 进程告警 - AI研判
EOF

cat > "${BUILD_ROOT}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e
pip3 install --break-system-packages flask flask-cors waitress pymysql DBUtils cryptography openpyxl requests 2>/dev/null || \
pip3 install flask flask-cors waitress pymysql DBUtils cryptography openpyxl requests 2>/dev/null || true
[ ! -f /opt/hwmon-server/config.json ] && cp /opt/hwmon-server/config.json.default /opt/hwmon-server/config.json
systemctl daemon-reload
echo ""
echo "  HwMon Server 安装完成"
echo "  1. vim /opt/hwmon-server/config.json  (配置MySQL和登录密码)"
echo "  2. systemctl start hwmon-server && systemctl enable hwmon-server"
echo "  3. 浏览器访问 http://IP:5000"
echo ""
POSTINST
chmod 755 "${BUILD_ROOT}/DEBIAN/postinst"

cat > "${BUILD_ROOT}/DEBIAN/prerm" << 'EOF'
#!/bin/bash
systemctl stop hwmon-server 2>/dev/null || true
systemctl disable hwmon-server 2>/dev/null || true
EOF
chmod 755 "${BUILD_ROOT}/DEBIAN/prerm"

cat > "${BUILD_ROOT}/DEBIAN/postrm" << 'EOF'
#!/bin/bash
[ "$1" = "purge" ] && rm -rf /opt/hwmon-server/config.json
systemctl daemon-reload 2>/dev/null || true
EOF
chmod 755 "${BUILD_ROOT}/DEBIAN/postrm"

DEB_SERVER="hwmon-server_${VERSION}-${BUILD_DATE}_amd64.deb"
dpkg-deb --build "${BUILD_ROOT}" "${OUTPUT}/linux/${DEB_SERVER}"
echo "  OK  linux/${DEB_SERVER}  ($(du -h "${OUTPUT}/linux/${DEB_SERVER}" | cut -f1))"
rm -rf "${BUILD_ROOT}"
echo ""

# ============================================================
#  3/4  Windows 打包脚本
# ============================================================
echo "[3/4] 生成 Windows 打包脚本 ..."
echo ""

cat > "${OUTPUT}/windows/build_windows.bat" << 'BUILDEOF'
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
BUILDEOF

echo "  OK  windows/build_windows.bat"
echo ""

# ============================================================
#  4/4  汇总
# ============================================================
echo "[4/4] 生成说明文件 ..."

cat > "${OUTPUT}/README.txt" << EOF
HwMon ${TAG} 发布包
============================================================

目录结构:
  linux/
    hwmon-client_${VERSION}-${BUILD_DATE}_amd64.deb    Linux 客户端
    hwmon-server_${VERSION}-${BUILD_DATE}_amd64.deb    Linux 服务端
  windows/
    build_windows.bat                                   Windows 一键打包脚本
    (运行后自动生成 HwMonClient 和 HwMonServer 部署包)

Linux 客户端安装:
  sudo dpkg -i hwmon-client_*.deb
  vim /opt/hwmon/config.json
  systemctl start hwmon && systemctl enable hwmon

Linux 服务端安装:
  sudo dpkg -i hwmon-server_*.deb
  vim /opt/hwmon-server/config.json
  systemctl start hwmon-server && systemctl enable hwmon-server
  浏览器访问 http://IP:5000

Windows 打包:
  将 windows/build_windows.bat 复制到项目根目录
  双击运行 (需要 .venv 虚拟环境)
  产出 HwMonClient_v5.0.0-20260526_Win64 和 HwMonServer_v5.0.0-20260526_Win64

版本: ${VERSION}
日期: ${BUILD_DATE}
EOF

echo "  OK"
echo ""

# 列出全部产出物
echo "============================================================"
echo "  打包完成! 全部产出物:"
echo "============================================================"
echo ""
find "${OUTPUT}" -type f | sort | while read f; do
    SIZE=$(du -h "$f" | cut -f1)
    REL="${f#${OUTPUT}/}"
    printf "  %-60s %s\n" "${REL}" "${SIZE}"
done
echo ""
echo "  输出目录: ${OUTPUT}"
echo ""
