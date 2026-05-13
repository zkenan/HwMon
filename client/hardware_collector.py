"""
硬件信息采集模块
采集Windows系统的硬件信息、MAC地址、IP地址和主机名
"""

import wmi
import socket
import uuid
import platform
import psutil
from datetime import datetime


class HardwareCollector:
    """硬件信息采集器"""

    def __init__(self):
        self.c = wmi.WMI()

    def get_system_info(self):
        """获取系统基本信息"""
        try:
            os_info = self.c.Win32_OperatingSystem()[0]
            return {
                "hostname": socket.gethostname(),
                "os_name": os_info.Caption,
                "os_version": os_info.Version,
                "os_architecture": platform.architecture()[0],
                "boot_time": str(psutil.boot_time()),
            }
        except Exception as e:
            return {"error": f"获取系统信息失败: {str(e)}"}

    def get_cpu_info(self):
        """获取CPU信息"""
        try:
            cpu_list = []
            for cpu in self.c.Win32_Processor():
                cpu_list.append({
                    "name": cpu.Name,
                    "cores": cpu.NumberOfCores,
                    "threads": cpu.NumberOfLogicalProcessors,
                    "max_clock_speed": cpu.MaxClockSpeed,
                    "manufacturer": cpu.Manufacturer,
                })
            return cpu_list
        except Exception as e:
            return [{"error": f"获取CPU信息失败: {str(e)}"}]

    def get_memory_info(self):
        """获取内存信息"""
        try:
            memory_list = []
            for mem in self.c.Win32_PhysicalMemory():
                memory_list.append({
                    "capacity": int(mem.Capacity),
                    "speed": mem.Speed,
                    "manufacturer": mem.Manufacturer,
                    "part_number": mem.PartNumber,
                })

            # 总内存
            total_memory = sum([m["capacity"] for m in memory_list])
            return {
                "modules": memory_list,
                "total_capacity": total_memory,
            }
        except Exception as e:
            return {"error": f"获取内存信息失败: {str(e)}"}

    def get_disk_info(self):
        """获取硬盘信息"""
        try:
            disk_list = []
            for disk in self.c.Win32_DiskDrive():
                disk_list.append({
                    "model": disk.Model,
                    "size": int(disk.Size) if disk.Size else 0,
                    "serial_number": disk.SerialNumber,
                    "interface_type": disk.InterfaceType,
                })
            return disk_list
        except Exception as e:
            return [{"error": f"获取硬盘信息失败: {str(e)}"}]

    def get_gpu_info(self):
        """获取显卡信息"""
        try:
            gpu_list = []
            for gpu in self.c.Win32_VideoController():
                gpu_list.append({
                    "name": gpu.Name,
                    "adapter_ram": int(gpu.AdapterRAM) if gpu.AdapterRAM else 0,
                    "driver_version": gpu.DriverVersion,
                })
            return gpu_list
        except Exception as e:
            return [{"error": f"获取显卡信息失败: {str(e)}"}]

    def get_network_info(self):
        """获取网络信息(MAC地址和IP地址)"""
        try:
            network_list = []
            for interface in self.c.Win32_NetworkAdapterConfiguration(IPEnabled=True):
                mac = interface.MACAddress
                if mac:
                    ips = interface.IPAddress if interface.IPAddress else []
                    network_list.append({
                        "mac_address": mac,
                        "ip_addresses": [ip for ip in ips if ip],
                        "description": interface.Description,
                    })
            return network_list
        except Exception as e:
            return [{"error": f"获取网络信息失败: {str(e)}"}]

    def get_motherboard_info(self):
        """获取主板信息"""
        try:
            for board in self.c.Win32_BaseBoard():
                return {
                    "manufacturer": board.Manufacturer,
                    "product": board.Product,
                    "serial_number": board.SerialNumber,
                }
            return {}
        except Exception as e:
            return {"error": f"获取主板信息失败: {str(e)}"}

    def get_bios_info(self):
        """获取BIOS信息"""
        try:
            for bios in self.c.Win32_BIOS():
                return {
                    "manufacturer": bios.Manufacturer,
                    "version": bios.Version,
                    "serial_number": bios.SerialNumber,
                    "release_date": bios.ReleaseDate,
                }
            return {}
        except Exception as e:
            return {"error": f"获取BIOS信息失败: {str(e)}"}

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
        }
        return data


if __name__ == "__main__":
    collector = HardwareCollector()
    info = collector.collect_all()
    import json
    print(json.dumps(info, indent=2, ensure_ascii=False))
