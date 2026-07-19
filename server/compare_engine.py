"""
智能硬件变更检测引擎

核心原则：可以占便宜但不能吃亏
- 新增硬件 → 不告警（可能是驱动安装）
- 丢失硬件 → 必须告警（可能是被盗）
- 升级（6G→8G）→ 不告警
- 降级（8G→6G）→ 告警
"""

import logging
from collections import Counter
from compare_config import get_compare_config

logger = logging.getLogger('hwmon')


def compare_attributes(baseline_item, new_item, hardware_type="gpu"):
    """
    对比单个物品的属性变化

    参数:
        baseline_item: 基准物品（字典）
        new_item: 新数据物品（字典）
        hardware_type: 硬件类型（cpu/gpu/memory/disk等）

    返回:
        {
            "type": "unchanged" | "upgraded" | "downgraded" | "critical",
            "dimension": "变化的维度",
            "old": 旧值,
            "new": 新值
        }
    """
    config = get_compare_config(hardware_type)
    high_dims = config.get("high", [])
    medium_dims = config.get("medium", [])
    low_dims = config.get("low", [])

    # 对比高重要性维度（任何变化都告警）
    for dim in high_dims:
        old_val = baseline_item.get(dim)
        new_val = new_item.get(dim)
        if old_val is not None and new_val is not None and old_val != new_val:
            return {
                "type": "critical",
                "dimension": dim,
                "old": old_val,
                "new": new_val
            }

    # 对比中重要性维度（降值告警，升值不告警）
    for dim in medium_dims:
        old_val = baseline_item.get(dim, 0)
        new_val = new_item.get(dim, 0)

        if old_val and new_val and old_val != new_val:
            if new_val < old_val:
                # 降值 → 告警
                return {
                    "type": "downgraded",
                    "dimension": dim,
                    "old": old_val,
                    "new": new_val
                }
            else:
                # 升值 → 仅记录
                return {
                    "type": "upgraded",
                    "dimension": dim,
                    "old": old_val,
                    "new": new_val
                }

    # 无变化
    return {"type": "unchanged"}


def compare_items(baseline_items, new_items, hardware_type="gpu"):
    """
    智能对比算法

    核心原则：可以占便宜但不能吃亏

    参数:
        baseline_items: 基准物品列表（字典列表）
        new_items: 新数据物品列表（字典列表）
        hardware_type: 硬件类型

    返回:
        {
            "lost": [...],        # 丢失的物品（需要告警）
            "downgraded": [...],  # 降级的物品（需要告警）
            "upgraded": [...],    # 升级的物品（仅记录）
            "unchanged": [...]    # 无变化
        }
    """
    result = {
        "lost": [],
        "downgraded": [],
        "upgraded": [],
        "unchanged": []
    }

    if not baseline_items:
        return result

    if not new_items:
        # 基准有但新数据没有 → 全部丢失
        for item in baseline_items:
            result["lost"].append({
                "item": item.get("name", "未知"),
                "detail": item,
                "message": f"{hardware_type} {item.get('name', '未知')} 丢失"
            })
        return result

    # 统计基准中的物品（按名称计数）
    baseline_counter = Counter()
    for item in baseline_items:
        name = item.get("name", str(item))
        baseline_counter[name] += 1

    # 统计新数据中的物品（按名称计数）
    new_counter = Counter()
    for item in new_items:
        name = item.get("name", str(item))
        new_counter[name] += 1

    # 对比数量
    for name, baseline_count in baseline_counter.items():
        new_count = new_counter.get(name, 0)

        if new_count < baseline_count:
            # 数量减少 → 丢失
            lost_count = baseline_count - new_count
            result["lost"].append({
                "item": name,
                "count": lost_count,
                "message": f"{hardware_type} {name} 丢了 {lost_count} 个"
            })
        elif new_count == baseline_count:
            # 数量相同 → 对比属性
            baseline_item = next((i for i in baseline_items if i.get("name") == name), None)
            new_item = next((i for i in new_items if i.get("name") == name), None)

            if baseline_item and new_item:
                change = compare_attributes(baseline_item, new_item, hardware_type)

                if change["type"] == "critical":
                    # 高重要性变化 → 丢失
                    result["lost"].append({
                        "item": name,
                        "dimension": change["dimension"],
                        "old": change["old"],
                        "new": change["new"],
                        "message": f"{hardware_type} {name} {change['dimension']} 变化: {change['old']} → {change['new']}"
                    })
                elif change["type"] == "downgraded":
                    # 中重要性降值 → 降级告警
                    result["downgraded"].append({
                        "item": name,
                        "dimension": change["dimension"],
                        "old": change["old"],
                        "new": change["new"],
                        "message": f"{hardware_type} {name} 降级: {change['dimension']} {change['old']} → {change['new']}"
                    })
                elif change["type"] == "upgraded":
                    # 中重要性升值 → 仅记录
                    result["upgraded"].append({
                        "item": name,
                        "dimension": change["dimension"],
                        "old": change["old"],
                        "new": change["new"],
                        "message": f"{hardware_type} {name} 升级: {change['dimension']} {change['old']} → {change['new']}"
                    })
                else:
                    # 无变化
                    result["unchanged"].append(name)
        # new_count > baseline_count: 数量增加，新增的不管

    return result


def should_trigger_alert(compare_result):
    """
    判断是否应该触发告警

    返回:
        True: 需要告警（有丢失或降级）
        False: 不需要告警（仅升级或无变化）
    """
    return bool(compare_result.get("lost")) or bool(compare_result.get("downgraded"))


def format_alert_message(compare_result, hardware_type="硬件"):
    """格式化告警消息"""
    messages = []

    for item in compare_result.get("lost", []):
        messages.append(f"⚠️ 丢失: {item['message']}")

    for item in compare_result.get("downgraded", []):
        messages.append(f"⚠️ 降级: {item['message']}")

    for item in compare_result.get("upgraded", []):
        messages.append(f"ℹ️ 升级: {item['message']}（仅记录）")

    return messages
