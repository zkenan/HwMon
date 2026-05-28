#!/bin/bash
# HwMon Server Linux .deb 打包脚本 v5.0.0-20260526
set -e

VERSION="5.0.0"
BUILD_DATE=$(date +%Y%m%d)
BUILD_TAG="v${VERSION}-${BUILD_DATE}"
PKG_NAME="hwmon-server"
PKG_DIR="${PKG_NAME}_${VERSION}_${BUILD_DATE}"
DEB_FILE="${PKG_NAME}_${VERSION}-${BUILD_DATE}_amd64.deb"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "  HwMon Server .deb 打包工具 ${BUILD_TAG}"
echo "============================================================"
echo ""

# 检查必要文件
for f in app.py ai_analyzer.py requirements.txt templates/index.html templates/login.html; do
    if [ ! -f "${SCRIPT_DIR}/${f}" ]; then
        echo "ERROR: ${f} 不存在"
        exit 1
    fi
done
echo "必要文件检查通过"
echo ""

# 清理旧包
BUILD_ROOT="/tmp/${PKG_DIR}"
rm -rf "${BUILD_ROOT}"

# 创建 .deb 目录结构
echo "[1/4] 创建目录结构 ..."
mkdir -p "${BUILD_ROOT}/DEBIAN"
mkdir -p "${BUILD_ROOT}/opt/hwmon-server"
mkdir -p "${BUILD_ROOT}/opt/hwmon-server/templates"
mkdir -p "${BUILD_ROOT}/etc/systemd/system"
echo "OK"

# 复制程序文件
echo "[2/4] 复制程序文件 ..."
cp "${SCRIPT_DIR}/app.py"             "${BUILD_ROOT}/opt/hwmon-server/"
cp "${SCRIPT_DIR}/ai_analyzer.py"     "${BUILD_ROOT}/opt/hwmon-server/"
cp "${SCRIPT_DIR}/templates/index.html" "${BUILD_ROOT}/opt/hwmon-server/templates/"
cp "${SCRIPT_DIR}/templates/login.html" "${BUILD_ROOT}/opt/hwmon-server/templates/"
cp "${SCRIPT_DIR}/requirements.txt"   "${BUILD_ROOT}/opt/hwmon-server/"

# 配置文件
if [ -f "${SCRIPT_DIR}/config.json" ]; then
    cp "${SCRIPT_DIR}/config.json" "${BUILD_ROOT}/opt/hwmon-server/config.json.default"
else
    cat > "${BUILD_ROOT}/opt/hwmon-server/config.json.default" << 'CONFIGEOF'
{
    "database": {
        "host": "localhost",
        "port": 3306,
        "user": "root",
        "password": "",
        "database": "hwmon",
        "charset": "utf8mb4"
    },
    "login": {
        "username": "admin",
        "password": ""
    },
    "server": {
        "port": 5000,
        "host": "0.0.0.0"
    },
    "collect": {
        "max_workers": 50,
        "timeout": 15,
        "retry_times": 0
    }
}
CONFIGEOF
fi

# systemd 服务文件
cat > "${BUILD_ROOT}/etc/systemd/system/hwmon-server.service" << 'SERVICEEOF'
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
SERVICEEOF

# 启动脚本
cat > "${BUILD_ROOT}/opt/hwmon-server/start.sh" << 'STARTEOF'
#!/bin/bash
cd /opt/hwmon-server
exec python3 app.py "$@"
STARTEOF
chmod 755 "${BUILD_ROOT}/opt/hwmon-server/start.sh"

echo "OK"

# DEBIAN/control
echo "[3/4] 生成控制文件 ..."
cat > "${BUILD_ROOT}/DEBIAN/control" << EOF
Package: ${PKG_NAME}
Version: ${VERSION}-${BUILD_DATE}
Section: utils
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.8), python3-pip, python3-flask, python3-mysqldb
Maintainer: HwMon Team <admin@hwmon.local>
Description: HwMon Hardware Monitor Server ${BUILD_TAG}
 硬件监控系统服务端，提供 Web 管理界面、进程告警、AI 研判。
 版本: ${VERSION}  构建日期: ${BUILD_DATE}
EOF

# postinst
cat > "${BUILD_ROOT}/DEBIAN/postinst" << 'POSTEOF'
#!/bin/bash
set -e

echo "安装 Python 依赖 ..."
pip3 install --break-system-packages flask flask-cors waitress pymysql DBUtils cryptography openpyxl requests 2>/dev/null || \
pip3 install flask flask-cors waitress pymysql DBUtils cryptography openpyxl requests 2>/dev/null || true

# 如果没有配置文件，从默认配置创建
if [ ! -f /opt/hwmon-server/config.json ]; then
    cp /opt/hwmon-server/config.json.default /opt/hwmon-server/config.json
    echo ""
    echo "============================================================"
    echo "  已创建默认配置 /opt/hwmon-server/config.json"
    echo "  请编辑配置后再启动服务"
    echo "============================================================"
fi

echo "重新加载 systemd ..."
systemctl daemon-reload

echo ""
echo "============================================================"
echo "  HwMon Server ${VERSION} 安装完成"
echo "============================================================"
echo ""
echo "  1. 编辑配置: vim /opt/hwmon-server/config.json"
echo "  2. 启动服务: systemctl start hwmon-server"
echo "  3. 开机自启: systemctl enable hwmon-server"
echo "  4. 查看日志: journalctl -u hwmon-server -f"
echo "  5. 访问界面: http://localhost:5000"
echo ""
POSTEOF
chmod 755 "${BUILD_ROOT}/DEBIAN/postinst"

# prerm
cat > "${BUILD_ROOT}/DEBIAN/prerm" << 'PREREOF'
#!/bin/bash
set -e
systemctl stop hwmon-server 2>/dev/null || true
systemctl disable hwmon-server 2>/dev/null || true
PREREOF
chmod 755 "${BUILD_ROOT}/DEBIAN/prerm"

# postrm
cat > "${BUILD_ROOT}/DEBIAN/postrm" << 'POSTRMEOF'
#!/bin/bash
set -e
if [ "$1" = "purge" ]; then
    rm -rf /opt/hwmon-server/config.json
fi
systemctl daemon-reload 2>/dev/null || true
POSTRMEOF
chmod 755 "${BUILD_ROOT}/DEBIAN/postrm"

echo "OK"

# 构建 .deb
echo "[4/4] 构建 .deb 包 ..."
OUTPUT_DIR="${SCRIPT_DIR}/dist"
mkdir -p "${OUTPUT_DIR}"
dpkg-deb --build "${BUILD_ROOT}" "${OUTPUT_DIR}/${DEB_FILE}"

echo ""
echo "============================================================"
echo "  打包完成!"
echo "============================================================"
echo ""
echo "  包文件: ${OUTPUT_DIR}/${DEB_FILE}"
echo "  大小:   $(du -h "${OUTPUT_DIR}/${DEB_FILE}" | cut -f1)"
echo ""
echo "  安装方法:"
echo "    sudo dpkg -i ${DEB_FILE}"
echo "    sudo apt-get install -f"
echo ""
echo "  部署步骤:"
echo "    1. sudo dpkg -i ${DEB_FILE}"
echo "    2. vim /opt/hwmon-server/config.json   # 配置 MySQL 和登录密码"
echo "    3. systemctl start hwmon-server         # 启动"
echo "    4. systemctl enable hwmon-server        # 开机自启"
echo "    5. 浏览器访问 http://服务器IP:5000"
echo ""

rm -rf "${BUILD_ROOT}"
