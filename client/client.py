"""
HwMonClient - 硬件监控客户端
支持三种运行模式:
  1. 交互模式 - 菜单操作
  2. 静默模式 --silent - 后台运行(兼容旧版本)
  3. 服务模式 --service - 作为Windows服务运行
支持配置文件管理和exe打包
支持服务端主动采集
"""

import sys
import os
import time
import json
import requests
import socket
import threading
import winreg
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from hardware_collector import HardwareCollector
from config import ConfigManager
from service import install_service, uninstall_service, get_service_status


def get_exe_dir():
    """获取exe所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def get_client_id(config):
    """获取客户端ID - 使用主机名"""
    try:
        hostname = socket.gethostname()
        return hostname
    except Exception:
        # 获取主机名失败时使用备用ID
        return config.get_client_id()


def get_local_ip(config):
    """获取本机IP地址"""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return local_ip
    except Exception:
        return "127.0.0.1"


def log_message(message, config):
    """记录日志"""
    if not config.is_logging_enabled():
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}\n"
    try:
        log_file = config.get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line)
    except:
        pass


def report_to_server(client_id, hardware_info, config, is_on_demand=False):
    """向服务器上报硬件信息"""
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

        response = requests.post(
            f"{server_url}/api/report",
            json=data,
            timeout=timeout
        )

        if response.status_code == 200:
            log_message(f"上报成功 ({'主动采集' if is_on_demand else '定时上报'})", config)
            return True
        else:
            log_message(f"上报失败: HTTP {response.status_code}", config)
            return False
    except Exception as e:
        log_message(f"上报异常: {str(e)}", config)
        return False


def set_startup(config, auto_start=True):
    """设置开机自启动"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )

        # 获取可执行文件路径(支持exe和py)
        if getattr(sys, 'frozen', False):
            # 打包后的exe
            exe_path = sys.executable
            args = "--silent"
        else:
            # Python脚本
            exe_path = sys.executable
            script_path = os.path.abspath(__file__)
            args = f'"{script_path}" --silent'

        if auto_start:
            winreg.SetValueEx(key, "HardwareMonitor", 0, winreg.REG_SZ,
                            f'"{exe_path}" {args}')
            log_message("已设置开机自启动", config)
        else:
            try:
                winreg.DeleteValue(key, "HardwareMonitor")
                log_message("已取消开机自启动", config)
            except:
                pass

        winreg.CloseKey(key)
        return True
    except Exception as e:
        log_message(f"设置开机自启动失败: {str(e)}", config)
        return False


def collect_hardware_info(config):
    """根据配置采集硬件信息"""
    collector = HardwareCollector()
    info = {
        "timestamp": datetime.now().isoformat(),
        "system": collector.get_system_info()
    }

    # 根据配置选择性地采集
    if config.should_collect('cpu'):
        info["cpu"] = collector.get_cpu_info()

    if config.should_collect('memory'):
        info["memory"] = collector.get_memory_info()

    if config.should_collect('disk'):
        info["disk"] = collector.get_disk_info()

    if config.should_collect('gpu'):
        info["gpu"] = collector.get_gpu_info()

    if config.should_collect('network'):
        info["network"] = collector.get_network_info()

    if config.should_collect('motherboard'):
        info["motherboard"] = collector.get_motherboard_info()

    if config.should_collect('bios'):
        info["bios"] = collector.get_bios_info()

    return info


