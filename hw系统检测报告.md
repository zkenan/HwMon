# HwMon 硬件监控系统 v5.0 — 安全与功能检测报告

**报告编号**: HWMON-TEST-2026-0711  
**检测日期**: 2026-07-11  
**检测人员**: MiMoCode 自动化测试系统  
**系统地址**: http://192.168.20.27:5000  
**测试账号**: admin / admin123  
**系统版本**: v5.0.0-20260526  
**服务器**: Waitress (Python WSGI)

---

## 目录

1. [检测概述](#1-检测概述)
2. [系统概况](#2-系统概况)
3. [安全检测结果](#3-安全检测结果)
4. [功能检测结果](#4-功能检测结果)
5. [性能检测结果](#5-性能检测结果)
6. [前端/UI检测结果](#6-前端ui检测结果)
7. [问题汇总与修复建议](#7-问题汇总与修复建议)
8. [结论](#8-结论)

---

## 1. 检测概述

### 1.1 检测范围

本次检测针对 HwMon 硬件监控系统 v5.0 进行全面的安全与功能评估，涵盖以下维度：

- **安全测试**: 认证安全、授权控制、输入验证、会话管理、跨域安全、安全配置
- **功能测试**: 各业务模块的 CRUD 操作、数据流转、异常处理
- **性能测试**: API 响应时间、并发处理能力、大数据量场景
- **前端/UI测试**: 页面渲染、响应式设计、主题切换、无障碍访问

### 1.2 检测方法

| 测试类型 | 方法 |
|----------|------|
| 安全测试 | 黑盒渗透测试、API fuzzing、手动验证 |
| 功能测试 | 接口调用验证、数据完整性检查 |
| 性能测试 | 并发请求、响应时间测量 |
| 前端测试 | 源码分析、HTML/CSS 审查 |

### 1.3 检测结果概览

| 维度 | 发现数 | 严重程度分布 |
|------|--------|-------------|
| 安全测试 | 9 | 🔴 4 高危 / 🟡 5 中危 |
| 功能测试 | 4 | 🟡 4 中危 |
| 性能测试 | — | ✅ 优秀 |
| 前端/UI | 2 | 🟡 2 中危 |
| **合计** | **15** | **🔴 4 / 🟡 11** |

---

## 2. 系统概况

### 2.1 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (SPA)                           │
│  - 单页面应用，暗色/亮色双主题                           │
│  - 原生 JavaScript，无第三方框架                         │
│  - 响应式设计，支持移动端                                │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   API 服务层                             │
│  - RESTful JSON API                                     │
│  - JWT Session Cookie 认证                              │
│  - Waitress WSGI 服务器                                 │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   数据层                                 │
│  - 客户端硬件数据存储                                     │
│  - 告警记录                                             │
│  - 探针监控数据                                          │
└─────────────────────────────────────────────────────────┘
```

### 2.2 功能模块

| 模块 | 功能描述 |
|------|----------|
| 仪表盘 | 客户端/分组/告警概览统计 |
| 客户端管理 | 硬件监控 Agent 管理（列表、详情、采集） |
| 分组管理 | 客户端分组组织 |
| 告警中心 | 系统告警、探针告警、进程告警 |
| 探针监控 | HTTP 探针监控外部主机状态 |
| AI 研判 | GPT 集成分析（可选） |
| 系统配置 | 邮件通知、AI 配置 |

### 2.3 已发现 API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/login` | POST | 用户登录 |
| `/api/logout` | POST | 用户登出 |
| `/api/check-login` | GET | 检查登录状态 |
| `/api/dashboard` | GET | 获取仪表盘数据 |
| `/api/clients` | GET | 获取客户端列表 |
| `/api/client/{id}` | GET | 获取客户端详情 |
| `/api/groups` | GET/POST | 分组管理 |
| `/api/alerts` | GET | 告警列表 |
| `/api/probe/targets` | GET/POST/DELETE | 探针目标管理 |
| `/api/probe/alerts` | GET | 探针告警 |
| `/api/process-alerts` | GET | 进程告警 |
| `/api/collect/{client_id}` | POST | 单客户端采集 |
| `/api/collect/all` | POST | 全量采集 |
| `/api/email-config` | GET/PUT | 邮件配置 |
| `/api/ai/config` | GET/PUT | AI 配置 |

---

## 3. 安全检测结果

### 3.1 🔴 严重/高危问题

#### S1: 登出后会话未失效 [严重]

**风险等级**: 🔴 Critical (CVSS 3.1: 9.1)

**问题描述**:  
调用 `/api/logout` 接口后，服务器返回成功消息，但原有的 session cookie 并未被失效，仍可用于访问所有受保护的 API 端点。

**复现步骤**:
```bash
# 1. 登录获取 session
curl -c cookies.txt -X POST http://192.168.20.27:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 2. 使用 session 访问 dashboard（成功）
curl -b cookies.txt http://192.168.20.27:5000/api/dashboard
# 返回: {"status":"success",...}

# 3. 调用 logout
curl -b cookies.txt -X POST http://192.168.20.27:5000/api/logout
# 返回: {"message":"已登出","status":"success"}

# 4. 再次使用旧 session 访问 dashboard（仍然成功！）
curl -b cookies.txt http://192.168.20.27:5000/api/dashboard
# 返回: {"status":"success",...}  ← 问题所在
```

**影响分析**:
- 用户以为已安全登出，但会话仍有效
- 攻击者获取 cookie 后可长期使用
- 公共电脑使用场景风险极高

**修复建议**:
```python
# 方案1: 服务端维护 session 黑名单
logout_sessions = set()  # 存储已登出的 session ID

def check_session(session_id):
    if session_id in logout_sessions:
        return False
    return validate_jwt(session_id)

# 方案2: 使用短期 token + refresh token
# 登出时同时删除 refresh token

# 方案3: 将 session 存储在服务端（Redis/数据库）
# 登出时删除服务端 session
```

---

#### S2: CORS 配置允许任意来源 [高危]

**风险等级**: 🔴 High (CVSS 3.1: 8.1)

**问题描述**:  
服务器的 CORS 配置反射任意 Origin 头，允许任何网站跨域访问 API 数据。

**复现步骤**:
```bash
# 测试1: 恶意网站 Origin
curl -I -H "Origin: http://evil.com" http://192.168.20.27:5000/api/dashboard
# 返回: Access-Control-Allow-Origin: http://evil.com

# 测试2: null Origin
curl -I -H "Origin: null" http://192.168.20.27:5000/api/dashboard
# 返回: Access-Control-Allow-Origin: null

# 测试3: 子域名 Origin
curl -I -H "Origin: http://evil.192.168.20.27" http://192.168.20.27:5000/api/dashboard
# 返回: Access-Control-Allow-Origin: http://evil.192.168.20.27
```

**影响分析**:
- 恶意网站可读取用户的硬件监控数据
- 可发起 CSRF 攻击执行敏感操作
- 用户隐私数据泄露风险

**修复建议**:
```python
# 配置 CORS 白名单
ALLOWED_ORIGINS = [
    "http://192.168.20.27:5000",
    "https://your-domain.com",
]

@app.after_request
def add_cors_headers(request):
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response
```

---

#### S3: 无登录速率限制 [高危]

**风险等级**: 🔴 High (CVSS 3.1: 7.5)

**问题描述**:  
登录接口 `/api/login` 没有任何速率限制，攻击者可进行暴力破解攻击。

**复现步骤**:
```bash
# 连续发送 5 次错误密码请求
for i in {1..5}; do
  curl -s -X POST http://192.168.20.27:5000/api/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"wrongpassword"}'
done
# 所有请求均正常响应，无限制
```

**影响分析**:
- 攻击者可暴力破解用户密码
- 弱密码场景风险极高

**修复建议**:
```python
# 方案1: 基于 IP 的速率限制
from flask_limiter import Limiter

limiter = Limiter(app, key_func=get_remote_address)

@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")  # 每分钟最多 5 次
def login():
    # ...

# 方案2: 账户锁定机制
# 连续失败 5 次后锁定 15 分钟

# 方案3: 验证码
# 失败 3 次后要求输入验证码
```

---

#### S4: 无 CSRF 防护 [高危]

**风险等级**: 🔴 High (CVSS 3.1: 7.5)

**问题描述**:  
API 接口没有 CSRF token 验证，攻击者可构造恶意页面诱导用户执行操作。

**复现步骤**:
```bash
# 直接发送 POST 请求创建探针目标（无需 CSRF token）
curl -b cookies.txt -X POST http://192.168.20.27:5000/api/probe/targets \
  -H "Content-Type: application/json" \
  -d '{"name":"evil-target","host":"evil.com","port":80,"protocol":"http","path":"/","enabled":true}'
# 返回: {"status":"success","target_id":2}
```

**影响分析**:
- 攻击者可诱导用户删除数据、修改配置
- 结合 CORS 漏洞风险更高

**修复建议**:
```python
# 方案1: 验证 Origin/Header
@app.before_request
def csrf_protect():
    if request.method in ['POST', 'PUT', 'DELETE']:
        origin = request.headers.get('Origin')
        if origin and origin not in ALLOWED_ORIGINS:
            return jsonify({"error": "CSRF validation failed"}), 403

# 方案2: 双重提交 Cookie
# 方案3: 自定义 Header 验证（如 X-Requested-With）
```

---

### 3.2 🟡 中危问题

#### S5: 缺少安全响应头

**问题描述**:  
服务器响应缺少多个重要的安全头。

| 缺失头 | 风险 |
|--------|------|
| `X-Frame-Options` | 点击劫持攻击 |
| `Content-Security-Policy` | XSS 攻击 |
| `X-Content-Type-Options` | MIME 嗅探 |
| `Referrer-Policy` | 信息泄露 |
| `Permissions-Policy` | 功能滥用 |

**修复建议**:
```python
@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'"
    return response
```

---

#### S6: Session Cookie 缺少 Secure 标志

**问题描述**:  
Cookie 仅设置 `HttpOnly; SameSite=Lax`，缺少 `Secure` 标志。

**修复建议**:
- 启用 HTTPS 后添加 `Secure` 标志
- 考虑使用 `SameSite=Strict`

---

#### S7: SSRF 漏洞 (Probe Targets)

**问题描述**:  
探针目标功能允许创建指向任意主机的监控目标，包括云元数据端点。

**复现步骤**:
```bash
# 创建指向 AWS 元数据端点的探针
curl -b cookies.txt -X POST http://192.168.20.27:5000/api/probe/targets \
  -H "Content-Type: application/json" \
  -d '{"name":"ssrf-test","host":"169.254.169.254","port":80,"protocol":"http","path":"/latest/meta-data/","enabled":true}'
# 返回: {"status":"success","target_id":1}
```

**修复建议**:
```python
import ipaddress

BLOCKED_HOSTS = ['169.254.169.254', '127.0.0.1', '0.0.0.0']
BLOCKED_RANGES = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
]

def validate_probe_host(host):
    if host in BLOCKED_HOSTS:
        return False
    try:
        ip = ipaddress.ip_address(host)
        for range in BLOCKED_RANGES:
            if ip in range:
                return False
    except ValueError:
        pass  # hostname, validate DNS
    return True
```

---

#### S8: API 响应暴露敏感配置

**问题描述**:  
`/api/ai/config` 和 `/api/email-config` 返回完整的配置信息，包括 API Key 和密码字段。

**修复建议**:
```python
def sanitize_config(config):
    """掩码敏感字段"""
    if config.get('api_key'):
        config['api_key'] = config['api_key'][:8] + '****'
    if config.get('smtp_password'):
        config['smtp_password'] = '****'
    return config
```

---

#### S9: JWT 签名较短

**问题描述**:  
JWT 签名仅 27 字符，理论上可被暴力破解。

**修复建议**:
- 使用 RS256（非对称加密）替代 HS256
- 确保签名密钥足够长（至少 256 位）

---

### 3.3 ✅ 安全测试通过项

| 测试项 | 结果 | 说明 |
|--------|------|------|
| SQL 注入 | ✅ 通过 | 返回标准错误，无数据泄露 |
| XSS 注入 | ✅ 通过 | 输入被正确处理 |
| 路径遍历 | ✅ 通过 | 返回 404，无法访问系统文件 |
| 目录列表 | ✅ 通过 | 已禁用 |
| 调试模式 | ✅ 通过 | 未暴露堆栈信息 |
| 未认证访问 | ✅ 通过 | 返回 401 |
| 无效 Session | ✅ 通过 | 返回 401 |
| XXE 攻击 | ✅ 通过 | 仅接受 JSON，拒绝 XML |
| HTTP 方法限制 | ✅ 通过 | 不支持的方法返回 405 |
| 密码 URL 传输 | ✅ 通过 | GET 方法被拒绝 |

---

## 4. 功能检测结果

### 4.1 ✅ 功能正常

| 功能模块 | 测试内容 | 结果 |
|----------|----------|------|
| 登录认证 | 用户名密码登录 | ✅ 正常 |
| 仪表盘 | 数据统计展示 | ✅ 正确 |
| 客户端列表 | 获取所有客户端 | ✅ 正常 |
| 客户端详情 | 获取硬件信息 | ✅ 包含完整信息 |
| 分组管理 | 创建/列表分组 | ✅ 正常 |
| 探针目标 | CRUD 操作 | ✅ 正常 |
| 数据采集 | 单客户端/全量 | ✅ 正常触发 |
| 告警列表 | 分页查询 | ✅ 正常 |
| 邮件配置 | 读取/更新 | ✅ 正常 (PUT) |
| AI 配置 | 读取/更新 | ✅ 正常 (PUT) |

### 4.2 🟡 功能异常

#### F1: 数据导出返回 404

**问题描述**:  
`/api/export/{client_id}` 返回 404 Not Found。

**影响**: 用户无法导出客户端数据。

**建议**: 检查路由配置或实现导出功能。

---

#### F2: 探针手动检查返回 404

**问题描述**:  
`/api/probe/targets/{id}/check` 返回 404 Not Found。

**影响**: 用户无法手动触发探针检查。

**建议**: 实现或修复该端点。

---

#### F3: AI 模型列表返回空

**问题描述**:  
`/api/ai/config/models` 返回空响应。

**影响**: 无法获取可用的 AI 模型列表。

**建议**: 检查 API Key 配置后是否能正常获取。

---

#### F4: 全量采集需强制 Content-Type

**问题描述**:  
`/api/collect/all` 即使无请求体，也必须发送 `Content-Type: application/json`，否则返回 415。

**影响**: 客户端集成时需注意。

**建议**: 该端点应允许无 Content-Type 的 POST 请求。

---

## 5. 性能检测结果

### 5.1 响应时间测试

| 测试场景 | 响应时间 | 评价 |
|----------|----------|------|
| Dashboard API | 平均 2.5ms | ✅ 优秀 |
| 顺序请求 (20次) | 平均 19ms/次 | ✅ 优秀 |
| 全量采集 (1客户端) | 1.8s | ✅ 正常 |

### 5.2 并发测试

| 并发数 | 完成时间 | 评价 |
|--------|----------|------|
| 10 并发 | 10ms | ✅ 优秀 |
| 50 并发 | 57ms | ✅ 优秀 |
| 100 并发 | 220ms | ✅ 优秀 |

### 5.3 性能评价

系统性能表现优秀：
- API 响应时间极快（< 20ms）
- 并发处理能力强（100 并发 < 250ms）
- 服务器资源利用高效

---

## 6. 前端/UI检测结果

### 6.1 ✅ 通过项

| 测试项 | 结果 | 说明 |
|--------|------|------|
| 响应式设计 | ✅ 通过 | 有 viewport meta，768px 以下隐藏侧边栏 |
| 主题切换 | ✅ 通过 | 支持 Dark/Light 双主题 |
| Toast 通知 | ✅ 通过 | 有 toast 提示系统 |
| 告警分级 | ✅ 通过 | critical/warning/info 样式区分 |
| 表单验证 | ✅ 通过 | 必填字段有 required 属性 |
| 登录错误提示 | ✅ 通过 | 3 秒自动隐藏 |

### 6.2 🟡 待改进项

#### U1: 缺少无障碍支持

**问题描述**:  
- 无 ARIA 属性（aria-label, role 等）
- 无 skip navigation 链接

**影响**: 屏幕阅读器用户无法正常使用。

**建议**:
```html
<!-- 添加 ARIA 属性 -->
<nav aria-label="主导航">
  <button aria-label="仪表盘">仪表盘</button>
</nav>

<!-- 添加 skip navigation -->
<a href="#main-content" class="sr-only">跳转到主内容</a>
```

---

#### U2: 键盘导航不完整

**问题描述**:  
- 仅有 focus 样式，无自定义键盘事件处理
- 侧边栏导航依赖 onclick，无 tabindex

**建议**: 添加 tabindex 和键盘事件处理。

---

## 7. 问题汇总与修复建议

### 7.1 优先级排序

| 优先级 | 问题ID | 问题描述 | 严重程度 |
|--------|--------|----------|----------|
| P0 | S1 | 登出会话未失效 | 🔴 Critical |
| P0 | S2 | CORS 任意来源 | 🔴 High |
| P1 | S3 | 无登录速率限制 | 🔴 High |
| P1 | S4 | 无 CSRF 防护 | 🔴 High |
| P1 | S5 | 缺少安全响应头 | 🟡 Medium |
| P2 | S6 | Cookie 无 Secure | 🟡 Medium |
| P2 | S7 | SSRF 漏洞 | 🟡 Medium |
| P2 | S8 | 敏感配置暴露 | 🟡 Medium |
| P2 | F1-F4 | 功能异常 | 🟡 Medium |
| P3 | S9 | JWT 签名较短 | 🟡 Medium |
| P3 | U1-U2 | 前端无障碍 | 🟡 Medium |

### 7.2 修复建议汇总

#### 立即修复 (P0)

1. **修复会话管理**
   - 实现服务端 session 存储
   - 登出时删除 session
   - 或使用短期 JWT + refresh token

2. **修复 CORS 配置**
   - 配置 Origin 白名单
   - 仅允许可信域名

#### 尽快修复 (P1)

3. **添加登录速率限制**
   - IP 级别限流（5次/分钟）
   - 账户锁定机制

4. **添加 CSRF 防护**
   - 验证 Origin header
   - 或使用 CSRF token

5. **添加安全响应头**
   - X-Frame-Options
   - Content-Security-Policy
   - X-Content-Type-Options

#### 计划修复 (P2)

6. **修复 SSRF 漏洞** - 限制探针目标范围
7. **掩码敏感配置** - API 响应中隐藏密钥
8. **修复功能异常** - 导出、探针检查等
9. **添加 Secure 标志** - 启用 HTTPS

#### 持续改进 (P3)

10. **增强 JWT 安全** - 使用 RS256
11. **添加无障碍支持** - ARIA 属性
12. **完善键盘导航** - tabindex 事件

---

## 8. 结论

### 8.1 总体评价

HwMon 硬件监控系统 v5.0 在**功能完整性**和**性能表现**方面表现良好，但在**安全防护**方面存在多个高危漏洞需要立即修复。

### 8.2 风险等级

| 风险等级 | 说明 |
|----------|------|
| 🔴 高风险 | 存在 4 个高危安全漏洞，可能导致用户数据泄露、账户被攻破 |
| 🟡 中风险 | 存在 11 个中危问题，影响系统安全性和用户体验 |
| ✅ 低风险 | 功能正常，性能优秀，前端设计合理 |

### 8.3 建议

1. **立即修复** P0 级别问题（会话管理、CORS）
2. **尽快修复** P1 级别问题（速率限制、CSRF、安全头）
3. **计划修复** P2 级别问题（SSRF、敏感数据、功能异常）
4. **持续改进** P3 级别问题（JWT、无障碍）

### 8.4 后续测试

建议在修复后进行以下验证测试：
- 会话管理回归测试
- 安全头验证
- CORS 配置验证
- 功能回归测试

---

**报告完成时间**: 2026-07-11 17:50:00 CST  
**检测工具**: MiMoCode 自动化测试系统  
**报告版本**: v1.0

---

*本报告仅供内部使用，未经授权不得对外传播。*
