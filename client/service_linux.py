"""
硬件监控客户端 - Linux 守护进程模块
使用 systemd 管理服务生命周期
"""

import sys
import os
import time
import json
import signal
import requests
import socket
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from hardware_collector import HardwareCollector
from process_monitor import ProcessMonitor
from config import ConfigManager


def get_exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def get_client_id(config):
    try:
        return socket.gethostname()
    except Exception:
        return config.get_client_id()


def get_local_ip(config):
    try:
        hostname = socket.gethostname()
        # 尝试获取非回环地址
        for info in socket.getaddrinfo(hostname, None):
            if info[0] == socket.AF_INET:
                ip = info[4][0]
                if ip != "127.0.0.1":
                    return ip
        return socket.gethostbyname(hostname)
    except Exception:
        return "127.0.0.1"


def log_message(message, config=None):
    if not config or not config.is_logging_enabled():
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}\n"
    try:
        log_file = config.get_log_file()
        if not os.path.isabs(log_file):
            log_file = os.path.join(get_exe_dir(), log_file)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


def report_to_server(client_id, hardware_info, config, is_on_demand=False):
    try:
        data = {
            "client_id": client_id,
            "hostname": hardware_info.get("system", {}).get("hostname", ""),
            "hardware_info": hardware_info,
            "timestamp": datetime.now().isoformat(),
            "group_name": config.get('client', 'group_name', default=''),
            "local_ip": get_local_ip(config),
            "report_type": "on_demand" if is_on_demand else "scheduled"
        }
        server_url = config.get_server_url()
        timeout = config.get('server', 'timeout', default=10)
        response = requests.post(f"{server_url}/api/report", json=data, timeout=timeout)
        if response.status_code == 200:
            log_message(f"上报成功 ({'主动采集' if is_on_demand else '定时上报'})", config)
            return True
        else:
            log_message(f"上报失败: HTTP {response.status_code}", config)
            return False
    except Exception as e:
        log_message(f"上报异常: {str(e)}", config)
        return False


def report_process_alert(client_id, alert_data, config):
    """上报进程告警到服务端"""
    try:
        data = {
            "client_id": client_id,
            "hostname": socket.gethostname(),
            "local_ip": get_local_ip(config),
            "timestamp": datetime.now().isoformat(),
            "alerts": alert_data.get("alerts", []),
            "system_summary": alert_data.get("system_summary", {})
        }
        server_url = config.get_server_url()
        timeout = config.get('server', 'timeout', default=10)
        response = requests.post(f"{server_url}/api/process-alert", json=data, timeout=timeout)
        if response.status_code == 200:
            log_message(f"进程告警上报成功, 包含 {len(data['alerts'])} 个进程", config)
            return True
        else:
            log_message(f"进程告警上报失败: HTTP {response.status_code}", config)
            return False
    except Exception as e:
        log_message(f"进程告警上报异常: {str(e)}", config)
        return False


def collect_hardware_info(config):
    collector = HardwareCollector()
    info = {"timestamp": datetime.now().isoformat(), "system": collector.get_system_info()}
    if config.should_collect('cpu'): info["cpu"] = collector.get_cpu_info()
    if config.should_collect('memory'): info["memory"] = collector.get_memory_info()
    if config.should_collect('disk'): info["disk"] = collector.get_disk_info()
    if config.should_collect('gpu'): info["gpu"] = collector.get_gpu_info()
    if config.should_collect('network'): info["network"] = collector.get_network_info()
    if config.should_collect('motherboard'): info["motherboard"] = collector.get_motherboard_info()
    if config.should_collect('bios'): info["bios"] = collector.get_bios_info()
    if config.should_collect('uptime'): info["uptime"] = collector.get_uptime_info()
    if config.should_collect('temperature'): info["temperature"] = collector.get_temperature_info()
    if config.should_collect('fan'): info["fan"] = collector.get_fan_info()
    if config.should_collect('voltage'): info["voltage"] = collector.get_voltage_info()
    return info


