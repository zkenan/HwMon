"""
硬件对比维度配置
定义各硬件的对比维度和重要性级别

核心原则：可以占便宜但不能吃亏
- 高重要性：任何变化都告警（被盗/更换）
- 中重要性：降值告警（被偷换降级），升值不告警（升级）
- 低重要性：忽略（软件变化）
"""

# 对比维度配置
# high: 高重要性维度，任何变化都触发告警
# medium: 中重要性维度，降值触发告警，升值仅记录
# low: 低重要性维度，变化忽略
HARDWARE_COMPARE_CONFIG = {
    "cpu": {
        "high": ["name", "cores"],                    # 型号、核心数
        "medium": [],                                  # 无
        "low": ["max_clock_speed", "manufacturer"]    # 主频、制造商
    },
    "gpu": {
        "high": ["name"],                              # 型号名称
        "medium": ["adapter_ram"],                     # 显存容量
        "low": ["driver_version"]                      # 驱动版本
    },
    "memory": {
        "high": ["total_capacity"],                    # 总容量
        "medium": ["capacity", "speed"],               # 单条容量、频率
        "low": ["manufacturer"]                        # 制造商
    },
    "disk": {
        "high": ["model", "size"],                     # 型号、容量
        "medium": [],                                  # 无
        "low": ["interface_type"]                      # 接口类型
    },
    "network": {
        "high": ["mac_address"],                       # MAC地址
        "medium": [],                                  # 无
        "low": ["description"]                         # 网卡描述
    },
    "motherboard": {
        "high": ["manufacturer", "product"],           # 制造商、型号
        "medium": [],                                  # 无
        "low": ["serial_number"]                       # 序列号
    },
    "bios": {
        "high": ["manufacturer"],                      # 制造商
        "medium": [],                                  # 无
        "low": ["version"]                             # 版本
    }
}


def get_compare_config(hardware_type):
    """获取指定硬件类型的对比配置"""
    return HARDWARE_COMPARE_CONFIG.get(hardware_type, {
        "high": ["name"],
        "medium": [],
        "low": []
    })
