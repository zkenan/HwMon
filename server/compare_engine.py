"""
智能硬件变更检测引擎

核心原则：可以占便宜但不能吃亏
- 新增硬件 → 不告警（可能是驱动安装）
- 丢失硬件 → 必须告警（可能是被盗）
- 升级（6G→8G）→ 不告警
- 降级（8G→6G）→ 告警
"""

import logging
import json
import re
from collections import Counter
from compare_config import get_compare_config

logger = logging.getLogger('hwmon')


def _norm(value):
    """归一化字段值：去首尾空白，None 转空串"""
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    return value


def normalize_gpu_name(name):
    """归一化 GPU 型号名，消除驱动更新/命名格式差异导致的误报。

    背景：Windows 显卡名称会随驱动更新带 WDDM 后缀、厂商前缀变化，
    例如：
      "NVIDIA GeForce RTX 4060"                        -> "rtx 4060"
      "NVIDIA GeForce RTX 4060 (Microsoft Corporation - WDDM)" -> "rtx 4060"
      "Intel(R) UHD Graphics 770"                      -> "uhd graphics 770"
      "AMD Radeon RX 6800 XT"                          -> "radeon rx 6800 xt"
    同一块显卡在驱动更新前后归一化结果一致，从而不再误报「型号变化」。
    """
    if not name:
        return ''
    low = str(name).strip().lower()

    # NVIDIA 独显：RTX/GTX/Quadro/Tesla/TITAN + 型号数字（含可选字母后缀，如 Ti/Super）
    m = re.search(r'\b(rtx|gtx|quadro|tesla|titan)\s+([a-z]?\d{3,4}(?:\s*[a-z]{1,6})?)\b', low)
    if m:
        model = re.sub(r'\s+', ' ', m.group(2)).strip()
        return f"{m.group(1)} {model}"

    # GeForce（老命名，如 "GeForce GTX 1060" / "GeForce RTX 3060"）：
    # 尝试再往里取具体前缀+数字
    m = re.search(r'\b(geforce)\s+(?:(rtx|gtx|gt)\s+)?([a-z]?\d{3,4}(?:\s*[a-z]{1,6})?)\b', low)
    if m:
        prefix = m.group(2) or 'geforce'
        model = re.sub(r'\s+', ' ', m.group(3)).strip()
        return f"{prefix} {model}"

    # Intel 集显 / 独显
    m = re.search(r'\b(uhd\s*graphics\s*\d{3,4}|hd\s*graphics\s*\d{3,4}|iris\s*xe(?:\s*graphics)?|arc\s+[a-z]?\d{3,4}[a-z]?)\b', low)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).strip()

    # AMD
    m = re.search(r'\b(radeon(?:\s+(?:rx|pro)\s*\d{3,4}[a-z]*)?(?:\s+\d{3,4}[a-z]*)?)\b', low)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).strip()

    # 兜底：去括号、去厂商/驱动噪声词、压缩空白
    s2 = re.sub(r'\([^)]*\)', '', low)
    s2 = re.sub(r'\b(microsoft|corporation|wddm|nvidia|intel|amd|advanced micro devices|\(r\)|\(tm\))\b', '', s2)
    s2 = re.sub(r'\s+', ' ', s2).strip()
    return s2


# Windows 占位显卡特征（独显驱动未加载/虚拟环境时出现，非真实硬件）
_PLACEHOLDER_GPU_MARKERS = [
    'basic display adapter',
    'basic render driver',
    'remote display adapter',
    'hyper-v video',
    'virtualbox graphics adapter',
    'vmware svga',
    'standard vga graphics adapter',
    'microsoft display adapter',
]


