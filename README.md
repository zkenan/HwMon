# 硬件监控系统

一个用于自动采集Windows客户端硬件信息并上报到服务端的系统,支持分组管理和数据导出。

## 功能特性

### 客户端
- ✅ 自动采集硬件信息(CPU、内存、硬盘、显卡、网卡等)
- ✅ 采集MAC地址和IP地址
- ✅ 获取主机名和系统信息
- ✅ 开机自启动(静默运行)
- ✅ 定时上报(可配置间隔)
- ✅ 本地日志记录
- ✅ JSON配置文件管理
- ✅ 支持打包为独立exe程序
- ✅ 可选择性采集硬件组件

### 服务端
- ✅ Web管理界面(美观的UI)
- ✅ 实时查看所有客户端信息
- ✅ 自定义分组管理
- ✅ 查看硬件详细信息
- ✅ 数据导出(CSV/JSON格式)
- ✅ 客户端在线状态检测
- ✅ 自动刷新(30秒)

## 项目结构

```
hardware-monitor/
├── client/                     # 客户端目录
│   ├── client.py              # 主程序
│   ├── hardware_collector.py  # 硬件采集模块
│   ├── config.py              # 配置管理模块
│   ├── config.example.json    # 配置示例文件
│   ├── build_exe.py           # exe打包脚本
│   ├── install.bat            # 一键安装脚本
│   └── requirements.txt       # Python依赖
└── server/                    # 服务端目录
    ├── app.py                 # Flask应用
    ├── templates/             # HTML模板
    │   └── index.html         # Web管理界面
    └── requirements.txt       # Python依赖
```

## 快速开始

### 方式一: 使用Python脚本(开发/测试)

#### 服务端部署

1. 安装Python依赖:
```bash
cd server
pip install -r requirements.txt
```

2. 启动服务端:
```bash
python app.py
```

3. 访问Web界面: `http://localhost:5000`

#### 客户端部署

1. 安装Python依赖:
```bash
cd client
pip install -r requirements.txt
```

2. 配置服务器地址:

复制 `config.example.json` 为 `config.json`,然后编辑:
```json
{
    "server": {
        "url": "http://你的服务器IP:5000"
    }
}
```

3. 运行客户端:

**交互模式**(测试用):
```bash
python client.py
```

**安装为开机自启**:
```bash
python client.py --install
```

或使用一键安装脚本:
```bash
install.bat
```

### 方式二: 使用exe程序(生产环境推荐)

#### 1. 打包exe

在客户端电脑上执行:
```bash
cd client
python build_exe.py
```

打包完成后会在 `dist` 目录生成:
- `HardwareMonitor.exe` - 主程序
- `HardwareMonitor_Package/` - 便携版安装包

#### 2. 部署exe

**方法A: 使用便携版安装包**

1. 将 `HardwareMonitor_Package` 文件夹复制到目标电脑
2. 编辑 `config.json`,修改服务器地址
3. 双击 `HardwareMonitor.exe` 运行
4. 或运行 `HardwareMonitor.exe --install` 安装为开机自启

**方法B: 直接分发exe**

1. 将 `HardwareMonitor.exe` 复制到目标电脑
2. 首次运行会自动生成 `config.json`
3. 编辑 `config.json` 修改配置
4. 再次运行程序

#### 3. 配置exe程序

**命令行配置**:
```bash
HardwareMonitor.exe --config
```

进入交互式配置界面,可以修改:
- 服务器URL
- 上报间隔
- 开机自启设置
- 客户端ID
- 分组名称
- 日志功能

**直接编辑配置文件**:

用记事本打开 `config.json`:
```json
{
    "server": {
        "url": "http://192.168.1.100:5000",
        "timeout": 10
    },
    "client": {
        "report_interval": 300,
        "auto_start": true,
        "group_name": "办公室电脑"
    }
}
```

## 配置说明

### 完整配置项

```json
{
    "server": {
        "url": "http://localhost:5000",     // 服务器地址
        "timeout": 10,                       // 请求超时时间(秒)
        "retry_times": 3,                    // 重试次数
        "retry_interval": 60                 // 重试间隔(秒)
    },
    "client": {
        "report_interval": 300,              // 上报间隔(秒)
        "auto_start": true,                  // 是否开机自启
        "client_id": "",                     // 客户端ID(留空自动生成)
        "group_name": ""                     // 分组名称
    },
    "logging": {
        "enabled": true,                     // 是否启用日志
        "log_file": "client.log",            // 日志文件路径
        "max_size_mb": 10,                   // 日志文件最大大小(MB)
        "backup_count": 5                    // 日志备份数量
    },
    "advanced": {
        "collect_cpu": true,                 // 采集CPU信息
        "collect_memory": true,              // 采集内存信息
        "collect_disk": true,                // 采集硬盘信息
        "collect_gpu": true,                 // 采集显卡信息
        "collect_network": true,             // 采集网络信息
        "collect_motherboard": true,         // 采集主板信息
        "collect_bios": true,                // 采集BIOS信息
        "compress_data": false               // 压缩数据(暂未实现)
    }
}
```

