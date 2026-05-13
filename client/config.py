"""
配置文件管理模块
使用JSON格式存储配置,支持自动创建默认配置
"""

import json
import os
from datetime import datetime


class ConfigManager:
    """配置管理器"""

    CONFIG_FILE = "config.json"

    # 默认配置
    DEFAULT_CONFIG = {
        "server": {
            "url": "http://localhost:5000",
            "timeout": 10,
            "retry_times": 3,
            "retry_interval": 60
        },
        "client": {
            "report_interval": 120,
            "auto_start": True,
            "client_id": "",
            "group_name": "",
            "listen_port": 13301
        },
        "logging": {
            "enabled": True,
            "log_file": "client.log",
            "max_size_mb": 10,
            "backup_count": 5
        },
        "advanced": {
            "collect_cpu": True,
            "collect_memory": True,
            "collect_disk": True,
            "collect_gpu": True,
            "collect_network": True,
            "collect_motherboard": True,
            "collect_bios": True,
            "compress_data": False
        }
    }

    def __init__(self, config_file=None):
        """初始化配置管理器"""
        if config_file:
            self.CONFIG_FILE = config_file
        self.config = self.load_config()

    def load_config(self):
        """加载配置文件,如果不存在则创建默认配置"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 合并默认配置(防止缺少字段)
                    return self._merge_config(self.DEFAULT_CONFIG.copy(), config)
            except Exception as e:
                print(f"加载配置文件失败: {str(e)},使用默认配置")
                return self.DEFAULT_CONFIG.copy()
        else:
            # 创建默认配置文件
            self.save_config(self.DEFAULT_CONFIG.copy())
            return self.DEFAULT_CONFIG.copy()

    def save_config(self, config=None):
        """保存配置到文件"""
        if config is None:
            config = self.config

        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {str(e)}")
            return False

    def _merge_config(self, default, custom):
        """递归合并配置字典"""
        merged = default.copy()
        for key, value in custom.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_config(merged[key], value)
            else:
                merged[key] = value
        return merged

    def get(self, *keys, default=None):
        """获取配置值,支持嵌套键访问"""
        current = self.config
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
        return current

    def set(self, value, *keys):
        """设置配置值,支持嵌套键访问"""
        current = self.config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        self.save_config()

    def get_server_url(self):
        """获取服务器URL"""
        return self.get('server', 'url')

    def get_report_interval(self):
        """获取上报间隔(秒)"""
        return self.get('client', 'report_interval')

    def get_client_id(self):
        """获取客户端ID"""
        client_id = self.get('client', 'client_id')
        if not client_id:
            # 生成新的客户端ID
            client_id = f"CLIENT_{datetime.now().strftime('%Y%m%d%H%M%S')}_{os.getpid()}"
            self.set(client_id, 'client', 'client_id')
        return client_id

    def is_auto_start(self):
        """是否开机自启"""
        return self.get('client', 'auto_start')

    def is_logging_enabled(self):
        """是否启用日志"""
        return self.get('logging', 'enabled')

    def get_log_file(self):
        """获取日志文件路径"""
        return self.get('logging', 'log_file')

    def should_collect(self, component):
        """是否采集指定组件"""
        return self.get('advanced', f'collect_{component}')

    def reset_to_default(self):
        """重置为默认配置"""
        self.config = self.DEFAULT_CONFIG.copy()
        self.save_config()

    def export_config(self, filepath):
        """导出配置到指定文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"导出配置失败: {str(e)}")
            return False

    def import_config(self, filepath):
        """从文件导入配置"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                new_config = json.load(f)
            self.config = self._merge_config(self.DEFAULT_CONFIG.copy(), new_config)
            self.save_config()
            return True
        except Exception as e:
            print(f"导入配置失败: {str(e)}")
            return False


# 全局配置实例
config_manager = ConfigManager()


if __name__ == "__main__":
    # 测试配置管理
    cfg = ConfigManager()

    print("当前配置:")
    print(json.dumps(cfg.config, indent=2, ensure_ascii=False))

    print("\n测试读取配置:")
    print(f"服务器URL: {cfg.get_server_url()}")
    print(f"上报间隔: {cfg.get_report_interval()}秒")
    print(f"客户端ID: {cfg.get_client_id()}")

    print("\n测试修改配置:")
    cfg.set("http://192.168.1.100:5000", 'server', 'url')
    cfg.set(600, 'client', 'report_interval')
    print(f"新服务器URL: {cfg.get_server_url()}")
    print(f"新上报间隔: {cfg.get_report_interval()}秒")
