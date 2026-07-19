"""
硬件信息采集模块（跨平台版）
支持 Windows（WMI）和 Linux（psutil + /sys）
采集系统的硬件信息、MAC地址、IP地址和主机名
"""

import socket
import platform
import psutil
import json
import os
import subprocess
from datetime import datetime

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# Windows 专用：延迟导入 WMI
_wmi = None
_wmi_attempted = False


def _get_wmi():
    """延迟加载 WMI（仅 Windows）"""
    global _wmi, _wmi_attempted
    if _wmi_attempted:
        return _wmi
    if not IS_WINDOWS:
        _wmi_attempted = True
        return None
    try:
        import wmi as wmi_module
        _wmi = wmi_module.WMI()
    except Exception:
        _wmi = None
    _wmi_attempted = True
    return _wmi


def _read_file(path):
    """安全读取文件内容"""
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read().strip()
    except Exception:
        return None


def _read_sys_file(path):
    """读取 /sys 文件系统中的单行值"""
    val = _read_file(path)
    return val


class HardwareCollector:
    """硬件信息采集器（跨平台）"""

    def get_system_info(self):
        """获取系统基本信息"""
        try:
            if IS_WINDOWS:
                return self._get_system_info_windows()
            else:
                return self._get_system_info_linux()
        except Exception as e:
            return {"error": f"获取系统信息失败: {str(e)}"}

    def _get_system_info_windows(self):
        c = _get_wmi()
        if c:
            try:
                os_info = c.Win32_OperatingSystem()[0]
                return {
                    "hostname": socket.gethostname(),
                    "os_name": os_info.Caption,
                    "os_version": os_info.Version,
                    "os_architecture": platform.architecture()[0],
                    "boot_time": str(psutil.boot_time()),
                }
            except Exception:
                pass
        return self._get_system_info_fallback()

    def _get_system_info_linux(self):
        os_name = "Linux"
        os_version = platform.release()

        # 尝试从 /etc/os-release 读取发行版信息
        os_release = _read_file("/etc/os-release")
        if os_release:
            for line in os_release.splitlines():
                if line.startswith("PRETTY_NAME="):
                    os_name = line.split("=", 1)[1].strip('"')
                    break

        return {
            "hostname": socket.gethostname(),
            "os_name": os_name,
            "os_version": os_version,
            "os_architecture": platform.architecture()[0],
            "boot_time": str(psutil.boot_time()),
        }

    def _get_system_info_fallback(self):
        return {
            "hostname": socket.gethostname(),
            "os_name": platform.system(),
            "os_version": platform.release(),
            "os_architecture": platform.architecture()[0],
            "boot_time": str(psutil.boot_time()),
        }

    def get_cpu_info(self):
        """获取CPU信息"""
        try:
            if IS_WINDOWS:
                return self._get_cpu_info_windows()
            else:
                return self._get_cpu_info_linux()
        except Exception as e:
            return [{"error": f"获取CPU信息失败: {str(e)}"}]

    def _get_cpu_info_windows(self):
        c = _get_wmi()
        if c:
            try:
                cpu_list = []
                for cpu in c.Win32_Processor():
                    cpu_list.append({
                        "name": cpu.Name,
                        "cores": cpu.NumberOfCores,
                        "threads": cpu.NumberOfLogicalProcessors,
                        "max_clock_speed": cpu.MaxClockSpeed,
                        "manufacturer": cpu.Manufacturer,
                    })
                if cpu_list:
                    return cpu_list
            except Exception:
                pass
        return self._get_cpu_info_fallback()

    def _get_cpu_info_linux(self):
        cpu_name = "Unknown"
        cores = psutil.cpu_count(logical=False) or 1
        threads = psutil.cpu_count(logical=True) or 1

        # 从 /proc/cpuinfo 读取型号
        cpuinfo = _read_file("/proc/cpuinfo")
        if cpuinfo:
            for line in cpuinfo.splitlines():
                if line.startswith("model name"):
                    cpu_name = line.split(":", 1)[1].strip()
                    break

        # 读取 CPU 频率
        freq = psutil.cpu_freq()
        max_clock = int(freq.max * 1000) if freq and freq.max else 0

        # 读取制造商
        vendor = _read_sys_file("/sys/devices/virtual/dmi/id/cpu_vendor") or ""

        return [{
            "name": cpu_name,
            "cores": cores,
            "threads": threads,
            "max_clock_speed": max_clock,
            "manufacturer": vendor,
        }]

    def _get_cpu_info_fallback(self):
        freq = psutil.cpu_freq()
        return [{
            "name": platform.processor() or "Unknown",
            "cores": psutil.cpu_count(logical=False) or 1,
            "threads": psutil.cpu_count(logical=True) or 1,
            "max_clock_speed": int(freq.max * 1000) if freq and freq.max else 0,
            "manufacturer": "",
        }]

    def get_memory_info(self):
        """获取内存信息"""
        try:
            if IS_WINDOWS:
                return self._get_memory_info_windows()
            else:
                return self._get_memory_info_linux()
        except Exception as e:
            return {"error": f"获取内存信息失败: {str(e)}"}

    def _get_memory_info_windows(self):
        c = _get_wmi()
        if c:
            try:
                memory_list = []
                for mem in c.Win32_PhysicalMemory():
                    memory_list.append({
                        "capacity": int(mem.Capacity),
                        "speed": mem.Speed,
                        "manufacturer": mem.Manufacturer,
                        "part_number": mem.PartNumber,
                    })
                if memory_list:
                    total_memory = sum([m["capacity"] for m in memory_list])
                    return {"modules": memory_list, "total_capacity": total_memory}
            except Exception:
                pass
        return self._get_memory_info_fallback()

    def _get_memory_info_linux(self):
        mem = psutil.virtual_memory()
        modules = []

        # 尝试用 dmidecode 获取内存条信息
        try:
            result = subprocess.run(
                ['dmidecode', '-t', 'memory'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                current_module = {}
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("Size:") and "MB" in line:
                        size_str = line.split(":", 1)[1].strip()
                        try:
                            size_mb = int(size_str.split()[0])
                            current_module["capacity"] = size_mb * 1024 * 1024
                        except ValueError:
                            pass
                    elif line.startswith("Speed:") and "MHz" in line:
                        speed_str = line.split(":", 1)[1].strip()
                        try:
                            current_module["speed"] = int(speed_str.split()[0])
                        except ValueError:
                            pass
                    elif line.startswith("Manufacturer:"):
                        current_module["manufacturer"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Part Number:"):
                        current_module["part_number"] = line.split(":", 1)[1].strip()
                    elif line == "" and current_module.get("capacity"):
                        modules.append(current_module)
                        current_module = {}
                if current_module.get("capacity"):
                    modules.append(current_module)
        except Exception:
            pass

        if not modules:
            modules = [{"capacity": mem.total, "speed": 0, "manufacturer": "", "part_number": ""}]

        return {
            "modules": modules,
            "total_capacity": mem.total,
        }

    def _get_memory_info_fallback(self):
        mem = psutil.virtual_memory()
        return {
            "modules": [{"capacity": mem.total, "speed": 0, "manufacturer": "", "part_number": ""}],
            "total_capacity": mem.total,
        }

    def get_disk_info(self):
        """获取硬盘信息"""
        try:
            if IS_WINDOWS:
                return self._get_disk_info_windows()
            else:
                return self._get_disk_info_linux()
        except Exception as e:
            return [{"error": f"获取硬盘信息失败: {str(e)}"}]

    def _get_disk_info_windows(self):
        c = _get_wmi()
        if c:
            try:
                disk_list = []
                for disk in c.Win32_DiskDrive():
                    disk_list.append({
                        "model": disk.Model,
                        "size": int(disk.Size) if disk.Size else 0,
                        "serial_number": disk.SerialNumber,
                        "interface_type": disk.InterfaceType,
                    })
                if disk_list:
                    return disk_list
            except Exception:
                pass
        return self._get_disk_info_fallback()

    def _get_disk_info_linux(self):
        disk_list = []
        for part in psutil.disk_partitions():
            if part.device.startswith("/dev/"):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disk_list.append({
                        "model": part.device,
                        "size": usage.total,
                        "serial_number": "",
                        "interface_type": part.fstype,
                    })
                except Exception:
                    continue

        # 尝试从 /sys/block 获取更详细的磁盘信息
        if os.path.isdir("/sys/block"):
            disk_list = []
            for dev in os.listdir("/sys/block"):
                if dev.startswith("loop") or dev.startswith("ram"):
                    continue
                model = _read_sys_file(f"/sys/block/{dev}/device/model") or dev
                size_sectors = _read_sys_file(f"/sys/block/{dev}/size")
                size = int(size_sectors) * 512 if size_sectors else 0
                serial = _read_sys_file(f"/sys/block/{dev}/device/serial") or ""

                disk_list.append({
                    "model": model,
                    "size": size,
                    "serial_number": serial,
                    "interface_type": "SCSI" if "sd" in dev else "NVMe" if "nvme" in dev else "Unknown",
                })

        return disk_list if disk_list else self._get_disk_info_fallback()

    def _get_disk_info_fallback(self):
        partitions = psutil.disk_partitions()
        if partitions:
            p = partitions[0]
            usage = psutil.disk_usage(p.mountpoint)
            return [{"model": p.device, "size": usage.total, "serial_number": "", "interface_type": p.fstype}]
        return []

    def get_gpu_info(self):
        """获取显卡信息"""
        try:
            if IS_WINDOWS:
                return self._get_gpu_info_windows()
            else:
                return self._get_gpu_info_linux()
        except Exception as e:
            return [{"error": f"获取显卡信息失败: {str(e)}"}]

    def _get_gpu_info_windows(self):
        c = _get_wmi()
        if c:
            try:
                gpu_list = []
                for gpu in c.Win32_VideoController():
                    gpu_list.append({
                        "name": gpu.Name,
                        "adapter_ram": int(gpu.AdapterRAM) if gpu.AdapterRAM else 0,
                        "driver_version": gpu.DriverVersion,
                    })
                if gpu_list:
                    return gpu_list
            except Exception:
                pass
        return []

    def _get_gpu_info_linux(self):
        gpu_list = []

        # 尝试通过 lspci 获取 GPU 信息
        try:
            result = subprocess.run(
                ['lspci', '-v'], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "VGA" in line or "3D" in line or "Display" in line:
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            gpu_list.append({
                                "name": parts[2].strip(),
                                "adapter_ram": 0,
                                "driver_version": "",
                            })
        except Exception:
            pass

        # 尝试通过 nvidia-smi 获取 NVIDIA GPU 信息
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                gpu_list = []
                for line in result.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        gpu_list.append({
                            "name": parts[0],
                            "adapter_ram": int(parts[1]) * 1024 * 1024 if parts[1].isdigit() else 0,
                            "driver_version": parts[2],
                        })
        except Exception:
            pass

        return gpu_list if gpu_list else []

    def get_network_info(self):
        """获取网络信息(MAC地址和IP地址)"""
        try:
            if IS_WINDOWS:
                return self._get_network_info_windows()
            else:
                return self._get_network_info_linux()
        except Exception as e:
            return [{"error": f"获取网络信息失败: {str(e)}"}]

    def _get_network_info_windows(self):
        c = _get_wmi()
        if c:
            try:
                network_list = []
                for interface in c.Win32_NetworkAdapterConfiguration(IPEnabled=True):
                    mac = interface.MACAddress
                    if mac:
                        ips = interface.IPAddress if interface.IPAddress else []
                        network_list.append({
                            "mac_address": mac,
                            "ip_addresses": [ip for ip in ips if ip],
                            "description": interface.Description,
                        })
                if network_list:
                    return network_list
            except Exception:
                pass
        return self._get_network_info_fallback()

    def _get_network_info_linux(self):
        network_list = []
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        for iface_name, addr_list in addrs.items():
            if iface_name == "lo":
                continue

            mac = ""
            ips = []
            for addr in addr_list:
                if addr.family == psutil.AF_LINK:
                    mac = addr.address
                elif addr.family == 2:  # AF_INET
                    ips.append(addr.address)
                elif addr.family == 10:  # AF_INET6
                    ips.append(addr.address)

            if mac:
                desc = iface_name
                if iface_name in stats:
                    desc = f"{iface_name} ({'UP' if stats[iface_name].isup else 'DOWN'})"

                network_list.append({
                    "mac_address": mac,
                    "ip_addresses": ips,
                    "description": desc,
                })

        return network_list if network_list else self._get_network_info_fallback()

    def _get_network_info_fallback(self):
        addrs = psutil.net_if_addrs()
        network_list = []
        for iface_name, addr_list in addrs.items():
            mac = ""
            ips = []
            for addr in addr_list:
                if addr.family == psutil.AF_LINK:
                    mac = addr.address
                elif addr.family == 2:
                    ips.append(addr.address)
            if mac and iface_name != "lo":
                network_list.append({
                    "mac_address": mac,
                    "ip_addresses": ips,
                    "description": iface_name,
                })
        return network_list

    def get_motherboard_info(self):
        """获取主板信息"""
        try:
            if IS_WINDOWS:
                return self._get_motherboard_info_windows()
            else:
                return self._get_motherboard_info_linux()
        except Exception as e:
            return {"error": f"获取主板信息失败: {str(e)}"}

    def _get_motherboard_info_windows(self):
        c = _get_wmi()
        if c:
            try:
                for board in c.Win32_BaseBoard():
                    return {
                        "manufacturer": board.Manufacturer or "",
                        "product": board.Product or "",
                        "serial_number": board.SerialNumber or "",
                    }
            except Exception:
                pass
        return {}

    def _get_motherboard_info_linux(self):
        manufacturer = _read_sys_file("/sys/devices/virtual/dmi/id/board_vendor") or ""
        product = _read_sys_file("/sys/devices/virtual/dmi/id/board_name") or ""
        serial = _read_sys_file("/sys/devices/virtual/dmi/id/board_serial") or ""
        return {
            "manufacturer": manufacturer,
            "product": product,
            "serial_number": serial,
        }

    def get_bios_info(self):
        """获取BIOS信息"""
        try:
            if IS_WINDOWS:
                return self._get_bios_info_windows()
            else:
                return self._get_bios_info_linux()
        except Exception as e:
            return {"error": f"获取BIOS信息失败: {str(e)}"}

    def _get_bios_info_windows(self):
        c = _get_wmi()
        if c:
            try:
                for bios in c.Win32_BIOS():
                    return {
                        "manufacturer": bios.Manufacturer or "",
                        "version": bios.Version or "",
                        "serial_number": bios.SerialNumber or "",
                        "release_date": bios.ReleaseDate or "",
                    }
            except Exception:
                pass
        return {}

    def _get_bios_info_linux(self):
        vendor = _read_sys_file("/sys/devices/virtual/dmi/id/bios_vendor") or ""
        version = _read_sys_file("/sys/devices/virtual/dmi/id/bios_version") or ""
        date = _read_sys_file("/sys/devices/virtual/dmi/id/bios_date") or ""
        return {
            "manufacturer": vendor,
            "version": version,
            "serial_number": "",
            "release_date": date,
        }

    def get_uptime_info(self):
        """获取系统运行时间（跨平台通用）"""
        try:
            boot_timestamp = psutil.boot_time()
            now_timestamp = datetime.now().timestamp()
            uptime_seconds = int(now_timestamp - boot_timestamp)

            days = uptime_seconds // 86400
            hours = (uptime_seconds % 86400) // 3600
            minutes = (uptime_seconds % 3600) // 60
            seconds = uptime_seconds % 60

            uptime_parts = []
            if days > 0:
                uptime_parts.append(f"{days}天")
            if hours > 0:
                uptime_parts.append(f"{hours}小时")
            if minutes > 0:
                uptime_parts.append(f"{minutes}分钟")
            uptime_parts.append(f"{seconds}秒")

            return {
                "boot_time": datetime.fromtimestamp(boot_timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                "uptime_seconds": uptime_seconds,
                "uptime_human": "".join(uptime_parts),
            }
        except Exception as e:
            return {"error": f"获取运行时间失败: {str(e)}"}

    def get_temperature_info(self):
        """获取温度传感器信息（跨平台）"""
        try:
            if IS_WINDOWS:
                return self._get_temperature_info_windows()
            else:
                return self._get_temperature_info_linux()
        except Exception as e:
            return {"sensors": [], "source": "error", "hint": str(e)}

    def _get_temperature_info_windows(self):
        # 方案1: LibreHardwareMonitor
        temps = self._query_lhm_sensors("Temperature")
        if temps:
            return {"sensors": temps, "source": "LibreHardwareMonitor"}

        # 方案2: WMI 原生
        try:
            import pythoncom
            pythoncom.CoInitialize()
            try:
                import wmi as wmi_mod
                wmi_std = wmi_mod.WMI(namespace="root\\wmi")
                thermal_zones = wmi_std.MSAcpi_ThermalZoneTemperature()
                sensors = []
                for i, zone in enumerate(thermal_zones):
                    temp_c = round((float(zone.CurrentTemperature) / 10.0) - 273.15, 2)
                    if -50 < temp_c < 150:
                        sensors.append({
                            "name": f"ACPI Thermal Zone {i}",
                            "value": temp_c,
                            "sensor_type": "Temperature",
                            "hardware_name": "ACPI Thermal Zone",
                        })
                if sensors:
                    return {"sensors": sensors, "source": "WMI_MSAcpi"}
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            pass

        return {"sensors": [], "source": "unavailable", "hint": "未检测到温度数据"}

    def _get_temperature_info_linux(self):
        sensors = []

        # 方案1: psutil sensors_temperatures（需要 lm-sensors）
        try:
            temps = psutil.sensors_temperatures()
            for chip_name, entries in temps.items():
                for entry in entries:
                    if entry.current is not None and entry.current > 0:
                        sensors.append({
                            "name": f"{chip_name} - {entry.label or 'temp'}",
                            "value": round(entry.current, 2),
                            "sensor_type": "Temperature",
                            "hardware_name": chip_name,
                        })
        except Exception:
            pass

        # 方案2: 直接读取 /sys/class/hwmon
        if not sensors:
            try:
                hwmon_path = "/sys/class/hwmon"
                if os.path.isdir(hwmon_path):
                    for hwmon in os.listdir(hwmon_path):
                        hwmon_dir = os.path.join(hwmon_path, hwmon)
                        name = _read_sys_file(os.path.join(hwmon_dir, "name")) or hwmon
                        for fname in sorted(os.listdir(hwmon_dir)):
                            if fname.startswith("temp") and fname.endswith("_input"):
                                val = _read_sys_file(os.path.join(hwmon_dir, fname))
                                if val:
                                    temp_c = round(int(val) / 1000.0, 2)
                                    if 0 < temp_c < 150:
                                        label = fname.replace("_input", "_label")
                                        label_val = _read_sys_file(os.path.join(hwmon_dir, label))
                                        sensors.append({
                                            "name": f"{name} - {label_val or fname}",
                                            "value": temp_c,
                                            "sensor_type": "Temperature",
                                            "hardware_name": name,
                                        })
            except Exception:
                pass

        if sensors:
            return {"sensors": sensors, "source": "hwmon/psutil"}

        return {"sensors": [], "source": "unavailable", "hint": "未检测到温度数据，请安装 lm-sensors"}

    def _query_lhm_sensors(self, sensor_type):
        """通过 LibreHardwareMonitor WMI 接口查询传感器数据（仅 Windows）"""
        if not IS_WINDOWS:
            return []
        try:
            import pythoncom
            pythoncom.CoInitialize()
            try:
                import wmi as wmi_mod
                lhm_wmi = wmi_mod.WMI(namespace="root\\LibreHardwareMonitor")
                sensors = lhm_wmi.Sensor(SensorType=sensor_type)
                results = []
                for sensor in sensors:
                    value = sensor.Value
                    if value is not None:
                        results.append({
                            "name": sensor.Name,
                            "value": round(float(value), 2),
                            "sensor_type": sensor.SensorType,
                            "hardware_name": sensor.Hardware if hasattr(sensor, 'Hardware') else "",
                        })
                return results
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            return []

    def get_fan_info(self):
        """获取风扇转速传感器信息（跨平台）"""
        try:
            if IS_WINDOWS:
                return self._get_fan_info_windows()
            else:
                return self._get_fan_info_linux()
        except Exception as e:
            return {"sensors": [], "source": "error", "hint": str(e)}

    def _get_fan_info_windows(self):
        fans = self._query_lhm_sensors("Fan")
        if fans:
            return {"sensors": fans, "source": "LibreHardwareMonitor"}

        try:
            c = _get_wmi()
            if c:
                for fan in c.Win32_Fan():
                    return {"sensors": [{
                        "name": fan.Name or "System Fan",
                        "value": int(fan.DesiredSpeed) if fan.DesiredSpeed else 0,
                        "sensor_type": "Fan",
                        "hardware_name": fan.SystemName or "",
                    }], "source": "WMI_Win32_Fan"}
        except Exception:
            pass

        return {"sensors": [], "source": "unavailable", "hint": "未检测到风扇数据"}

    def _get_fan_info_linux(self):
        sensors = []
        try:
            fans = psutil.sensors_fans()
            for chip_name, entries in fans.items():
                for entry in entries:
                    if entry.current is not None and entry.current > 0:
                        sensors.append({
                            "name": f"{chip_name} - {entry.label or 'fan'}",
                            "value": round(entry.current, 0),
                            "sensor_type": "Fan",
                            "hardware_name": chip_name,
                        })
        except Exception:
            pass

        if sensors:
            return {"sensors": sensors, "source": "hwmon/psutil"}

        return {"sensors": [], "source": "unavailable", "hint": "未检测到风扇数据，请安装 lm-sensors"}

    def get_voltage_info(self):
        """获取电压传感器信息（跨平台）"""
        try:
            if IS_WINDOWS:
                return self._get_voltage_info_windows()
            else:
                return self._get_voltage_info_linux()
        except Exception as e:
            return {"sensors": [], "source": "error", "hint": str(e)}

    def _get_voltage_info_windows(self):
        voltages = self._query_lhm_sensors("Voltage")
        if voltages:
            return {"sensors": voltages, "source": "LibreHardwareMonitor"}

        try:
            c = _get_wmi()
            if c:
                probes = c.Win32_VoltageProbe()
                sensors = []
                for probe in probes:
                    val = probe.CurrentReading
                    if val is not None:
                        sensors.append({
                            "name": probe.Description or probe.Name or "Voltage Probe",
                            "value": round(float(val) / 1000.0, 3) if abs(float(val)) > 10 else round(float(val), 3),
                            "sensor_type": "Voltage",
                            "hardware_name": probe.SystemName or "",
                        })
                if sensors:
                    return {"sensors": sensors, "source": "WMI_Win32_VoltageProbe"}
        except Exception:
            pass

        return {"sensors": [], "source": "unavailable", "hint": "未检测到电压数据"}

    def _get_voltage_info_linux(self):
        # Linux 下电压传感器一般通过 /sys/class/hwmon 获取
        sensors = []
        try:
            hwmon_path = "/sys/class/hwmon"
            if os.path.isdir(hwmon_path):
                for hwmon in os.listdir(hwmon_path):
                    hwmon_dir = os.path.join(hwmon_path, hwmon)
                    name = _read_sys_file(os.path.join(hwmon_dir, "name")) or hwmon
                    for fname in sorted(os.listdir(hwmon_dir)):
                        if fname.startswith("in") and fname.endswith("_input"):
                            val = _read_sys_file(os.path.join(hwmon_dir, fname))
                            if val:
                                voltage = round(int(val) / 1000.0, 3)
                                if 0 < voltage < 20:
                                    label = fname.replace("_input", "_label")
                                    label_val = _read_sys_file(os.path.join(hwmon_dir, label))
                                    sensors.append({
                                        "name": f"{name} - {label_val or fname}",
                                        "value": voltage,
                                        "sensor_type": "Voltage",
                                        "hardware_name": name,
                                    })
        except Exception:
            pass

        if sensors:
            return {"sensors": sensors, "source": "hwmon"}

        return {"sensors": [], "source": "unavailable", "hint": "未检测到电压数据，请安装 lm-sensors"}

    def collect_all(self):
        """采集所有硬件信息"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "system": self.get_system_info(),
            "cpu": self.get_cpu_info(),
            "memory": self.get_memory_info(),
            "disk": self.get_disk_info(),
            "gpu": self.get_gpu_info(),
            "network": self.get_network_info(),
            "motherboard": self.get_motherboard_info(),
            "bios": self.get_bios_info(),
            "uptime": self.get_uptime_info(),
            "temperature": self.get_temperature_info(),
            "fan": self.get_fan_info(),
            "voltage": self.get_voltage_info(),
        }
        return data


if __name__ == "__main__":
    collector = HardwareCollector()
    info = collector.collect_all()
    print(json.dumps(info, indent=2, ensure_ascii=False))
