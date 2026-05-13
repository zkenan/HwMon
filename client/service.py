"""
硬件监控客户端 - Windows 服务模块
使用 pywin32 ServiceFramework 正确实现 Windows 服务
"""

import sys
import os
import time
import json
import requests
import socket
import threading
import servicemanager
import win32service
import win32serviceutil
import win32event
import subprocess
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from hardware_collector import HardwareCollector
from config import ConfigManager


SERVICE_NAME = "HwMon"
SERVICE_DISPLAY_NAME = "硬件监控客户端"
SERVICE_DESC = "硬件监控客户端服务，定时上报硬件信息到服务器，支持服务端主动采集"


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
                import pythoncom
                pythoncom.CoInitialize()
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
                finally:
                    pythoncom.CoUninitialize()
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


class HwMonService(win32serviceutil.ServiceFramework):
    """硬件监控 Windows 服务"""

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESC

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.config = None
        self.local_server = None
        self.running = False

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.running = False

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, ''))
        os.chdir(get_exe_dir())

        # 初始化 COM（WMI 需要）
        import pythoncom
        pythoncom.CoInitialize()

        self.config = ConfigManager()
        self.running = True

        log_message("硬件监控客户端服务已启动", self.config)

        try:
            client_id = get_client_id(self.config)
            local_ip = get_local_ip(self.config)
            log_message(f"客户端ID: {client_id}", self.config)
            log_message(f"本机IP: {local_ip}", self.config)
            log_message(f"服务器地址: {self.config.get_server_url()}", self.config)
            log_message(f"上报间隔: {self.config.get_report_interval()}秒", self.config)

            self.local_server = start_local_server(self.config)

            try:
                hardware_info = collect_hardware_info(self.config)
                report_to_server(client_id, hardware_info, self.config)
            except Exception as e:
                log_message(f"首次上报失败: {str(e)}", self.config)

            report_interval = self.config.get_report_interval()
            while self.running:
                result = win32event.WaitForSingleObject(self.hWaitStop, report_interval * 1000)
                if result == win32event.WAIT_OBJECT_0:
                    break
                try:
                    hardware_info = collect_hardware_info(self.config)
                    report_to_server(client_id, hardware_info, self.config)
                except Exception as e:
                    log_message(f"定时上报异常: {str(e)}", self.config)
                    time.sleep(60)
        except Exception as e:
            import traceback
            log_message(f"服务运行异常: {str(e)}\n{traceback.format_exc()}", self.config)
        finally:
            log_message("硬件监控客户端服务已停止", self.config)
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STOPPED, (self._svc_name_, ''))


def install_service():
    """安装并启动服务（使用 sc 命令）"""
    exe_path = sys.executable

    try:
        # 先卸载已存在的服务
        try:
            win32serviceutil.StopService(SERVICE_NAME)
            time.sleep(2)
            print("  已停止旧服务")
        except Exception:
            pass
        try:
            win32serviceutil.RemoveService(SERVICE_NAME)
            time.sleep(1)
            print("  已卸载旧服务")
        except Exception:
            pass

        # 用 sc 创建服务
        bin_path = f'"{exe_path}" --service'
        result = subprocess.run(
            ['sc', 'create', SERVICE_NAME,
             'binPath=', bin_path,
             'start=', 'auto',
             'DisplayName=', SERVICE_DISPLAY_NAME],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            print(f"  创建服务失败: {result.stdout}")
            return False

        print("  ✓ 服务安装成功")

        try:
            hscm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            hs = win32service.OpenService(hscm, SERVICE_NAME, win32service.SERVICE_ALL_ACCESS)
            win32service.ChangeServiceConfig2(hs, win32service.SERVICE_CONFIG_DESCRIPTION, SERVICE_DESC)
            win32service.CloseServiceHandle(hs)
            win32service.CloseServiceHandle(hscm)
        except Exception:
            pass

        try:
            subprocess.run(['sc', 'failure', SERVICE_NAME, 'reset=', '86400', 'actions=', 'restart/5000/restart/5000/restart/5000'], capture_output=True, timeout=10)
        except Exception:
            pass

        # 启动服务
        result = subprocess.run(['sc', 'start', SERVICE_NAME], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("  ✓ 服务已启动")
        else:
            time.sleep(3)
            status = get_service_status()
            if status == "运行中":
                print("  ✓ 服务已启动")
            else:
                print(f"  服务已安装（状态: {status}），请手动启动")

        return True
    except Exception as e:
        print(f"  ✗ 服务安装失败: {str(e)}")
        return False


def uninstall_service():
    try:
        try:
            win32serviceutil.StopService(SERVICE_NAME)
            time.sleep(3)
            print("  ✓ 服务已停止")
        except Exception:
            pass
        win32serviceutil.RemoveService(SERVICE_NAME)
        print("  ✓ 服务已卸载")
        return True
    except Exception as e:
        print(f"  ✗ 服务卸载失败: {str(e)}")
        return False


def get_service_status():
    try:
        hscm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
        hs = win32service.OpenService(hscm, SERVICE_NAME, win32service.SERVICE_QUERY_STATUS)
        status = win32service.QueryServiceStatus(hs)
        win32service.CloseServiceHandle(hs)
        win32service.CloseServiceHandle(hscm)
        state_map = {
            win32service.SERVICE_STOPPED: "已停止",
            win32service.SERVICE_START_PENDING: "启动中",
            win32service.SERVICE_STOP_PENDING: "停止中",
            win32service.SERVICE_RUNNING: "运行中",
            win32service.SERVICE_CONTINUE_PENDING: "继续中",
            win32service.SERVICE_PAUSE_PENDING: "暂停中",
            win32service.SERVICE_PAUSED: "已暂停",
        }
        return state_map.get(status[1], "未知")
    except Exception:
        return "未安装"


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(HwMonService)