def is_placeholder_gpu(name):
    """判断是否为 Windows 占位显卡（独显驱动未加载时的临时显卡，非真实硬件）。

    背景：Windows 在独显驱动未加载时会枚举出「Microsoft Basic Display Adapter」等
    临时显卡，驱动加载后它消失、真实独显出现。若把占位显卡当作真实硬件对比，
    会出现「basic display adapter 丢失 → 误报」的问题（用户实测踩坑）。

    返回 True 表示该名称是占位显卡，应被过滤、不参与对比、不写告警。
    """
    if not name:
        return False
    low = str(name).strip().lower()
    for marker in _PLACEHOLDER_GPU_MARKERS:
        if marker in low:
            return True
    return False


def is_placeholder_cpu_name(name):
    """判断是否为 CPU 占位底层名（虚拟机/无驱动环境下 Windows 返回的底层标识）。

    特征：以 Intel64/AMD64/Intel/AMD 开头 + "Family X Model Y Stepping Z"。
    例如 "Intel64 Family 6 Model 60 Stepping 3, GenuineIntel"。
    这类名字不是友好型号名（如 "Intel(R) Core(TM) i5-4590 CPU @ 3.30GHz"）。
    """
    if not name:
        return False
    low = str(name).strip().lower()
    return bool(re.search(r'^(intel64|amd64|intel|amd)\s+family\s+\d+', low))


def _item_key(item, hardware_type):
    """生成硬件的稳定身份标识，用于计数对比。

    问题背景：内存条/磁盘采集项没有 name 字段，旧逻辑回退到 str(item)
    （整个字典字符串），导致 part_number 尾部空格或字段顺序差异被误判为
    「不同物品 → 数量减少 → 丢失」。

    本函数返回一个稳定、去抖动的 key：
      - 有 name 字段 → 用归一化后的 name
      - 无 name 时按硬件类型回退到稳定字段组合
      - 最终兜底用确定性 JSON 序列化
    """
    if not isinstance(item, dict):
        return str(item)

    name = _norm(item.get('name'))
    if name:
        if hardware_type == 'cpu':
            # CPU 身份用稳定特征（核心数+线程数）识别，避免 name 命名格式差异导致 key 不匹配。
            # 背景：客户端 CPU 采集字段曾从 WMI 友好名（"Intel(R) Core(TM) i5-4590 CPU @ 3.30GHz"）
            #       变为底层名（"Intel64 Family 6 Model 60 Stepping 3, GenuineIntel"），同一颗 CPU
            #       两种命名，若直接用 name 做 key 会误判「cpu 丢了 1 个」。
            # 去 vendor：manufacturer 字段在驱动加载前后可能为空/非空，也会导致 key 抖动，
            # 因此只用 核心数|线程数 作为稳定身份（同一物理机这两者不变）。
            cores = item.get('cores') or item.get('number_of_cores') or ''
            threads = item.get('threads') or item.get('number_of_logical_processors') or ''
            return f"cpu:{cores}|{threads}"
        if hardware_type == 'gpu':
            # GPU 用归一化型号做 key，消除驱动更新导致的名称抖动
            return normalize_gpu_name(name)
        return name

    if hardware_type == 'memory':
        part_number = _norm(item.get('part_number'))
        capacity = _norm(item.get('capacity'))
        if part_number:
            return f"{part_number}|{capacity}"

    if hardware_type == 'disk':
        serial = _norm(item.get('serial_number'))
        model = _norm(item.get('model'))
        if serial or model:
            return f"{serial}|{model}"

    # 兜底：确定性序列化（key 排序，消除字段顺序与多余空白）
    try:
        return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        return str(item)


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

    # 对比高重要性维度（任何变化都告警；字符串值先归一化去首尾空白）
    for dim in high_dims:
        old_val = baseline_item.get(dim)
        new_val = new_item.get(dim)
        if old_val is not None and new_val is not None and _norm(old_val) != _norm(new_val):
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

        if old_val and new_val and _norm(old_val) != _norm(new_val):
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

    # GPU 占位显卡过滤：占位显卡（Basic Display Adapter 等）不是真实硬件，
    # 从 baseline 与 new 两侧都过滤掉，避免驱动加载前后「占位显卡消失」被误报丢失。
    # 同时记录本次上报是否处于「占位状态」（=独显驱动尚未加载完成），供上层在
    # 占位状态时抑制 GPU 丢失告警。
    if hardware_type == 'gpu':
        new_has_placeholder = bool(new_items) and any(
            isinstance(i, dict) and is_placeholder_gpu(i.get('name'))
            for i in new_items
        )
        baseline_items = [i for i in baseline_items
                          if not (isinstance(i, dict) and is_placeholder_gpu(i.get('name')))]
        new_items = [i for i in new_items
                     if not (isinstance(i, dict) and is_placeholder_gpu(i.get('name')))]
        if new_has_placeholder:
            result['gpu_placeholder'] = True

    if not baseline_items:
        return result

    if not new_items:
        # 基准有但新数据为空 → 可能是采集失败/虚拟设备时有时无（如无独显
        # 机器的 Microsoft Basic Display Adapter）。构造「丢失」候选，但标记
        # empty=True，交由上层按「连续 N 次空采集」策略决定是否真正告警。
        for item in baseline_items:
            result["lost"].append({
                "item": _item_key(item, hardware_type),
                "detail": item,
                "message": f"{hardware_type} {_item_key(item, hardware_type)} 丢失"
            })
        result['empty'] = True
        return result

    # 统计基准中的物品（按稳定 key 计数）
    baseline_counter = Counter()
    for item in baseline_items:
        baseline_counter[_item_key(item, hardware_type)] += 1

    # 统计新数据中的物品（按稳定 key 计数）
    new_counter = Counter()
    for item in new_items:
        new_counter[_item_key(item, hardware_type)] += 1

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
            # 数量相同 → 对比属性（用同一稳定 key 找回 item）
            baseline_item = next((i for i in baseline_items if _item_key(i, hardware_type) == name), None)
            new_item = next((i for i in new_items if _item_key(i, hardware_type) == name), None)

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


