"""
PyInstaller打包脚本 - 完整版
将Python环境和所有依赖打包为独立的exe文件
目标电脑无需安装Python即可运行
"""

import os
import sys
import subprocess
import shutil
import json
from pathlib import Path

# 设置UTF-8编码输出,避免Windows GBK编码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class BuildTool:
    """打包工具类"""

    def __init__(self):
        self.current_dir = Path(__file__).parent.absolute()
        self.dist_dir = self.current_dir / "dist"
        self.build_dir = self.current_dir / "build"
        self.spec_file = self.current_dir / "HardwareMonitor.spec"

    def check_prerequisites(self):
        """检查打包前置条件"""
        print("=" * 70)
        print("  硬件监控客户端 - 打包工具")
        print("=" * 70)
        print()

        # 检查Python版本
        python_version = sys.version_info
        print(f"Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
        if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 7):
            print("✗ Python版本过低,需要3.7或更高版本")
            return False
        print("✓ Python版本符合要求")
        print()

        # 检查必要文件
        required_files = [
            "client.py",
            "hardware_collector.py",
            "config.py",
            "requirements.txt"
        ]

        print("检查必要文件:")
        for file in required_files:
            if (self.current_dir / file).exists():
                print(f"  ✓ {file}")
            else:
                print(f"  ✗ {file} 不存在")
                return False
        print()

        return True

    def install_dependencies(self):
        """安装Python依赖"""
        print("=" * 70)
        print("  步骤 1: 安装Python依赖")
        print("=" * 70)
        print()

        # 检查并安装PyInstaller
        try:
            import PyInstaller
            print("✓ PyInstaller 已安装")
        except ImportError:
            print("正在安装 PyInstaller...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "pyinstaller"
            ])
            print("✓ PyInstaller 安装完成")
            print()

        # 安装其他依赖
        print("检查并安装项目依赖...")
        requirements_file = self.current_dir / "requirements.txt"

        if requirements_file.exists():
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
            ])
            print("✓ 所有依赖安装完成")
        else:
            print("✗ requirements.txt 不存在")
            return False

        print()
        return True

    def create_spec_file(self):
        """创建PyInstaller spec文件"""
        print("=" * 70)
        print("  步骤 2: 创建打包配置")
        print("=" * 70)
        print()

        spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['client.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('hardware_collector.py', '.'),
        ('config.py', '.'),
    ],
    hiddenimports=[
        'wmi',
        'psutil',
        'requests',
        'winreg',
        'json',
        'threading',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HardwareMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # True=显示控制台窗口(支持交互菜单和卸载), False=无窗口(会崩溃)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标文件,如: icon='icon.ico'
)
'''

        with open(self.spec_file, 'w', encoding='utf-8') as f:
            f.write(spec_content)

        print("✓ 打包配置文件已创建: HardwareMonitor.spec")
        print()

    def build_exe(self):
        """执行打包"""
        print("=" * 70)
        print("  步骤 3: 开始打包")
        print("=" * 70)
        print()
        print("这可能需要几分钟时间,请耐心等待...")
        print("打包过程中会:")
        print("  - 分析依赖关系")
        print("  - 收集Python运行时库")
        print("  - 收集所有第三方库")
        print("  - 编译为单个exe文件")
        print()

        # 清理旧的构建文件
        if self.build_dir.exists():
            print("清理旧的构建文件...")
            shutil.rmtree(self.build_dir)

        if self.dist_dir.exists():
            shutil.rmtree(self.dist_dir)

        # 执行PyInstaller
        try:
            cmd = [
                sys.executable, "-m", "PyInstaller",
                "--clean",
                str(self.spec_file)
            ]

            result = subprocess.run(
                cmd,
                cwd=str(self.current_dir),
                check=True,
                capture_output=True,
                text=True
            )

            # 检查是否成功
            exe_path = self.dist_dir / "HardwareMonitor.exe"
            if exe_path.exists():
                file_size = exe_path.stat().st_size
                size_mb = file_size / (1024 * 1024)

                print()
                print("=" * 70)
                print("  ✓ 打包成功!")
                print("=" * 70)
                print()
                print(f"EXE文件位置: {exe_path}")
                print(f"文件大小: {size_mb:.2f} MB")
                print()
                print("说明:")
                print("  - 此exe已包含完整的Python环境")
                print("  - 目标电脑无需安装Python")
                print("  - 首次运行会自动生成config.json配置文件")
                print()
                return True
            else:
                print("\n✗ 打包失败: 找不到生成的exe文件")
                return False

        except subprocess.CalledProcessError as e:
            print(f"\n✗ 打包失败:")
            print(f"错误信息: {e.stderr}")
            return False
        except Exception as e:
            print(f"\n✗ 发生错误: {str(e)}")
            return False

    def create_deployment_package(self):
        """创建部署包"""
        print()
        print("=" * 70)
        print("  步骤 4: 创建部署包")
        print("=" * 70)
        print()

        package_dir = self.dist_dir / "HardwareMonitor_部署包"

        # 创建目录结构
        if package_dir.exists():
            shutil.rmtree(package_dir)

        package_dir.mkdir(parents=True)
        (package_dir / "config").mkdir()

        # 复制exe
        exe_path = self.dist_dir / "HardwareMonitor.exe"
        if exe_path.exists():
            shutil.copy2(exe_path, package_dir)
            print(f"✓ 已复制: HardwareMonitor.exe")

        # 创建默认配置文件
        default_config = {
            "server": {
                "url": "http://localhost:5000",
                "timeout": 10,
                "retry_times": 3,
                "retry_interval": 60
            },
            "client": {
                "report_interval": 300,
                "auto_start": True,
                "client_id": "",
                "group_name": ""
            },
            "logging": {
                "enabled": True,
                "log_file": "client.log",
                "max_size_mb": 10,
                "backup_count": 5
            },
            "advanced": {
                "collect_cpu": True,
                "collect_memory": True,
                "collect_disk": True,
                "collect_gpu": True,
                "collect_network": True,
                "collect_motherboard": True,
                "collect_bios": True,
                "compress_data": False
            }
        }

        config_path = package_dir / "config" / "config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"✓ 已创建: config/config.json (配置文件)")

        # 创建配置示例
        config_example = default_config.copy()
        config_example["server"]["url"] = "http://你的服务器IP:5000"
        example_path = package_dir / "config" / "config.example.json"
        with open(example_path, 'w', encoding='utf-8') as f:
            json.dump(config_example, f, indent=4, ensure_ascii=False)
        print(f"✓ 已创建: config/config.example.json (配置示例)")

        # 创建批处理启动脚本
        startup_batch = package_dir / "启动配置工具.bat"
        with open(startup_batch, 'w', encoding='gbk') as f:
            f.write('@echo off\n')
            f.write('chcp 65001 >nul\n')
            f.write('echo 启动配置工具...\n')
            f.write('HardwareMonitor.exe --config\n')
            f.write('pause\n')
        print(f"✓ 已创建: 启动配置工具.bat")

        # 创建安装脚本
        install_batch = package_dir / "安装为开机自启.bat"
        with open(install_batch, 'w', encoding='gbk') as f:
            f.write('@echo off\n')
            f.write('chcp 65001 >nul\n')
            f.write('echo 正在安装为开机自启...\n')
            f.write('echo.\n')
            f.write('HardwareMonitor.exe --install\n')
            f.write('echo.\n')
            f.write('echo 安装完成!程序将在后台运行\n')
            f.write('pause\n')
        print(f"✓ 已创建: 安装为开机自启.bat")

        # 创建卸载脚本
        uninstall_batch = package_dir / "卸载程序.bat"
        with open(uninstall_batch, 'w', encoding='gbk') as f:
            f.write('@echo off\n')
            f.write('chcp 65001 >nul\n')
            f.write('echo ============================================\n')
            f.write('echo   硬件监控客户端 - 卸载工具\n')
            f.write('echo ============================================\n')
            f.write('echo.\n')
            f.write('echo 警告: 此操作将:\n')
            f.write('echo   1. 取消开机自启动\n')
            f.write('echo   2. 停止后台运行\n')
            f.write('echo   3. 删除配置文件和日志\n')
            f.write('echo.\n')
            f.write('set /p confirm=确定要卸载吗? (y/n): \n')
            f.write('if /i not "%%confirm%%"=="y" (\n')
            f.write('    echo 已取消卸载\n')
            f.write('    pause\n')
            f.write('    exit /b 0\n')
            f.write(')\n')
            f.write('echo.\n')
            f.write('echo 正在卸载...\n')
            f.write('echo.\n')
            f.write('HardwareMonitor.exe --uninstall\n')
            f.write('echo.\n')
            f.write('echo 如需删除本程序文件,请手动删除:\n')
            f.write('echo   HardwareMonitor.exe\n')
            f.write('pause\n')
        print(f"✓ 已创建: 卸载程序.bat")

        # 创建说明文档
        readme = package_dir / "使用说明.txt"
        with open(readme, 'w', encoding='utf-8') as f:
            f.write(self._generate_readme())
        print(f"✓ 已创建: 使用说明.txt")

        # 创建快速开始指南
        quickstart = package_dir / "快速开始.txt"
        with open(quickstart, 'w', encoding='utf-8') as f:
            f.write(self._generate_quickstart())
        print(f"✓ 已创建: 快速开始.txt")

        print()
        print("=" * 70)
        print(f"  ✓ 部署包已创建: {package_dir}")
        print("=" * 70)
        print()
        print("部署包内容:")
        print("  - HardwareMonitor.exe (主程序,含Python环境)")
        print("  - config/config.json (配置文件,需修改服务器地址)")
        print("  - config/config.example.json (配置示例)")
        print("  - 启动配置工具.bat (配置向导)")
        print("  - 安装为开机自启.bat (一键安装)")
        print("  - 卸载程序.bat (一键卸载)")
        print("  - 使用说明.txt (详细文档)")
        print("  - 快速开始.txt (快速指南)")
        print()
        print("使用方法:")
        print("  1. 将整个文件夹复制到目标电脑")
        print("  2. 编辑 config/config.json,修改服务器地址")
        print("  3. 双击 安装为开机自启.bat 完成安装")
        print("  4. 如需卸载,双击 卸载程序.bat")
        print()

        return True

    def _generate_readme(self):
        """生成使用说明"""
        return """================================================================================
                    硬件监控客户端 - 使用说明
================================================================================

一、系统要求
-----------
- Windows 7/8/10/11 (64位推荐)
- 无需安装Python环境
- 需要网络连接以访问服务器

二、文件说明
-----------
HardwareMonitor.exe          - 主程序(已包含Python环境)
config/config.json           - 配置文件(需要修改)
config/config.example.json   - 配置示例
启动配置工具.bat             - 图形化配置向导
安装为开机自启.bat           - 一键安装脚本
卸载程序.bat                 - 一键卸载脚本
使用说明.txt                 - 本文档
快速开始.txt                 - 快速入门指南

三、快速开始
-----------

方法1: 使用批处理脚本(推荐)
  1. 编辑 config/config.json,修改服务器地址
  2. 双击 "安装为开机自启.bat"
  3. 完成!程序会在后台运行

方法2: 手动配置
  1. 双击 HardwareMonitor.exe 运行
  2. 选择选项4进入配置编辑器
  3. 修改服务器URL为你的服务器地址
  4. 选择选项2安装为开机自启

四、配置说明
-----------

重要配置项(config/config.json):

1. server.url
   服务器地址,必须修改!
   例如: "http://192.168.1.100:5000"

2. client.report_interval
   上报间隔(秒),默认300秒(5分钟)

3. client.group_name
   分组名称,用于在服务器端分类
   例如: "财务部", "办公室", "机房"

4. client.auto_start
   是否开机自启, true/false

五、命令行参数
-------------
HardwareMonitor.exe              - 交互模式(显示菜单)
HardwareMonitor.exe --silent     - 静默运行(后台)
HardwareMonitor.exe --install    - 安装为开机自启
HardwareMonitor.exe --config     - 配置编辑器

六、常见问题
-----------

Q1: 程序运行后没有界面?
A: 这是正常的,程序设计为后台静默运行。
   可以在任务管理器中看到HardwareMonitor.exe进程。

Q2: 如何确认程序正在运行?
A: 1. 查看任务管理器中的进程
   2. 查看client.log日志文件
   3. 在服务端Web界面查看是否收到数据

Q3: 上报失败怎么办?
A: 1. 检查config.json中的服务器地址是否正确
   2. 确认服务器正在运行
   3. 检查网络连接: ping 服务器IP
   4. 检查防火墙设置
   5. 查看client.log日志获取详细错误

Q4: 如何停止程序?
A: 1. 在任务管理器中结束HardwareMonitor.exe进程
   2. 取消开机自启设置

Q5: 如何更新配置?
A: 直接编辑config.json文件,然后重启程序即可。
   或者运行 HardwareMonitor.exe --config 进入配置向导。

Q6: exe文件很大(30-50MB)?
A: 这是正常的,因为包含了完整的Python环境和所有依赖库。
   优点是目标电脑无需安装任何软件即可运行。

Q7: 杀毒软件报毒?
A: PyInstaller打包的exe可能被误报。
   解决方法:
   1. 添加到杀毒软件白名单
   2. 使用代码签名证书(企业环境)
   3. 联系杀毒软件厂商提交误报

七、日志文件
-----------
日志文件: client.log
位置: 与exe同目录

日志包含:
- 程序启动时间
- 客户端ID
- 每次上报结果
- 错误信息

八、技术支持
-----------
如遇到问题,请提供以下信息:
1. 操作系统版本
2. client.log日志内容
3. config.json配置(隐藏敏感信息)
4. 具体的错误信息

================================================================================
"""

    def _generate_quickstart(self):
        """生成快速开始指南"""
        return """================================================================================
                         快速开始 - 3步完成部署
================================================================================

第一步: 修改配置 (1分钟)
----------------------
用记事本打开 config/config.json

找到这一行:
    "url": "http://localhost:5000"

修改为你的服务器地址:
    "url": "http://192.168.1.100:5000"

保存文件(Ctrl+S)

第二步: 安装程序 (10秒)
----------------------
双击 "安装为开机自启.bat"

等待提示"安装完成"

第三步: 验证 (30秒)
------------------
1. 打开浏览器访问服务器Web界面
2. 应该能看到新出现的客户端
3. 点击"详情"查看硬件信息

完成!
-----
程序现在会:
✓ 开机自动启动
✓ 每5分钟上报一次硬件信息
✓ 静默后台运行
✓ 记录日志到client.log

其他操作:
--------
- 查看配置: 双击 HardwareMonitor.exe,选择5
- 修改配置: 双击 "启动配置工具.bat"
- 卸载程序: 任务管理器结束进程,删除文件夹

================================================================================
"""

    def run(self):
        """执行完整打包流程"""
        try:
            # 步骤0: 检查前置条件
            if not self.check_prerequisites():
                print("\n✗ 前置检查失败,无法继续")
                input("\n按回车键退出...")
                return False

            # 步骤1: 安装依赖
            if not self.install_dependencies():
                print("\n✗ 依赖安装失败")
                input("\n按回车键退出...")
                return False

            # 步骤2: 创建spec文件
            self.create_spec_file()

            # 步骤3: 打包exe
            if not self.build_exe():
                print("\n✗ 打包失败")
                input("\n按回车键退出...")
                return False

            # 步骤4: 创建部署包
            self.create_deployment_package()

            print()
            print("=" * 70)
            print("  🎉 全部完成!")
            print("=" * 70)
            print()
            print("下一步:")
            print(f"  1. 测试: 运行 dist/HardwareMonitor.exe")
            print(f"  2. 部署: 复制 dist/HardwareMonitor_部署包 到目标电脑")
            print(f"  3. 配置: 编辑 config/config.json 修改服务器地址")
            print()

            return True

        except Exception as e:
            print(f"\n✗ 打包过程出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    tool = BuildTool()
    success = tool.run()

    if not success:
        print("\n打包失败,请检查上述错误信息")

    input("\n按回车键退出...")
