HwMon v5.0.0-20260526 发布包
============================================================

目录结构:
  linux/
    hwmon-client_5.0.0-20260526_amd64.deb    Linux 客户端
    hwmon-server_5.0.0-20260526_amd64.deb    Linux 服务端
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

版本: 5.0.0
日期: 20260526