class ClientRequestHandler(BaseHTTPRequestHandler):
    """处理服务端主动采集请求的HTTP处理器"""
    
    # 类属性,通过外部设置
    config_instance = None

    def do_GET(self):
        """处理GET请求 - 返回客户端状态"""
        if self.path == '/api/status':
            try:
                client_id = get_client_id(self.config_instance)
                response = {
                    "status": "online",
                    "client_id": client_id,
                    "hostname": socket.gethostname(),
                    "timestamp": datetime.now().isoformat()
                }
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
        """处理POST请求 - 主动采集硬件信息"""
        if self.path == '/api/collect':
            try:
                # WMI在子线程中需要初始化COM
                import pythoncom
                pythoncom.CoInitialize()
                
                # 读取请求体（必须读取，否则连接异常）
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    self.rfile.read(content_length)
                
                log_message("收到服务端主动采集请求", self.config_instance)

                # 采集硬件信息
                hardware_info = collect_hardware_info(self.config_instance)
                client_id = get_client_id(self.config_instance)

                # 上报到服务器
                success = report_to_server(client_id, hardware_info, self.config_instance, is_on_demand=True)

                response = {
                    "status": "success" if success else "failed",
                    "message": "采集并上报成功" if success else "上报失败",
                    "client_id": client_id,
                    "timestamp": datetime.now().isoformat()
                }

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

                log_message(f"主动采集完成,上报{'成功' if success else '失败'}", self.config_instance)
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                log_message(f"主动采集失败: {str(e)}\n{error_detail}", self.config_instance)
                response = {
                    "status": "error",
                    "message": str(e),
                    "detail": error_detail,
                    "timestamp": datetime.now().isoformat()
                }
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            finally:
                # 释放COM资源
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except:
                    pass
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """抑制默认日志输出"""
        pass


def start_local_server(config):
    """启动本地HTTP服务,接收服务端采集请求"""
    listen_port = config.get('client', 'listen_port', default=13301)

    try:
        # 设置类属性,避免__init__参数传递问题
        ClientRequestHandler.config_instance = config
        
        server = HTTPServer(('0.0.0.0', listen_port), ClientRequestHandler)
        # 设置socket超时,避免长时间占用
        server.timeout = 5

        log_message(f"本地HTTP服务已启动,监听端口: {listen_port}", config)

        # 在后台线程运行
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        return server
    except Exception as e:
        log_message(f"启动本地HTTP服务失败: {str(e)}", config)
        return None


def uninstall(config):
    """卸载程序 - 取消开机自启,停止进程,删除文件"""
    print("\n" + "=" * 50)
    print("硬件监控客户端 - 卸载工具")
    print("=" * 50)
    
    # 1. 取消开机自启
    print("\n步骤 1/4: 取消开机自启动...")
    try:
        set_startup(config, False)
        print("  ✓ 已取消开机自启动")
    except Exception as e:
        print(f"  ✗ 取消开机自启失败: {str(e)}")
    
    # 2. 停止本地HTTP服务（通过修改注册表后重启生效）
    print("\n步骤 2/4: 程序将在重启后完全停止")
    print("  提示: 如需立即停止,请在任务管理器中结束 HardwareMonitor.exe 进程")
    
    # 3. 删除文件
    print("\n步骤 3/4: 删除程序文件...")
    files_to_delete = []
    
    # 获取当前可执行文件路径
    if getattr(sys, 'frozen', False):
        # exe模式: 删除自身exe
        exe_path = sys.executable
        print(f"  提示: 无法删除正在运行的exe,请手动删除:")
        print(f"    {exe_path}")
    else:
        # Python脚本模式
        script_path = os.path.abspath(__file__)
        files_to_delete.append(script_path)
    
    # 配置文件和日志文件
    try:
        config_file = config.CONFIG_FILE
        files_to_delete.append(config_file)
    except:
        pass
    
    try:
        log_file = config.get_log_file()
        files_to_delete.append(log_file)
    except:
        pass
    
    # 删除文件
    deleted_count = 0
    for file_path in files_to_delete:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"  ✓ 已删除: {file_path}")
                deleted_count += 1
        except Exception as e:
            print(f"  ✗ 删除失败: {file_path}")
            print(f"     原因: {str(e)}")
            print(f"     请手动删除该文件")
    
    # 4. 完成
    print("\n步骤 4/4: 卸载完成!")
    print("\n" + "=" * 50)
    print(f"卸载结果: 已删除 {deleted_count}/{len(files_to_delete)} 个文件")
    print("=" * 50)
    print("\n注意事项:")
    print("  1. 如程序仍在运行,请在任务管理器中结束 HardwareMonitor.exe")
    print("  2. 剩余文件(如果有)请手动删除")
    print("  3. 卸载已完成,无需重启")
    print("\n按回车键退出...")
    safe_input()