def apply_manual_baseline(baseline_items, hardware_type, selected_keys=None, manual_overrides=None):
    """根据「手动基准」配置过滤并覆盖基准条目。

    手动基准的两种设定（对应产品需求）：
      1. 勾选纳入项：只对比用户勾选的硬件条目，未勾选的（如集显、易抖动项）
         后续增减/变值一律不告警 —— 通过 selected_keys 实现。
      2. 手动改值：用户可逐字段覆盖某条目的基准值，覆盖后优先级最高 ——
         通过 manual_overrides 实现。

    参数:
        baseline_items: 基准条目列表（字典列表）
        hardware_type: 硬件类型（cpu/gpu/memory/disk）
        selected_keys: 勾选纳入的条目 key 集合（_item_key 的结果）；
                       None = 未配置（全量纳入，向后兼容）；
                       空集合 = 该类型整体不纳入对比（用户取消全部勾选，
                       后续任何增减/变值一律不告警）
        manual_overrides: {item_key: {field: value}} 字段覆盖；优先级最高

    返回:
        过滤 + 覆盖后的 baseline_items 列表
    """
    if not baseline_items:
        return baseline_items

    # 注意：空列表/空集合是有效配置（=该类型全部不监控），
    # 只有 None 才表示"未配置"（=全量，向后兼容）
    has_filter = selected_keys is not None
    has_override = bool(manual_overrides)

    if not has_filter and not has_override:
        return baseline_items

    result = []
    for item in baseline_items:
        key = _item_key(item, hardware_type)

        # 1) 过滤：仅保留勾选项（未勾选不参与对比）
        if has_filter and key not in selected_keys:
            continue

        # 2) 覆盖：手动值优先（覆盖基准字段后再参与对比）
        if has_override and key in manual_overrides:
            item = dict(item)
            item.update(manual_overrides[key])

        result.append(item)

    return result
