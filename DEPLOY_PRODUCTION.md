# HwMon Server v5.0.1 生产部署方案（Docker Compose）

> 版本：v5.0.1 ｜ 日期：2026-09-03
> 部署方式：Docker Compose 单容器运行 Flask 服务端，**数据库与 Redis 使用外部专用实例**（手动指定）。

---

## 一、架构说明

```
┌─────────────────────────────────────────────┐
│  生产服务器 (Docker)                          │
│  ┌───────────────────────────────────────┐  │
│  │  hwmon-server 容器 (Flask + Waitress)  │  │
│  │  端口 5000 → 宿主机 5000               │  │
│  └──────────────┬──────────────┬─────────┘  │
│                 │              │            │
└─────────────────┼──────────────┼────────────┘
                  │              │
        ┌─────────▼───┐    ┌─────▼───────┐
        │ 专用 MySQL   │    │  专用 Redis  │
        │ (外部实例)   │    │  (外部实例)  │
        └─────────────┘    └─────────────┘
```

- **应用容器**：只跑 HwMon 服务端，无状态，可水平扩展。
- **数据库 / Redis**：独立部署（可自建、云数据库或已有实例），由 `docker-compose.yml` 通过环境变量注入连接信息。

---

## 二、前置条件

| 项 | 要求 |
|---|---|
| 操作系统 | Linux（推荐 Ubuntu 20.04+ / CentOS 7.9+） |
| Docker | 20.10+ |
| Docker Compose | v2.x（`docker compose` 子命令） |
| MySQL | 5.7+ / 8.0（需提前建库 `hwmon`，字符集 `utf8mb4`） |
| Redis | 5.0+（可选设置密码） |
| 网络 | 应用容器需能访问 MySQL 与 Redis 所在主机/端口 |

---

## 三、数据库初始化

在专用 MySQL 上创建数据库与账号（示例，请按实际安全策略调整）：

```sql
CREATE DATABASE IF NOT EXISTS hwmon
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'hwmon'@'%'
  IDENTIFIED BY '你的强密码';

GRANT ALL PRIVILEGES ON hwmon.* TO 'hwmon'@'%';
FLUSH PRIVILEGES;
```

> 表结构由服务端启动时**自动创建**（`init_tables`），无需手动建表。
> 若 MySQL 在独立主机，注意防火墙放行 3306 端口，并确保 `bind-address` 允许容器网段访问。

---

## 四、部署步骤

### 1. 获取代码

```bash
git clone https://github.com/zkenan/HwMon.git
cd HwMon
```

### 2. 配置环境变量

```bash
cp .env.example .env
vim .env
```

重点填写（**数据库与 Redis 手动指定专用实例**）：

| 变量 | 说明 | 示例 |
|---|---|---|
| `DB_HOST` | 专用 MySQL 地址 | `10.0.0.20` |
| `DB_PORT` | MySQL 端口 | `3306` |
| `DB_USER` / `DB_PASSWORD` | 数据库账号/密码 | `hwmon` / `强密码` |
| `DB_NAME` | 数据库名 | `hwmon` |
| `REDIS_HOST` / `REDIS_PORT` | 专用 Redis 地址/端口 | `10.0.0.21` / `6379` |
| `REDIS_PASSWORD` | Redis 密码（无则留空） | `redis密码` |
| `LOGIN_USERNAME` / `LOGIN_PASSWORD` | 登录账号/密码 | `admin` / `强密码` |
| `SECRET_KEY` | 会话密钥（随机串） | `openssl rand -hex 32` 生成 |
| `SERVER_PORT` | 对外端口 | `5000` |
| `HW_IMAGE_TAG` | 镜像版本标签 | `v5.0.1` |

### 3. 构建镜像并启动

```bash
docker compose build hwmon
docker compose up -d
```

### 4. 验证

```bash
# 查看容器状态（应为 Up）
docker compose ps

# 查看启动日志（应无报错，打印 DB_HOST / DB_NAME 等）
docker compose logs -f hwmon

# 健康检查
curl -s http://127.0.0.1:5000/api/login -X POST \
  -H 'Content-Type: application/json' \
  -d '{"username":"你的账号","password":"你的密码"}'
```

浏览器访问：`http://<服务器IP>:5000`

---

## 五、镜像版本管理

镜像标签由 `.env` 中的 `HW_IMAGE_TAG` 控制（默认 `v5.0.1`）。

```bash
# 打版本标签
docker tag hwmon-server:v5.0.1 hwmon-server:latest

# 查看本地镜像
docker images | grep hwmon-server
```

升级到新版本时，只需更新代码、修改 `HW_IMAGE_TAG`，重新 `docker compose build hwmon && docker compose up -d`。

---

## 六、常用运维命令

```bash
# 查看日志
docker compose logs -f hwmon

# 重启
docker compose restart hwmon

# 停止
docker compose down

# 停止并删除容器（保留数据，因为数据在外部 MySQL/Redis）
docker compose down --rmi local
```

---

## 七、安全注意事项

1. **`.env` 文件切勿提交到 git**（已加入 `.gitignore`），含数据库/Redis/登录密码。
2. `SECRET_KEY` 必须使用强随机串（`openssl rand -hex 32`），不要用默认值。
3. 生产环境务必修改 `LOGIN_PASSWORD` 默认值。
4. 若 MySQL/Redis 跨主机，建议在专用网络/VPC 内通信，避免公网暴露端口。
5. 客户端采集程序通过 5000 端口上报，请为终端机器放行该端口。

---

## 八、客户端（采集 Agent）说明

- 客户端为装在被管理终端上的 Python 采集程序（`client/`），非浏览器前端。
- 配置服务端地址后，按配置的上报间隔（默认 120s）向服务端 `/api/report` 上报硬件信息。
- 客户端安装与打包详见 `client/` 目录下的 `install.sh` / `install.bat` 与打包脚本。