def run_silent(config):
    """静默运行模式"""
    log_message("客户端启动", config)

    # 设置开机自启
    if config.is_auto_start():
        set_startup(config, True)

    client_id = get_client_id(config)
    local_ip = get_local_ip(config)
    listen_port = config.get('client', 'listen_port', default=13301)

    log_message(f"客户端ID: {client_id}", config)
    log_message(f"本机IP: {local_ip}", config)
    log_message(f"服务器地址: {config.get_server_url()}", config)
    log_message(f"上报间隔: {config.get_report_interval()}秒", config)

    # 启动本地HTTP服务(用于服务端主动采集)
    local_server = start_local_server(config)

    # 首次立即上报
    try:
        hardware_info = collect_hardware_info(config)
        report_to_server(client_id, hardware_info, config)
    except Exception as e:
        log_message(f"首次上报失败: {str(e)}", config)

    # 定时上报
    report_interval = config.get_report_interval()
    while True:
        try:
            time.sleep(report_interval)
            hardware_info = collect_hardware_info(config)
            report_to_server(client_id, hardware_info, config)
        except Exception as e:
            log_message(f"定时上报异常: {str(e)}", config)
            time.sleep(60)


def show_config_editor(config):
    """显示配置编辑器"""
    print("\n" + "=" * 50)
    print("配置编辑器")
    print("=" * 50)
    print(f"1. 服务器URL: {config.get_server_url()}")
    print(f"2. 上报间隔: {config.get_report_interval()}秒")
    print(f"3. 开机自启: {'启用' if config.is_auto_start() else '禁用'}")
    print(f"4. 客户端ID(主机名): {get_client_id(config)}")
    print(f"5. 分组名称: {config.get('client', 'group_name', default='')}")
    print(f"6. 本地监听端口: {config.get('client', 'listen_port', default=13301)}")
    print(f"7. 日志功能: {'启用' if config.is_logging_enabled() else '禁用'}")
    print("-" * 50)
    print("8. 重置为默认配置")
    print("9. 返回主菜单")
    print("=" * 50)

    choice = safe_input("请选择要修改的项目 (1-9): ").strip()

    if choice == "1":
        new_url = safe_input(f"输入新的服务器URL (当前: {config.get_server_url()}): ").strip()
        if new_url:
            config.set(new_url, 'server', 'url')
            print("服务器URL已更新")

    elif choice == "2":
        try:
            new_interval = int(safe_input(f"输入新的上报间隔(秒) (当前: {config.get_report_interval()}): ").strip())
            if new_interval > 0:
                config.set(new_interval, 'client', 'report_interval')
                print("上报间隔已更新")
        except ValueError:
            print("无效的数值")

    elif choice == "3":
        current = config.is_auto_start()
        config.set(not current, 'client', 'auto_start')
        print(f"开机自启已{'启用' if not current else '禁用'}")

    elif choice == "4":
        print(f"提示: 客户端ID自动使用主机名({get_client_id(config)}),无需手动设置")

    elif choice == "5":
        new_group = safe_input(f"输入分组名称 (当前: {config.get('client', 'group_name', default='')}): ").strip()
        config.set(new_group, 'client', 'group_name')
        print("分组名称已更新")

    elif choice == "6":
        try:
            new_port = int(safe_input(f"输入本地监听端口 (当前: {config.get('client', 'listen_port', default=13301)}): ").strip())
            if 1024 < new_port < 65535:
                config.set(new_port, 'client', 'listen_port')
                print("本地监听端口已更新")
        except ValueError:
            print("无效的数值")

    elif choice == "7":
        current = config.is_logging_enabled()
        config.set(not current, 'logging', 'enabled')
        print(f"日志功能已{'启用' if not current else '禁用'}")

    elif choice == "8":
        confirm = safe_input("确定要重置为默认配置吗? (y/n): ").strip().lower()
        if confirm == 'y':
            config.reset_to_default()
            print("配置已重置")

    elif choice == "9":
        return

    safe_input("\n按回车键继续...")
    show_config_editor(config)


def has_console():
    """检测是否有控制台输入"""
    try:
        import msvcrt
        return True
    except ImportError:
        return False

