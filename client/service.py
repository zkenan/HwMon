"""
HwMon Client v5.0.1
Windows 服务 + 交互菜单 + 进程监控
"""

import sys, os, time, json, socket, threading, subprocess
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

SERVICE_NAME = "HwMon"
SERVICE_DISPLAY_NAME = "硬件监控客户端"
SERVICE_DESC = "硬件监控客户端服务，定时上报硬件信息到服务器"

# ============ 延迟导入 ============
_w32 = {}  # win32 modules cache

def _w32_import():
    if not _w32:
        import win32service, win32serviceutil, win32event, servicemanager
        _w32['ws'] = win32service
        _w32['wsu'] = win32serviceutil
        _w32['we'] = win32event
        _w32['sm'] = servicemanager
    return _w32['ws'], _w32['wsu'], _w32['we'], _w32['sm']

# ============ 工具函数 ============

def get_exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.dirname(os.path.abspath(__file__))

def get_client_id(config):
    try: return socket.gethostname()
    except: return config.get_client_id()

def get_local_ip(config):
    try: return socket.gethostbyname(socket.gethostname())
    except: return "127.0.0.1"

def log_message(msg, config=None):
    if not config or not config.is_logging_enabled(): return
    try:
        lf = config.get_log_file()
        if not os.path.isabs(lf): lf = os.path.join(get_exe_dir(), lf)
        with open(lf, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except: pass

def report_to_server(client_id, hw_info, config, is_on_demand=False):
    try:
        import requests
        data = {
            "client_id": client_id,
            "hostname": hw_info.get("system", {}).get("hostname", ""),
            "hardware_info": hw_info,
            "timestamp": datetime.now().isoformat(),
            "group_name": config.get('client', 'group_name', default=''),
            "local_ip": get_local_ip(config),
            "report_type": "on_demand" if is_on_demand else "scheduled"
        }
        r = requests.post(f"{config.get_server_url()}/api/report", json=data, timeout=config.get('server','timeout',default=10))
        log_message(f"上报{'成功' if r.status_code==200 else '失败'} ({'主动' if is_on_demand else '定时'})", config)
        return r.status_code == 200
    except Exception as e:
        log_message(f"上报异常: {e}", config)
        return False

def report_process_alert(client_id, alert_data, config):
    try:
        import requests
        data = {
            "client_id": client_id, "hostname": socket.gethostname(),
            "local_ip": get_local_ip(config), "timestamp": datetime.now().isoformat(),
            "alerts": alert_data.get("alerts", []),
            "system_summary": alert_data.get("system_summary", {})
        }
        r = requests.post(f"{config.get_server_url()}/api/process-alert", json=data, timeout=config.get('server','timeout',default=10))
        log_message(f"进程告警上报{'成功' if r.status_code==200 else '失败'}", config)
        return r.status_code == 200
    except Exception as e:
        log_message(f"进程告警异常: {e}", config)
        return False

def collect_hardware_info(config):
    from hardware_collector import HardwareCollector
    c = HardwareCollector()
    info = {"timestamp": datetime.now().isoformat(), "system": c.get_system_info()}
    if config.should_collect('cpu'): info["cpu"] = c.get_cpu_info()
    if config.should_collect('memory'): info["memory"] = c.get_memory_info()
    if config.should_collect('disk'): info["disk"] = c.get_disk_info()
    if config.should_collect('gpu'): info["gpu"] = c.get_gpu_info()
    if config.should_collect('network'): info["network"] = c.get_network_info()
    if config.should_collect('motherboard'): info["motherboard"] = c.get_motherboard_info()
    if config.should_collect('bios'): info["bios"] = c.get_bios_info()
    if config.should_collect('uptime'): info["uptime"] = c.get_uptime_info()
    if config.should_collect('temperature'): info["temperature"] = c.get_temperature_info()
    if config.should_collect('fan'): info["fan"] = c.get_fan_info()
    if config.should_collect('voltage'): info["voltage"] = c.get_voltage_info()
    return info

# ============ 本地 HTTP 服务 ============

class ClientRequestHandler(BaseHTTPRequestHandler):
    config_instance = None
    def do_GET(self):
        if self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status":"online","client_id":get_client_id(self.config_instance),"hostname":socket.gethostname(),"timestamp":datetime.now().isoformat()},ensure_ascii=False).encode())
        else: self.send_response(404); self.end_headers()
    def do_POST(self):
        if self.path == '/api/collect':
            try:
                import pythoncom; pythoncom.CoInitialize()
                try:
                    cl = int(self.headers.get('Content-Length',0))
                    if cl>0: self.rfile.read(cl)
                    hw = collect_hardware_info(self.config_instance)
                    cid = get_client_id(self.config_instance)
                    ok = report_to_server(cid, hw, self.config_instance, True)
                    self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
                    self.wfile.write(json.dumps({"status":"success" if ok else "failed","client_id":cid,"timestamp":datetime.now().isoformat()},ensure_ascii=False).encode())
                finally: pythoncom.CoUninitialize()
            except Exception as e:
                self.send_response(500); self.send_header('Content-Type','application/json'); self.end_headers()
                self.wfile.write(json.dumps({"status":"error","message":str(e)},ensure_ascii=False).encode())
        else: self.send_response(404); self.end_headers()
    def log_message(self, *a): pass

def start_local_server(config):
    try:
        port = config.get('client','listen_port',default=13301)
        ClientRequestHandler.config_instance = config
        s = HTTPServer(('0.0.0.0', port), ClientRequestHandler); s.timeout = 5
        threading.Thread(target=s.serve_forever, daemon=True).start()
        log_message(f"本地HTTP服务启动 端口{port}", config)
        return s
    except Exception as e:
        log_message(f"HTTP服务失败: {e}", config)
        return None

# ============ 服务管理 ============

def get_service_status():
    try:
        ws, wsu, we, sm = _w32_import()
        hscm = ws.OpenSCManager(None, None, ws.SC_MANAGER_ALL_ACCESS)
        hs = ws.OpenService(hscm, SERVICE_NAME, ws.SERVICE_QUERY_STATUS)
        st = ws.QueryServiceStatus(hs)[1]
        ws.CloseServiceHandle(hs); ws.CloseServiceHandle(hscm)
        m = {ws.SERVICE_STOPPED:"已停止",ws.SERVICE_START_PENDING:"启动中",ws.SERVICE_STOP_PENDING:"停止中",ws.SERVICE_RUNNING:"运行中",ws.SERVICE_CONTINUE_PENDING:"继续中",ws.SERVICE_PAUSE_PENDING:"暂停中",ws.SERVICE_PAUSED:"已暂停"}
        return m.get(st, "未知")
    except: return "未安装"

def install_service():
    ws, wsu, we, sm = _w32_import()
    try:
        try: wsu.StopService(SERVICE_NAME); time.sleep(2)
        except: pass
        try: wsu.RemoveService(SERVICE_NAME); time.sleep(1)
        except: pass
        r = subprocess.run(['sc','create',SERVICE_NAME,'binPath=',f'"{sys.executable}" --service','start=','auto','DisplayName=',SERVICE_DISPLAY_NAME], capture_output=True, text=True, timeout=30)
        if r.returncode != 0: print(f"  创建失败: {r.stdout}"); return False
        print("  ✓ 服务安装成功")
        try:
            hscm = ws.OpenSCManager(None, None, ws.SC_MANAGER_ALL_ACCESS)
            hs = ws.OpenService(hscm, SERVICE_NAME, ws.SERVICE_ALL_ACCESS)
            ws.ChangeServiceConfig2(hs, ws.SERVICE_CONFIG_DESCRIPTION, SERVICE_DESC)
            ws.CloseServiceHandle(hs); ws.CloseServiceHandle(hscm)
        except: pass
        try: subprocess.run(['sc','failure',SERVICE_NAME,'reset=','86400','actions=','restart/5000/restart/5000/restart/5000'], capture_output=True, timeout=10)
        except: pass
        started = False
        for method_name, method_fn in [
            ("win32serviceutil", lambda: wsu.StartService(SERVICE_NAME)),
            ("sc start", lambda: subprocess.run(['sc','start',SERVICE_NAME], capture_output=True, text=True, timeout=30)),
            ("net start", lambda: subprocess.run(['net','start',SERVICE_NAME], capture_output=True, text=True, timeout=30)),
        ]:
            try:
                method_fn(); time.sleep(3)
                if get_service_status() == "运行中": started = True; print(f"  ✓ 服务已启动 ({method_name})"); break
            except: pass
        if not started: print(f"  服务已安装（状态: {get_service_status()}）,尝试管理员运行: sc start HwMon")
        return True
    except Exception as e: print(f"  ✗ 安装失败: {e}"); return False

def uninstall_service():
    ws, wsu, we, sm = _w32_import()
    try:
        try: wsu.StopService(SERVICE_NAME); time.sleep(3); print("  ✓ 服务已停止")
        except: pass
        wsu.RemoveService(SERVICE_NAME); print("  ✓ 服务已卸载"); return True
    except Exception as e: print(f"  ✗ 卸载失败: {e}"); return False

# ============ 服务类（延迟创建） ============

_ServiceClass = None

def _make_service_class():
    global _ServiceClass
    if _ServiceClass: return _ServiceClass
    ws, wsu, we, sm = _w32_import()

    class HwMonService(wsu.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESC
        def __init__(self, args):
            wsu.ServiceFramework.__init__(self, args)
            self.hWaitStop = we.CreateEvent(None,0,0,None)
            self.config = None; self.running = False
        def SvcStop(self):
            self.ReportServiceStatus(ws.SERVICE_STOP_PENDING)
            we.SetEvent(self.hWaitStop); self.running = False
        def SvcDoRun(self):
            ws, wsu, we, sm = _w32_import()
            self.ReportServiceStatus(ws.SERVICE_RUNNING)

            # 后台线程执行实际工作
            def worker():
                import pythoncom; pythoncom.CoInitialize()
                try:
                    from config import ConfigManager
                    os.chdir(get_exe_dir())
                    self.config = ConfigManager(); self.running = True
                    log_message("服务已启动", self.config)
                    cid = get_client_id(self.config)
                    log_message(f"ID={cid} 服务端={self.config.get_server_url()}", self.config)
                    start_local_server(self.config)
                    # 进程监控
                    pm = self.config.config.get("process_monitor",{})
                    if pm.get("enabled",True):
                        def pm_loop():
                            import pythoncom as pc2; pc2.CoInitialize()
                            try:
                                from process_monitor import ProcessMonitor
                                mon = ProcessMonitor(pm); iv = pm.get("check_interval",30)
                                while self.running:
                                    try:
                                        d = mon.check_and_get_alerts()
                                        if d and d.get("alerts"): report_process_alert(cid,d,self.config)
                                    except: pass
                                    for _ in range(iv):
                                        if not self.running: break
                                        time.sleep(1)
                            finally: pc2.CoUninitialize()
                        threading.Thread(target=pm_loop,daemon=True).start()
                    # 首次上报
                    try: hw = collect_hardware_info(self.config); report_to_server(cid,hw,self.config)
                    except Exception as e: log_message(f"首次上报失败: {e}",self.config)
                    # 定时上报循环
                    iv = self.config.get_report_interval()
                    while self.running:
                        time.sleep(iv)
                        if not self.running: break
                        try: hw = collect_hardware_info(self.config); report_to_server(cid,hw,self.config)
                        except Exception as e: log_message(f"上报失败: {e}",self.config)
                except Exception as e:
                    import traceback; log_message(f"服务异常: {e}\n{traceback.format_exc()}",self.config)
                finally: log_message("服务已停止", self.config)

            threading.Thread(target=worker, daemon=True).start()

            # 关键：SvcDoRun 必须阻塞，否则进程退出，daemon 线程被杀
            # 等待 SvcStop 设置的停止事件
            we.WaitForSingleObject(self.hWaitStop, we.INFINITE)
            self.running = False

    _ServiceClass = HwMonService
    return _ServiceClass

# ============ 前台运行 ============

def run_foreground(config):
    import pythoncom; pythoncom.CoInitialize()
    from process_monitor import ProcessMonitor
    cid = get_client_id(config)
    print(f"客户端ID: {cid}")
    print(f"本机IP:   {get_local_ip(config)}")
    print(f"服务端:   {config.get_server_url()}")
    print()
    start_local_server(config)
    # 进程监控
    pm = config.config.get("process_monitor",{})
    if pm.get("enabled",True):
        def pm_loop():
            import pythoncom as pc2; pc2.CoInitialize()
            try:
                mon = ProcessMonitor(pm); iv = pm.get("check_interval",30)
                while True:
                    try:
                        d = mon.check_and_get_alerts()
                        if d and d.get("alerts"): report_process_alert(cid,d,config); print(f"[进程告警] {len(d['alerts'])} 个")
                    except: pass
                    for _ in range(iv): time.sleep(1)
            finally: pc2.CoUninitialize()
        threading.Thread(target=pm_loop,daemon=True).start()
        print("[进程监控] 已启动")
    # 首次上报
    try: hw = collect_hardware_info(config); report_to_server(cid,hw,config); print("[上报] 首次成功")
    except Exception as e: print(f"[上报] 首次失败: {e}")
    # 主循环
    iv = config.get_report_interval()
    try:
        while True:
            for _ in range(iv): time.sleep(1)
            try: hw = collect_hardware_info(config); report_to_server(cid,hw,config); print(f"[上报] {datetime.now().strftime('%H:%M:%S')} 成功")
            except Exception as e: print(f"[上报] 失败: {e}")
    except KeyboardInterrupt: print("\n已停止")

# ============ 交互菜单 ============

def interactive_menu():
    from config import ConfigManager
    config = ConfigManager()
    while True:
        print()
        print("=" * 50)
        print("  HwMon Client v5.0.1")
        print("=" * 50)
        print(f"  服务端: {config.get_server_url()}")
        print(f"  上报间隔: {config.get_report_interval()}秒")
        print(f"  服务状态: {get_service_status()}")
        print("-" * 50)
        print("  1. 立即测试采集")
        print("  2. 安装并启动服务 (开机自启)")
        print("  3. 停止并卸载服务")
        print("  4. 编辑配置")
        print("  5. 查看当前配置")
        print("  6. 前台运行 (Ctrl+C 停止)")
        print("  0. 退出")
        print("-" * 50)
        choice = input("  请选择: ").strip()

        if choice == "1":
            print("\n正在采集...")
            try:
                import pythoncom; pythoncom.CoInitialize()
                print(json.dumps(collect_hardware_info(config), indent=2, ensure_ascii=False))
            except Exception as e: print(f"失败: {e}")
            input("\n回车返回...")

        elif choice == "2":
            print("\n正在安装服务...")
            install_service()
            input("\n回车返回...")

        elif choice == "3":
            print("\n正在卸载...")
            uninstall_service()
            input("\n回车返回...")

        elif choice == "4":
            print(f"\n当前服务端: {config.get_server_url()}")
            url = input("  新地址 (回车跳过): ").strip()
            if url: config.set(url, 'server', 'url')
            iv = input(f"  上报间隔秒 [{config.get_report_interval()}]: ").strip()
            if iv.isdigit(): config.set(int(iv), 'client', 'report_interval')
            g = input(f"  分组 [{config.get('client','group_name',default='')}]: ").strip()
            if g: config.set(g, 'client', 'group_name')
            print("已保存")

        elif choice == "5":
            print(json.dumps(config.config, indent=2, ensure_ascii=False))
            input("\n回车返回...")

        elif choice == "6":
            print("\n前台模式 Ctrl+C 停止\n")
            run_foreground(config)

        elif choice == "0":
            print("退出"); break

        else: print("无效选项")

# ============ 主入口 ============

if __name__ == "__main__":
    _log_file = os.path.join(os.environ.get('TEMP', os.path.expanduser('~')), 'hwmon_startup.log')
    def _wlog(msg):
        try:
            with open(_log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        except: pass

    try:
        _wlog(f"启动 sys.argv={sys.argv}")

        # 检测服务模式：--service 参数 或 无参数且无控制台
        _is_service = '--service' in sys.argv
        _wlog(f"  --service={_is_service}")

        if _is_service:
            _wlog(">>> 服务模式 (--service)")
            ws, wsu, we, sm = _w32_import()
            SvcClass = _make_service_class()
            sm.Initialize()
            sm.PrepareToHostSingle(SvcClass)
            sm.StartServiceCtrlDispatcher()
            _wlog("SCM返回")
        else:
            _wlog(">>> 交互模式")
            interactive_menu()

    except Exception as e:
        import traceback
        _wlog(f"顶层异常: {e}\n{traceback.format_exc()}")
        raise
