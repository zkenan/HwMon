# 硬件监控系统 - 客户端部署步骤

## 当前状态
- win-DL (192.168.20.18): 旧版客户端 ❌
- longxia (192.168.20.25): 旧版客户端 ❌

## 问题症状
1. 服务端点击"一键采集" → 全部失败
2. 服务端重启后客户端不自动重连

## 修复方案

### 步骤1: 复制新版exe到客户端
新版文件位置: `f:/1zkenan/1xiangmu/hardware-monitor/client/dist/HardwareMonitor.exe`

**方法A: 共享文件夹**
1. 在服务端共享 `f:/1zkenan/1xiangmu/hardware-monitor/client/dist` 目录
2. 在客户端访问 `\\服务端IP\共享名`
3. 复制 HardwareMonitor.exe 到客户端原目录

**方法B: USB传输**
1. 用U盘拷贝 HardwareMonitor.exe
2. 在每台客户端上覆盖旧文件

### 步骤2: 在每台客户端执行
1. 打开任务管理器，结束 `HardwareMonitor.exe` 进程
2. 将新版 exe 复制到原位置（覆盖旧文件）
3. 双击运行新 exe
4. 选择 `2. 安装并启动`
5. 可以关闭命令行窗口

### 步骤3: 验证
- 等待1-2分钟
- 刷新服务端页面 http://[服务端IP]:5000
- 点击"一键采集"，应显示成功

## 新版功能
- 每120秒自动上报（原300秒）
- 服务端重启后自动重连
- 修复HTTP 500错误