class ClientRequestHandler(BaseHTTPRequestHandler):
    config_instance = None

    def do_GET(self):
        if self.path == '/api/status':
            try:
                client_id = get_client_id(self.config_instance)
                response = {"status": "online", "client_id": client_id, "hostname": socket.gethostname(), "timestamp": datetime.now().isoformat()}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/collect':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    self.rfile.read(content_length)
                log_message("收到服务端主动采集请求", self.config_instance)
                hardware_info = collect_hardware_info(self.config_instance)
                client_id = get_client_id(self.config_instance)
                success = report_to_server(client_id, hardware_info, self.config_instance, is_on_demand=True)
                response = {"status": "success" if success else "failed", "message": "采集并上报成功" if success else "上报失败", "client_id": client_id, "timestamp": datetime.now().isoformat()}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
                log_message(f"主动采集完成,上报{'成功' if success else '失败'}", self.config_instance)
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                log_message(f"主动采集失败: {str(e)}\n{error_detail}", self.config_instance)
                response = {"status": "error", "message": str(e), "detail": error_detail, "timestamp": datetime.now().isoformat()}
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_local_server(config):
    listen_port = config.get('client', 'listen_port', default=13301)
    try:
        ClientRequestHandler.config_instance = config
        server = HTTPServer(('0.0.0.0', listen_port), ClientRequestHandler)
        server.timeout = 5
        log_message(f"本地HTTP服务已启动,监听端口: {listen_port}", config)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        return server
    except Exception as e:
        log_message(f"启动本地HTTP服务失败: {str(e)}", config)
        return None


# 全局停止信号
running = True


def signal_handler(signum, frame):
    global running
    running = False


def main():
    """Linux 守护进程主入口"""
    global running

    # 注册信号处理
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 切换到程序所在目录
    os.chdir(get_exe_dir())

    config = ConfigManager()
    client_id = get_client_id(config)
    local_ip = get_local_ip(config)

    log_message("=" * 50, config)
    log_message("硬件监控客户端服务已启动 (Linux)", config)
    log_message(f"客户端ID: {client_id}", config)
    log_message(f"本机IP: {local_ip}", config)
    log_message(f"服务器地址: {config.get_server_url()}", config)
    log_message(f"上报间隔: {config.get_report_interval()}秒", config)

    # 启动本地 HTTP 服务
    local_server = start_local_server(config)

    # 首次上报
    try:
        hardware_info = collect_hardware_info(config)
        report_to_server(client_id, hardware_info, config)
    except Exception as e:
        log_message(f"首次上报失败: {str(e)}", config)

    # 启动进程监控线程
    pm_config = config.config.get("process_monitor", {})
    if pm_config.get("enabled", True):
        def process_monitor_loop():
            monitor = ProcessMonitor(pm_config)
            check_interval = pm_config.get("check_interval", 30)
            log_message("进程监控已启动", config)
            while running:
                try:
                    alert_data = monitor.check_and_get_alerts()
                    if alert_data and alert_data.get("alerts"):
                        report_process_alert(client_id, alert_data, config)
                except Exception as e:
                    log_message(f"进程监控异常: {str(e)}", config)
                for _ in range(check_interval):
                    if not running:
                        break
                    time.sleep(1)

        pm_thread = threading.Thread(target=process_monitor_loop, daemon=True, name="ProcessMonitor")
        pm_thread.start()
    else:
        log_message("进程监控已禁用", config)

    # 主循环：定时硬件上报
    report_interval = config.get_report_interval()
    while running:
        for _ in range(report_interval):
            if not running:
                break
            time.sleep(1)

        if not running:
            break

        try:
            hardware_info = collect_hardware_info(config)
            report_to_server(client_id, hardware_info, config)
        except Exception as e:
            log_message(f"定时上报异常: {str(e)}", config)
            time.sleep(60)

    log_message("硬件监控客户端服务已停止", config)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # 测试模式：采集一次并打印
        config = ConfigManager()
        info = collect_hardware_info(config)
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        main()
