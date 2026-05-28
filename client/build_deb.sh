#!/bin/bash
# HwMon Client Linux .deb 打包脚本 v5.0.0-20260526
# 用法: sudo bash build_deb.sh
set -e

VERSION="5.0.0"
BUILD_DATE=$(date +%Y%m%d)
BUILD_TAG="v${VERSION}-${BUILD_DATE}"
PKG_NAME="hwmon-client"
PKG_DIR="${PKG_NAME}_${VERSION}_${BUILD_DATE}"
DEB_FILE="${PKG_NAME}_${VERSION}-${BUILD_DATE}_amd64.deb"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "  HwMon Client .deb 打包工具 ${BUILD_TAG}"
echo "============================================================"
echo ""

# 检查必要文件
for f in service_linux.py hardware_collector.py process_monitor.py config.py; do
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
mkdir -p "${BUILD_ROOT}/opt/hwmon"
mkdir -p "${BUILD_ROOT}/etc/systemd/system"
echo "OK"

# 复制程序文件
echo "[2/4] 复制程序文件 ..."
cp "${SCRIPT_DIR}/service_linux.py"   "${BUILD_ROOT}/opt/hwmon/"
cp "${SCRIPT_DIR}/hardware_collector.py" "${BUILD_ROOT}/opt/hwmon/"
cp "${SCRIPT_DIR}/process_monitor.py" "${BUILD_ROOT}/opt/hwmon/"
cp "${SCRIPT_DIR}/config.py"          "${BUILD_ROOT}/opt/hwmon/"

# 配置文件（如果目标已存在则不覆盖）
if [ -f "${SCRIPT_DIR}/config.json" ]; then
    cp "${SCRIPT_DIR}/config.json" "${BUILD_ROOT}/opt/hwmon/config.json.default"
else
    cat > "${BUILD_ROOT}/opt/hwmon/config.json.default" << 'CONFIGEOF'
{
    "server": {
        "url": "http://localhost:5000",
        "timeout": 10,
        "retry_times": 3,
        "retry_interval": 60
    },
    "client": {
        "report_interval": 120,
        "auto_start": true,
        "client_id": "",
        "group_name": "",
        "listen_port": 13301
    },
    "logging": {
        "enabled": true,
        "log_file": "client.log",
        "max_size_mb": 10,
        "backup_count": 5
    },
    "advanced": {
        "collect_cpu": true,
        "collect_memory": true,
        "collect_disk": true,
        "collect_gpu": true,
        "collect_network": true,
        "collect_motherboard": true,
        "collect_bios": true,
        "collect_temperature": true,
        "collect_fan": true,
        "collect_voltage": true,
        "collect_uptime": true,
        "compress_data": false
    },
    "process_monitor": {
        "enabled": true,
        "check_interval": 30,
        "thresholds": {
            "cpu_percent": 90,
            "memory_percent": 90,
            "gpu_percent": 90
        },
        "duration_seconds": 300,
        "ignore_processes": ["System Idle Process", "System", "idle", "Idle"],
        "gpu_enabled": false
    }
}
CONFIGEOF
fi

# systemd 服务文件
cat > "${BUILD_ROOT}/etc/systemd/system/hwmon.service" << 'SERVICEEOF'
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
SERVICEEOF

# 启动脚本（用户可直接运行）
cat > "${BUILD_ROOT}/opt/hwmon/hwmon_client" << 'STARTEOF'
#!/bin/bash
cd /opt/hwmon
exec python3 service_linux.py "$@"
STARTEOF
chmod 755 "${BUILD_ROOT}/opt/hwmon/hwmon_client"

echo "OK"

# DEBIAN/control
echo "[3/4] 生成控制文件 ..."
cat > "${BUILD_ROOT}/DEBIAN/control" << EOF
Package: ${PKG_NAME}
Version: ${VERSION}-${BUILD_DATE}
Section: utils
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.8), python3-pip, python3-psutil, lm-sensors, dmidecode, pciutils
Maintainer: HwMon Team <admin@hwmon.local>
Description: HwMon Hardware Monitor Client ${BUILD_TAG}
 硬件监控客户端，采集系统硬件信息和进程资源占用，
 支持阈值告警上报和 AI 研判。
 版本: ${VERSION}  构建日期: ${BUILD_DATE}
EOF

# postinst - 安装后脚本（安装 Python 依赖 + 启用服务）
cat > "${BUILD_ROOT}/DEBIAN/postinst" << 'POSTEOF'
#!/bin/bash
set -e

echo "安装 Python 依赖 ..."
pip3 install --break-system-packages psutil pynvml 2>/dev/null || \
pip3 install psutil pynvml 2>/dev/null || true

# 如果没有配置文件，从默认配置创建
if [ ! -f /opt/hwmon/config.json ]; then
    cp /opt/hwmon/config.json.default /opt/hwmon/config.json
    echo "已创建默认配置 /opt/hwmon/config.json，请编辑配置后启动服务"
fi

echo "重新加载 systemd ..."
systemctl daemon-reload

echo ""
echo "============================================================"
echo "  HwMon Client ${VERSION} 安装完成"
echo "============================================================"
echo ""
echo "  1. 编辑配置: vim /opt/hwmon/config.json"
echo "  2. 启动服务: systemctl start hwmon"
echo "  3. 开机自启: systemctl enable hwmon"
echo "  4. 查看日志: journalctl -u hwmon -f"
echo ""
POSTEOF
chmod 755 "${BUILD_ROOT}/DEBIAN/postinst"

# prerm - 卸载前脚本
cat > "${BUILD_ROOT}/DEBIAN/prerm" << 'PREREOF'
#!/bin/bash
set -e
systemctl stop hwmon 2>/dev/null || true
systemctl disable hwmon 2>/dev/null || true
PREREOF
chmod 755 "${BUILD_ROOT}/DEBIAN/prerm"

# postrm - 卸载后脚本
cat > "${BUILD_ROOT}/DEBIAN/postrm" << 'POSTRMEOF'
#!/bin/bash
set -e
if [ "$1" = "purge" ]; then
    rm -rf /opt/hwmon/config.json /opt/hwmon/client.log
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
echo "    sudo apt-get install -f  # 如有依赖问题"
echo ""
echo "  部署步骤:"
echo "    1. sudo dpkg -i ${DEB_FILE}"
echo "    2. vim /opt/hwmon/config.json   # 修改服务端地址"
echo "    3. systemctl start hwmon         # 启动服务"
echo "    4. systemctl enable hwmon        # 开机自启"
echo ""

# 清理
rm -rf "${BUILD_ROOT}"
