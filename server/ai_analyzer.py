"""
AI 研判引擎模块
调用 OpenAI 兼容接口对进程告警数据进行智能分析
支持任何实现 OpenAI Chat Completions API 的服务
"""

import json
import requests
from datetime import datetime, timezone, timedelta

# 东八区固定时区
_CST = timezone(timedelta(hours=8), name='CST')


DEFAULT_SYSTEM_PROMPT = """你是一位 IT 运维专家，负责分析服务器/工作站的进程资源占用告警。
请对以下进程告警数据进行分析，严格按照以下 JSON 格式返回结果（不要包含其他文字）：

{
  "risk_level": "低/中/高/紧急",
  "analysis": "详细的分析说明，包括每个异常进程的情况",
  "recommendations": ["建议1", "建议2", "建议3"],
  "need_immediate_action": true/false
}

分析要点：
1. 评估整体风险等级（考虑 CPU/内存/GPU 占用程度和持续时间）
2. 分析每个异常进程的可能原因（正常业务负载？内存泄漏？异常进程？挖矿程序？）
3. 给出具体可执行的处理建议
4. 判断是否需要立即人工介入

如果进程名称和命令行看起来像恶意软件（挖矿、病毒等），风险等级应为"紧急"。"""


def analyze_process_alert(alert_data, ai_config):
    """调用 AI 接口分析进程告警数据

    参数:
        alert_data: 进程告警数据字典，包含 alerts 和 system_summary
        ai_config: AI 配置字典，包含 api_base_url, api_key, model 等

    返回:
        {
            "risk_level": "高",
            "analysis": "...",
            "recommendations": [...],
            "need_immediate_action": true/false,
            "model_used": "gpt-4o-mini",
            "analyzed_at": "2026-05-26T14:31:00"
        }
    或 None（配置未启用或调用失败）
    """
    if not ai_config.get("enabled"):
        return None

    api_base_url = ai_config.get("api_base_url", "").rstrip("/")
    api_key = ai_config.get("api_key", "")
    model = ai_config.get("model", "gpt-4o-mini")
    max_tokens = ai_config.get("max_tokens", 2000)
    temperature = float(ai_config.get("temperature", 0.3))
    system_prompt = ai_config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT

    if not api_base_url or not api_key:
        return {"error": "AI 配置不完整：缺少 api_base_url 或 api_key"}

    # 构建用户消息
    user_message = _build_user_message(alert_data)

    # 构建请求
    url = f"{api_base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=300)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 尝试解析 JSON 响应
        analysis_result = _parse_ai_response(content)

        analysis_result["model_used"] = model
        analysis_result["analyzed_at"] = datetime.now(_CST).isoformat()
        analysis_result["raw_response"] = content

        return analysis_result

    except requests.exceptions.Timeout:
        return {"error": "AI 接口调用超时（60秒）", "analyzed_at": datetime.now(_CST).isoformat()}
    except requests.exceptions.ConnectionError:
        return {"error": f"无法连接到 AI 接口: {api_base_url}", "analyzed_at": datetime.now(_CST).isoformat()}
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json().get("error", {}).get("message", str(e))
        except Exception:
            error_detail = str(e)
        return {"error": f"AI 接口返回错误: {error_detail}", "analyzed_at": datetime.now(_CST).isoformat()}
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return {"error": f"AI 响应解析失败: {str(e)}", "analyzed_at": datetime.now(_CST).isoformat()}
    except Exception as e:
        return {"error": f"AI 分析异常: {str(e)}", "analyzed_at": datetime.now(_CST).isoformat()}


def test_ai_connection(ai_config):
    """测试 AI 接口连通性

    返回: (success: bool, message: str)
    """
    api_base_url = ai_config.get("api_base_url", "").rstrip("/")
    api_key = ai_config.get("api_key", "")
    model = ai_config.get("model", "gpt-4o-mini")

    if not api_base_url or not api_key:
        return False, "请填写 API 地址和 Key"

    url = f"{api_base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "回复OK两个字"}
        ],
        "max_tokens": 64
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return True, f"连接成功！模型响应: {content[:100]}"
    except requests.exceptions.Timeout:
        return False, "连接超时（30秒）"
    except requests.exceptions.ConnectionError:
        return False, f"无法连接到 {api_base_url}"
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json().get("error", {}).get("message", str(e))
        except Exception:
            error_detail = str(e)
        return False, f"接口错误: {error_detail}"
    except Exception as e:
        return False, f"测试失败: {str(e)}"


