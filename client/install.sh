#!/bin/bash
# HwMon 硬件监控客户端 Linux 安装脚本
set -e

INSTALL_DIR="/opt/hwmon"
SERVICE_NAME="hwmon"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================"
echo " HwMon 硬件监控客户端 安装程序 (Linux)"
echo "========================================"

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    echo "请使用 root 权限运行此脚本: sudo bash install.sh"
    exit 1
fi

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "未找到 python3，正在安装..."
    if command -v apt-get &> /dev/null; then
        apt-get update && apt-get install -y python3 python3-pip python3-venv
    elif command -v yum &> /dev/null; then
        yum install -y python3 python3-pip
    else
        echo "无法自动安装 Python3，请手动安装后重试"
        exit 1
    fi
fi

# 安装系统依赖（lm-sensors 用于温度/风扇/电压监控）
echo "安装系统依赖..."
if command -v apt-get &> /dev/null; then
    apt-get install -y lm-sensors dmidecode pciutils 2>/dev/null || true
elif command -v yum &> /dev/null; then
    yum install -y lm_sensors dmidecode pciutils 2>/dev/null || true
fi

# 创建安装目录
echo "创建安装目录: ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"

# 复制文件
echo "复制程序文件..."
cp "${SCRIPT_DIR}/hwmon_client" "${INSTALL_DIR}/" 2>/dev/null || true
cp "${SCRIPT_DIR}/service_linux.py" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/hardware_collector.py" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/process_monitor.py" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/config.py" "${INSTALL_DIR}/"

# 如果没有配置文件，复制默认配置
if [ ! -f "${INSTALL_DIR}/config.json" ]; then
    cp "${SCRIPT_DIR}/config.json" "${INSTALL_DIR}/"
    echo "已创建默认配置文件，请编辑 ${INSTALL_DIR}/config.json"
else
    echo "配置文件已存在，跳过"
fi

chmod +x "${INSTALL_DIR}/hwmon_client" 2>/dev/null || true
chmod +x "${INSTALL_DIR}/service_linux.py"

# 如果没有打包的二进制文件，创建 Python 启动脚本
if [ ! -f "${INSTALL_DIR}/hwmon_client" ]; then
    echo '#!/bin/bash' > "${INSTALL_DIR}/hwmon_client"
    echo "cd ${INSTALL_DIR}" >> "${INSTALL_DIR}/hwmon_client"
    echo 'exec python3 service_linux.py "$@"' >> "${INSTALL_DIR}/hwmon_client"
    chmod +x "${INSTALL_DIR}/hwmon_client"
fi

# 安装 Python 依赖
echo "安装 Python 依赖..."
pip3 install --break-system-packages -r "${SCRIPT_DIR}/requirements_linux.txt" 2>/dev/null || \
pip3 install -r "${SCRIPT_DIR}/requirements_linux.txt" 2>/dev/null || true

# 安装 systemd 服务
echo "安装 systemd 服务..."
cp "${SCRIPT_DIR}/hwmon.service" /etc/systemd/system/
systemctl daemon-reload

# 启动服务
echo "启动服务..."
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

sleep 2

# 检查状态
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo ""
    echo "========================================"
    echo " 安装成功！服务已启动"
    echo "========================================"
    echo ""
    echo " 常用命令:"
    echo "   查看状态: systemctl status ${SERVICE_NAME}"
    echo "   查看日志: journalctl -u ${SERVICE_NAME} -f"
    echo "   停止服务: systemctl stop ${SERVICE_NAME}"
    echo "   重启服务: systemctl restart ${SERVICE_NAME}"
    echo "   配置文件: ${INSTALL_DIR}/config.json"
    echo ""
else
    echo ""
    echo "========================================"
    echo " 安装完成，但服务启动失败"
    echo " 请检查日志: journalctl -u ${SERVICE_NAME} -n 50"
    echo "========================================"
fi