def safe_input(prompt=""):
    """安全的输入函数,在无控制台时返回空字符串"""
    try:
        return input(prompt)
    except (EOFError, OSError):
        return ""

def main():
    """主函数"""
    # 初始化配置管理器
    config = ConfigManager()

    # 检测是否以静默模式运行(无控制台窗口)
    is_silent_mode = not has_console()

    # --service 模式: 作为 Windows 服务运行
    if "--service" in sys.argv:
        import servicemanager
        import service
        os.chdir(get_exe_dir())
        # 正确注册 SCM: Initialize -> PrepareToHostSingle -> StartServiceCtrlDispatcher
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(service.HwMonService)
        servicemanager.StartServiceCtrlDispatcher()
        sys.exit(0)

    if "--uninstall" in sys.argv:
        # 卸载模式
        uninstall(config)
        sys.exit(0)
    elif "--silent" in sys.argv or "--install" in sys.argv or is_silent_mode:
        # 静默运行或安装模式
        if is_silent_mode and "--silent" not in sys.argv and "--install" not in sys.argv:
            # 如果是双击运行且无控制台,自动安装并静默运行
            log_message("检测到无控制台窗口,自动进入安装模式", config)
            set_startup(config, True)

        run_silent(config)
    elif "--config" in sys.argv:
        # 配置模式
        show_config_editor(config)
    else:
        # 交互模式
        while True:
            # 获取当前服务状态
            service_status = get_service_status()

            print("\n" + "=" * 50)
            print("硬件监控客户端 v4.0")
            print(f"本机: {socket.gethostname()} ({get_local_ip(config)})")
            print(f"Windows服务状态: {service_status}")
            print("=" * 50)
            print("1. 立即测试采集硬件信息")
            print("2. 安装为 Windows 服务(开机自启+完全后台)")
            print("3. 卸载 Windows 服务")
            print("4. 编辑配置")
            print("5. 查看当前配置")
            print("6. 退出")
            print("=" * 50)

            choice = safe_input("请选择操作 (1-6): ").strip()
            if not choice:
                print("输入无效,请重新输入")
                continue

            if choice == "1":
                print("\n正在采集硬件信息...")
                try:
                    hardware_info = collect_hardware_info(config)
                    print("\n采集到的硬件信息:")
                    print(json.dumps(hardware_info, indent=2, ensure_ascii=False))

                    # 测试上报
                    test_upload = safe_input("\n是否测试上报到服务器? (y/n): ").strip().lower()
                    if test_upload == 'y':
                        client_id = get_client_id(config)
                        print(f"\n正在上报...(客户端ID: {client_id})")
                        success = report_to_server(client_id, hardware_info, config)
                        if success:
                            print("上报成功!")
                        else:
                            print("上报失败,请检查服务器地址和网络连接")
                except Exception as e:
                    print(f"采集失败: {str(e)}")

            elif choice == "2":
                print("\n正在安装 Windows 服务...")
                print("(需要管理员权限)")
                if install_service():
                    print("\n安装完成!")
                    print("服务将开机自动启动,完全在后台运行")
                    print(f"日志文件: {config.get_log_file()}")
                    print(f"配置文件: {config.CONFIG_FILE}")
                    print("\n提示: 此控制台窗口可以安全关闭,服务会继续在后台运行")
                else:
                    print("\n安装失败,请以管理员身份运行此程序")
                safe_input("\n按回车键继续...")

            elif choice == "3":
                confirm = safe_input("\n确定要卸载 Windows 服务吗? (y/n): ").strip().lower()
                if confirm == 'y':
                    print("\n正在卸载 Windows 服务...")
                    if uninstall_service():
                        print("\n卸载完成!")
                    else:
                        print("\n卸载失败,请以管理员身份运行此程序")
                else:
                    print("已取消卸载")
                safe_input("\n按回车键继续...")

            elif choice == "4":
                show_config_editor(config)

            elif choice == "5":
                print("\n当前配置:")
                print(json.dumps(config.config, indent=2, ensure_ascii=False))

            elif choice == "6":
                print("\n退出程序")
                sys.exit(0)
            else:
                print("\n无效选择,请重新输入")


if __name__ == "__main__":
    main()