def _build_user_message(alert_data):
    """构建发送给 AI 的用户消息"""
    alerts = alert_data.get("alerts", [])
    summary = alert_data.get("system_summary", {})
    timestamp = alert_data.get("timestamp", "")

    msg_parts = [
        f"## 进程资源告警",
        f"**告警时间**: {timestamp}",
        f"",
        f"### 系统整体资源占用",
        f"- CPU 总占用: {summary.get('total_cpu_percent', 'N/A')}%",
        f"- 内存总占用: {summary.get('total_memory_percent', 'N/A')}%",
    ]

    if summary.get("total_gpu_percent", -1) >= 0:
        msg_parts.append(f"- GPU 总占用: {summary.get('total_gpu_percent')}%")

    msg_parts.append("")
    msg_parts.append(f"### 异常进程列表（共 {len(alerts)} 个）")
    msg_parts.append("")

    for i, alert in enumerate(alerts, 1):
        msg_parts.append(f"#### 进程 {i}: {alert.get('process_name', 'unknown')}")
        msg_parts.append(f"- PID: {alert.get('pid')}")
        msg_parts.append(f"- 用户: {alert.get('username', 'N/A')}")
        msg_parts.append(f"- 命令行: {alert.get('cmdline', 'N/A')}")
        msg_parts.append(f"- CPU 占用: {alert.get('cpu_percent', 'N/A')}%")
        msg_parts.append(f"- 内存占用: {alert.get('memory_percent', 'N/A')}%")

        if alert.get("gpu_percent", -1) >= 0:
            msg_parts.append(f"- GPU 占用: {alert.get('gpu_percent')}%")
            msg_parts.append(f"- GPU 显存: {alert.get('gpu_memory_mb', 0)} MB")

        msg_parts.append(f"- 超标类型: {alert.get('threshold_type', 'N/A')}")
        msg_parts.append(f"- 超标开始时间: {alert.get('exceeded_since', 'N/A')}")
        msg_parts.append(f"- 持续时间: {alert.get('duration_seconds', 0)} 秒")
        msg_parts.append("")

    return "\n".join(msg_parts)


def _parse_ai_response(content):
    """解析 AI 返回的 JSON 响应

    AI 可能返回纯 JSON 或包含其他文字，尝试从中提取 JSON
    """
    content = content.strip()

    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 块（可能被 ```json 包裹）
    if "```json" in content:
        start = content.index("```json") + 7
        end = content.index("```", start)
        json_str = content[start:end].strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    if "```" in content:
        start = content.index("```") + 3
        # 跳过可能的语言标识符
        newline_pos = content.find("\n", start)
        if newline_pos != -1:
            start = newline_pos + 1
        end = content.index("```", start)
        json_str = content[start:end].strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # 尝试找到第一个 { 和最后一个 }
    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_str = content[first_brace:last_brace + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # 如果都失败，返回原始文本作为分析结果
    return {
        "risk_level": "未知",
        "analysis": content,
        "recommendations": ["AI 返回格式无法解析，请查看原始响应"],
        "need_immediate_action": False
    }


if __name__ == "__main__":
    # 测试用例
    test_alert = {
        "alerts": [
            {
                "pid": 1234,
                "process_name": "python.exe",
                "username": "SYSTEM",
                "cmdline": "python main.py --verbose",
                "cpu_percent": 95.2,
                "memory_percent": 12.3,
                "gpu_percent": -1,
                "gpu_memory_mb": 0,
                "threshold_type": "cpu",
                "exceeded_since": "2026-05-26T14:25:00",
                "duration_seconds": 300
            }
        ],
        "system_summary": {
            "total_cpu_percent": 87.5,
            "total_memory_percent": 72.1,
            "total_gpu_percent": -1
        },
        "timestamp": "2026-05-26T14:30:00"
    }

    print("构建的 AI 消息:")
    print(_build_user_message(test_alert))
