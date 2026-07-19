# HwMon 硬件监控系统 v5.0.1

一个用于自动采集Windows客户端硬件信息并上报到服务端的系统，支持分组管理、硬件变更检测、AI智能分析和数据导出。

## 功能特性

### 客户端
- 自动采集硬件信息（CPU、内存、硬盘、显卡、网卡、主板、BIOS）
- 采集温度传感器、风扇转速、电压（需LibreHardwareMonitor）
- 进程监控（CPU/内存/GPU高占用告警）
- 本地HTTP服务（端口13301）供服务端主动采集
- 开机自启动（静默运行）
- 定时上报（可配置间隔）
- 支持打包为独立exe程序

### 服务端
- Web管理界面（深色/浅色主题，1Panel风格UI）
- 仪表盘实时监控（客户端数、在线数、分组数、告警数）
- 自定义分组管理
- 客户端列表全选 + 批量删除
- 硬件变更自动检测 + 邮件告警
- 告警中心（未解决/已解决标签页，全选批量操作）
- 主机探测（Ping/HTTP/TCP，自动告警）
- AI研判（进程告警智能分析）
- 数据导出（Excel/CSV）
- 客户端在线状态检测
- 智能轮询（60秒间隔，页面可见时刷新）
- 登录认证 + 速率限制

## 项目结构

```
HwMon/
├── client/                     # 客户端目录
│   ├── client.py              # 主程序
│   ├── hardware_collector.py  # 硬件采集模块（含温度/风扇/电压）
│   ├── config.py              # 配置管理模块
│   ├── service.py             # Windows服务管理
│   ├── process_monitor.py     # 进程监控
│   ├── config.example.json    # 配置示例文件
│   └── requirements.txt       # Python依赖
├── server/                    # 服务端目录
│   ├── app.py                 # Flask主应用（含所有API）
│   ├── start_server.py        # 启动脚本（设置环境变量）
│   ├── auth.py                # 登录认证 + 速率限制
│   ├── validators.py          # 输入验证
│   ├── cache.py               # Redis缓存
│   ├── celery_app.py          # Celery异步任务
│   ├── ai_analyzer.py         # AI智能分析
│   ├── compare_engine.py      # 硬件变更检测引擎
│   ├── Dockerfile             # Docker构建文件
│   ├── templates/
│   │   ├── index.html         # Web管理界面（v5.0.1 UI）
│   │   └── login.html         # 登录页面
│   └── requirements.txt       # Python依赖
├── docker-compose.yml         # Docker编排文件
└── .env.example               # 环境变量模板
```

## 快速开始

### 方式一：Docker部署（推荐）

1. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 设置数据库、Redis等配置
```

2. 启动服务：
```bash
docker compose up -d
```

3. 访问Web界面：`http://你的服务器IP:5000`

4. 默认账号：`admin` / `admin123`

### 方式二：Python直接运行

#### 服务端部署

1. 安装依赖：
```bash
cd server
pip install -r requirements.txt
```

2. 设置环境变量并启动：
```bash
export DB_HOST=192.168.20.27
export DB_PORT=3306
export DB_USER=hwmon
export DB_PASSWORD=hwmon
export DB_NAME=hwmon
python start_server.py
```

#### 客户端部署

1. 安装依赖：
```bash
cd client
pip install -r requirements.txt
```

2. 配置服务器地址，复制 `config.example.json` 为 `config.json`：
```json
{
    "server": {
        "url": "http://你的服务器IP:5000"
    }
}
```

3. 运行客户端：
```bash
python client.py
```

### 方式三：打包为exe

```bash
cd client
python build_exe.py
```

## 环境配置

### 数据库配置

系统使用MySQL数据库，需提前创建：
```sql
CREATE DATABASE hwmon CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'hwmon'@'%' IDENTIFIED BY 'hwmon';
GRANT ALL PRIVILEGES ON hwmon.* TO 'hwmon'@'%';
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DB_HOST | 数据库地址 | 192.168.20.27 |
| DB_PORT | 数据库端口 | 3306 |
| DB_USER | 数据库用户 | hwmon |
| DB_PASSWORD | 数据库密码 | hwmon |
| DB_NAME | 数据库名 | hwmon |
| REDIS_HOST | Redis地址 | 192.168.20.27 |
| REDIS_PORT | Redis端口 | 6379 |
| REDIS_PASSWORD | Redis密码 | - |
| LOGIN_USERNAME | 登录用户名 | admin |
| LOGIN_PASSWORD | 登录密码 | admin123 |
| SECRET_KEY | Session密钥 | - |

## 硬件变更检测

系统自动对比客户端上报的硬件信息与基准数据，检测以下变更：

- **丢失硬件**：必须告警（防盗场景）
- **降级告警**：如8G内存变为6G
- **升级记录**：仅记录不告警（如6G升8G）
- **驱动更新**：忽略不告警

## AI研判

支持对接OpenAI兼容API，对进程告警进行智能分析：
- 风险等级评估
- 原因分析
- 处理建议

## 安全特性

- 登录速率限制（每分钟5次/IP）
- Session认证 + 登出失效
- CORS白名单
- 安全响应头（X-Frame-Options等）
- 敏感配置掩码（API Key不返回明文）

## 技术栈

- **客户端**: Python + WMI + psutil + requests
- **服务端**: Python + Flask + MySQL + Redis + Celery
- **前端**: HTML/CSS/JavaScript（1Panel风格UI）
- **部署**: Docker + Gunicorn + Waitress
- **打包**: PyInstaller

## 许可证

MIT License
