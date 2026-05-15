# 硬件监控系统 - 更新说明

## ✅ 已完成的改进

### 1. 数据库迁移到MySQL ✓
- **原因**: SQLite在高并发下性能较差，导致系统卡顿
- **改进**: 
  - 迁移到MySQL数据库 (192.168.20.17:3306)
  - 使用连接池管理数据库连接（最大50个连接）
  - 所有SQL查询已从SQLite语法改为MySQL语法
  - 数据库用户名: HwMon, 密码: kk7cy7SDWDMXC5XQ

### 2. 客户端列表排序功能 ✓
- **功能**: 点击表头可进行正序/倒序排序
- **支持排序的字段**:
  - 主机名
  - IP地址
  - 分组
  - 最后上报时间
- **使用方式**: 
  - 点击表头一次：降序排列（↓）
  - 再点击一次：升序排列（↑）
  - 表头会显示排序方向指示器

### 3. 未分组列表功能 ✓
- **功能**: 新增"未分组"筛选选项
- **位置**: 分组下拉框中的第一项
- **显示**: 实时显示未分组的客户端数量
- **使用**: 选择"未分组"后，只显示没有分配到任何分组的客户端

### 4. 高并发优化 ✓
- **并发采集**: 使用ThreadPoolExecutor实现50并发
- **预计性能**: 1000台客户端约30秒完成采集
- **超时控制**: 单个客户端请求超时15秒
- **数据库连接池**: 最大50个连接，最小10个空闲连接

### 5. 前端界面改进 ✓
- **主机名显示**: 客户端列表第一列现在显示主机名（如果没有则显示client_id）
- **排序指示器**: 表头显示当前排序方向和字段
- **未分组计数**: 实时更新未分组客户端数量

## 📋 使用说明

### 初始化数据库
```bash
cd server
python init_mysql.py
```

### 启动服务器
```bash
cd server
python app.py
```

访问 http://localhost:5000

### 登录信息
- 用户名: xapi
- 密码: Ai78965

## 🔧 技术细节

### 数据库表结构
1. `groups` - 分组表
2. `clients` - 客户端表
3. `hardware_reports` - 硬件报告历史表
4. `hardware_history` - 硬件采集历史表
5. `client_baselines` - 客户端硬件基准表
6. `alert_records` - 告警记录表
7. `email_config` - 邮件配置表
8. `alert_settings` - 告警设置表

### API改进
- `/api/clients` - 支持排序参数
  - `sort_by`: 排序字段 (hostname, local_ip, group_name, last_report, created_at)
  - `order`: 排序方向 (asc, desc)
  - `group_id`: 分组ID (支持 "ungrouped" 表示未分组)

## ⚠️ 注意事项

1. **Waitress安装**: 为了支持高并发，建议安装waitress WSGI服务器
   ```bash
   pip install waitress
   ```
   如果无法安装，系统会使用Flask内置服务器（开发模式）

2. **数据库备份**: 从SQLite迁移到MySQL后，原有数据需要重新采集

3. **防火墙**: 确保MySQL服务器(192.168.20.17)允许来自本机的连接

## 📦 打包成EXE

要打包成exe文件，请使用现有的打包脚本：
```bash
cd server
python build_exe.py
```

或者使用快速打包：
```bash
cd server
快速打包.bat
```

## 🎯 下一步建议

1. 安装waitress以启用生产模式高并发支持
2. 配置邮件告警功能
3. 测试大规模客户端采集性能
4. 根据需要调整并发参数（在app.py中的COLLECT_CONFIG）
