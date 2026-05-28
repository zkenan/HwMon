"""
进程资源监控模块
监控系统进程的 CPU、内存、GPU 占用情况
当占用超过阈值且持续时间超过指定时长时，触发告警上报
"""

import psutil
import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict


class ProcessMonitor:
    """进程资源监控器"""

    def __init__(self, config=None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.check_interval = self.config.get("check_interval", 30)
        self.thresholds = self.config.get("thresholds", {
            "cpu_percent": 90,
            "memory_percent": 90,
            "gpu_percent": 90
        })
        self.duration_seconds = self.config.get("duration_seconds", 300)
        self.ignore_processes = set(self.config.get("ignore_processes", [
            "System Idle Process", "System", "idle", "Idle"
        ]))
        self.gpu_enabled = self.config.get("gpu_enabled", False)

        # 高占用追踪器: key=(pid, name), value={"first_seen": datetime, "threshold_type": str, "last_data": dict}
        self.high_usage_tracker = {}

        # GPU 初始化
        self._nvml_initialized = False
        if self.gpu_enabled:
            self._init_gpu()

        # 上一次 CPU 采样时间（psutil 第一次调用 cpu_percent 总是返回 0）
        self._last_cpu_sample_time = 0
        # 预热一次采样
        for proc in psutil.process_iter(['pid']):
            try:
                proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def _init_gpu(self):
        """初始化 NVIDIA GPU 监控"""
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_initialized = True
            device_count = pynvml.nvmlDeviceGetCount()
            if device_count == 0:
                self._nvml_initialized = False
        except Exception:
            self._nvml_initialized = False

    def get_process_gpu_usage(self, pid):
        """获取指定进程的 GPU 使用率和显存占用

        返回: (gpu_percent, gpu_memory_mb) 或 (-1, 0) 如果不可用
        """
        if not self._nvml_initialized:
            return -1, 0

        try:
            import pynvml
            device_count = pynvml.nvmlDeviceGetCount()
            total_gpu_percent = 0
            total_gpu_memory = 0
            found = False

            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                try:
                    processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                    for proc in processes:
                        if proc.pid == pid:
                            found = True
                            mem_info = proc.usedGpuMemory
                            if mem_info is not None:
                                total_gpu_memory += mem_info / (1024 * 1024)

                            # 获取 GPU 利用率
                            try:
                                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                                total_gpu_percent = max(total_gpu_percent, util.gpu)
                            except Exception:
                                pass
                except Exception:
                    continue

                try:
                    processes_graphics = pynvml.nvmlDeviceGetGraphicsRunningProcesses(handle)
                    for proc in processes_graphics:
                        if proc.pid == pid:
                            found = True
                            mem_info = proc.usedGpuMemory
                            if mem_info is not None:
                                total_gpu_memory += mem_info / (1024 * 1024)
                except Exception:
                    continue

            if found:
                return round(total_gpu_percent, 1), round(total_gpu_memory, 1)
            return 0, 0

        except Exception:
            return -1, 0

    def collect_process_info(self):
        """采集所有进程的资源占用信息

        返回: {
            "processes": [...],          # 超过阈值的进程列表
            "system_summary": {...},     # 系统级汇总
            "sample_time": "ISO格式时间"
        }
        """
        if not self.enabled:
            return None

        sample_time = datetime.now()
        processes = []
        high_usage_procs = []

        # 系统级资源汇总
        system_cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        system_memory = mem.percent

        total_gpu_percent = -1
        if self._nvml_initialized:
            try:
                import pynvml
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                total_gpu_percent = util.gpu
            except Exception:
                pass

        for proc in psutil.process_iter(['pid', 'name', 'username', 'cmdline', 'create_time']):
            try:
                pid = proc.info['pid']
                name = proc.info['name'] or ""

                # 跳过忽略的进程
                if name in self.ignore_processes:
                    continue
                if pid == 0:
                    continue

                cpu_percent = proc.cpu_percent(interval=None)

                try:
                    mem_info = proc.memory_info()
                    mem_percent = proc.memory_percent()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    mem_percent = 0

                gpu_percent, gpu_memory = self.get_process_gpu_usage(pid)

                # 检查是否超过阈值
                threshold_type = None
                if cpu_percent >= self.thresholds.get("cpu_percent", 90):
                    threshold_type = "cpu"
                if mem_percent >= self.thresholds.get("memory_percent", 90):
                    threshold_type = threshold_type or "memory"
                if gpu_percent >= self.thresholds.get("gpu_percent", 90) and gpu_percent > 0:
                    threshold_type = threshold_type or "gpu"

                if threshold_type:
                    high_usage_procs.append({
                        "pid": pid,
                        "process_name": name,
                        "username": proc.info.get('username', ''),
                        "cmdline": ' '.join(proc.info.get('cmdline', [])[:5]) if proc.info.get('cmdline') else '',
                        "cpu_percent": round(cpu_percent, 1),
                        "memory_percent": round(mem_percent, 1),
                        "gpu_percent": gpu_percent,
                        "gpu_memory_mb": gpu_memory,
                        "threshold_type": threshold_type,
                    })

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception:
                continue

        return {
            "processes": high_usage_procs,
            "system_summary": {
                "total_cpu_percent": round(system_cpu, 1),
                "total_memory_percent": round(system_memory, 1),
                "total_gpu_percent": total_gpu_percent
            },
            "sample_time": sample_time.isoformat()
        }

    def check_and_get_alerts(self):
        """执行一次检查，更新 tracker，返回触发告警的进程列表

        返回: {
            "alerts": [...],        # 持续超时需上报的进程
            "system_summary": {...},
            "timestamp": "ISO格式时间"
        }
        或 None（无告警或功能关闭）
        """
        if not self.enabled:
            return None

        result = self.collect_process_info()
        if result is None:
            return None

        now = datetime.now()
        current_keys = set()
        alerts = []

        for proc in result["processes"]:
            key = (proc["pid"], proc["process_name"])
            current_keys.add(key)

            if key in self.high_usage_tracker:
                # 已在追踪中，检查是否达到持续时间
                tracker = self.high_usage_tracker[key]
                elapsed = (now - tracker["first_seen"]).total_seconds()

                if elapsed >= self.duration_seconds:
                    # 达到阈值，触发告警
                    alert = proc.copy()
                    alert["exceeded_since"] = tracker["first_seen"].isoformat()
                    alert["duration_seconds"] = int(elapsed)
                    alerts.append(alert)
                    # 重置 tracker，避免重复上报
                    self.high_usage_tracker.pop(key)
            else:
                # 新增追踪
                self.high_usage_tracker[key] = {
                    "first_seen": now,
                    "threshold_type": proc["threshold_type"],
                    "last_data": proc
                }

        # 清理已退出进程的 tracker
        stale_keys = set(self.high_usage_tracker.keys()) - current_keys
        for key in stale_keys:
            # 检查进程是否还存在
            try:
                p = psutil.Process(key[0])
                if not p.is_running():
                    del self.high_usage_tracker[key]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                del self.high_usage_tracker[key]

        if alerts:
            return {
                "alerts": alerts,
                "system_summary": result["system_summary"],
                "timestamp": now.isoformat()
            }

        return None

    def get_tracker_status(self):
        """获取当前 tracker 状态（用于调试/展示）"""
        status = []
        now = datetime.now()
        for key, tracker in self.high_usage_tracker.items():
            elapsed = (now - tracker["first_seen"]).total_seconds()
            status.append({
                "pid": key[0],
                "process_name": key[1],
                "threshold_type": tracker["threshold_type"],
                "tracking_since": tracker["first_seen"].isoformat(),
                "elapsed_seconds": int(elapsed),
                "remaining_seconds": max(0, int(self.duration_seconds - elapsed)),
                "last_data": tracker["last_data"]
            })
        return status

    def clear_tracker(self):
        """清除所有追踪记录"""
        self.high_usage_tracker.clear()


if __name__ == "__main__":
    import json

    print("=== 进程资源监控测试 ===")
    print(f"阈值设置: CPU={90}%, 内存={90}%, 持续时间={300}秒")
    print(f"检查间隔: {30}秒")
    print()

    monitor = ProcessMonitor({
        "enabled": True,
        "check_interval": 30,
        "thresholds": {"cpu_percent": 90, "memory_percent": 90, "gpu_percent": 90},
        "duration_seconds": 300,
        "gpu_enabled": False
    })

    # 执行一次采集
    result = monitor.collect_process_info()
    if result:
        print(f"系统汇总: CPU={result['system_summary']['total_cpu_percent']}%, "
              f"内存={result['system_summary']['total_memory_percent']}%")
        print(f"超过阈值的进程数: {len(result['processes'])}")
        for p in result["processes"]:
            print(f"  PID={p['pid']} {p['process_name']} "
                  f"CPU={p['cpu_percent']}% MEM={p['memory_percent']}% "
                  f"({p['threshold_type']})")
    else:
        print("功能已关闭或无数据")

    print()
    print("Tracker 状态:")
    for s in monitor.get_tracker_status():
        print(f"  {s}")