### 常用配置场景

**场景1: 修改服务器地址**
```json
{
    "server": {
        "url": "http://192.168.1.100:5000"
    }
}
```

**场景2: 修改上报频率为10分钟**
```json
{
    "client": {
        "report_interval": 600
    }
}
```

**场景3: 设置分组名称**
```json
{
    "client": {
        "group_name": "财务部"
    }
}
```

**场景4: 只采集网络和系统信息(快速模式)**
```json
{
    "advanced": {
        "collect_cpu": false,
        "collect_memory": false,
        "collect_disk": false,
        "collect_gpu": false,
        "collect_network": true,
        "collect_motherboard": false,
        "collect_bios": false
    }
}
```

## 使用说明

### 客户端操作

**交互菜单选项**:
1. **立即测试采集** - 查看采集到的硬件信息
2. **安装并启动** - 设置开机自启并后台运行
3. **停止并卸载** - 取消开机自启
4. **编辑配置** - 进入配置编辑器
5. **查看当前配置** - 显示完整配置
6. **退出**

**命令行参数**:
- `--silent` - 静默运行模式
- `--install` - 安装为开机自启
- `--config` - 进入配置编辑器

### 服务端操作

1. **查看客户端** - 主页显示所有已上报的客户端列表
2. **查看详情** - 点击"详情"按钮查看完整硬件信息
3. **创建分组** - 点击"新建分组"创建自定义分组
4. **分配分组** - 点击客户端的"分组"按钮
5. **筛选查看** - 使用顶部分组下拉框筛选
6. **导出数据** - 点击"导出CSV"或"导出JSON"

### 数据说明

采集的硬件信息包括:
- **系统信息**: 主机名、操作系统、版本、架构
- **CPU**: 型号、核心数、线程数、主频
- **内存**: 容量、频率、制造商、序列号
- **硬盘**: 型号、容量、序列号、接口类型
- **显卡**: 型号、显存、驱动版本
- **网络**: MAC地址、IP地址、网卡描述
- **主板**: 制造商、型号、序列号
- **BIOS**: 制造商、版本、发布日期

## 批量部署方案

### 方案一: 使用批处理脚本

创建 `deploy.bat`:
```batch
@echo off
REM 批量部署脚本

REM 1. 复制程序到目标电脑
xcopy /Y HardwareMonitor.exe \\目标IP\C$\Programs\

REM 2. 复制配置文件
xcopy /Y config.json \\目标IP\C$\Programs\

REM 3. 远程执行安装(需要PSEXEC工具)
psexec \\目标IP -s C:\Programs\HardwareMonitor.exe --install
```

### 方案二: 使用组策略(GPO)

1. 将exe和config.json放到共享文件夹
2. 在组策略中配置开机脚本
3. 指向共享文件夹中的exe

### 方案三: 使用SCCM/PDQ Deploy

企业环境中可以使用专业的软件分发工具。

## 注意事项

1. **防火墙**: 确保服务器端口(默认5000)已开放
2. **网络**: 客户端必须能访问服务器地址
3. **权限**: 设置开机自启需要管理员权限
4. **杀毒软件**: 某些杀毒软件可能误报exe,需要添加白名单
5. **数据库**: 服务端使用SQLite,数据保存在 `hardware_monitor.db`
6. **Python版本**: 建议使用Python 3.7+
7. **WMI服务**: 确保Windows WMI服务正常运行

## 故障排查

### 客户端无法上报

1. 检查服务器是否正常运行
2. 检查 `config.json` 中的服务器地址是否正确
3. 查看 `client.log` 日志文件
4. 检查网络连接: `ping 服务器IP`
5. 检查防火墙设置

### 服务端无法启动

1. 确认Python版本 >= 3.7: `python --version`
2. 确认已安装所有依赖: `pip install -r requirements.txt`
3. 检查5000端口是否被占用: `netstat -ano | findstr :5000`

### Web界面无法访问

1. 确认服务端正在运行
2. 检查浏览器地址是否正确
3. 如从其他机器访问,确认使用正确的IP地址
4. 检查防火墙是否允许5000端口

### exe程序问题

**Q: 打包后的exe体积很大?**
A: 这是正常的,因为包含了Python运行时和所有依赖库

**Q: exe运行时报错找不到模块?**
A: 确保使用 `build_exe.py` 脚本打包,它会自动包含所有依赖

**Q: 如何更新配置?**
A: 直接编辑 `config.json` 文件,重启程序即可生效

## 技术栈

- **客户端**: Python + WMI + psutil + requests
- **服务端**: Python + Flask + SQLite
- **前端**: 原生HTML/CSS/JavaScript
- **打包**: PyInstaller

## 许可证

MIT License
