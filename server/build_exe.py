"""
服务端打包脚本
将Flask服务端打包为独立的exe文件
"""

import os
import sys
import subprocess
import shutil
import json
from pathlib import Path

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class ServerBuildTool:
    """服务端打包工具类"""

    def __init__(self):
        self.current_dir = Path(__file__).parent.absolute()
        self.dist_dir = self.current_dir / "dist"
        self.build_dir = self.current_dir / "build"

    def check_prerequisites(self):
        """检查打包前置条件"""
        print("=" * 70)
        print("  硬件监控系统服务端 - 打包工具")
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
            "app.py",
            "templates/index.html",
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

    def build_server(self):
        """执行打包"""
        print("=" * 70)
        print("  步骤 2: 开始打包服务端")
        print("=" * 70)
        print()
        print("这可能需要几分钟时间,请耐心等待...")
        print("打包过程中会:")
        print("  - 分析依赖关系(Flask等)")
        print("  - 收集Python运行时库")
        print("  - 收集所有第三方库")
        print("  - 打包templates文件夹")
        print()

        # 清理旧的构建文件
        if self.build_dir.exists():
            print("清理旧的构建文件...")
            shutil.rmtree(self.build_dir)

        if self.dist_dir.exists():
            shutil.rmtree(self.dist_dir)

        # 执行PyInstaller(使用--onedir模式,因为包含templates等文件)
        try:
            cmd = [
                sys.executable, "-m", "PyInstaller",
                "--onefile",
                "--console",
                "--name=HardwareMonitorServer",
                f"--add-data=templates{os.pathsep}templates",
                "--hidden-import=flask",
                "--hidden-import=flask_cors",
                "--hidden-import=waitress",
                "--hidden-import=concurrent.futures",
                "--hidden-import=requests",
                "--hidden-import=sqlite3",
                "--hidden-import=json",
                "--hidden-import=csv",
                "--clean",
                "app.py"
            ]

            result = subprocess.run(
                cmd,
                cwd=str(self.current_dir),
                check=True,
                capture_output=True,
                text=True
            )

            # 检查是否成功
            exe_path = self.dist_dir / "HardwareMonitorServer.exe"
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
                print("  - 目标服务器无需安装Python")
                print("  - 运行后会自动创建数据库和初始化数据")
                print("  - 默认监听端口: 5000")
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
        print("  步骤 3: 创建服务端部署包")
        print("=" * 70)
        print()

        package_dir = self.dist_dir / "HardwareMonitorServer_部署包"

        # 创建目录结构
        if package_dir.exists():
            shutil.rmtree(package_dir)

        package_dir.mkdir(parents=True)
        (package_dir / "data").mkdir()

        # 复制exe
        exe_path = self.dist_dir / "HardwareMonitorServer.exe"
        if exe_path.exists():
            shutil.copy2(exe_path, package_dir)
            print(f"✓ 已复制: HardwareMonitorServer.exe")

        # 创建启动脚本
        startup_batch = package_dir / "启动服务端.bat"
        with open(startup_batch, 'w', encoding='gbk') as f:
            f.write('@echo off\n')
            f.write('chcp 65001 >nul\n')
            f.write('echo ========================================\n')
            f.write('   硬件监控系统服务端\n')
            f.write('echo ========================================\n')
            f.write('echo.\n')
            f.write('echo 正在启动服务端...\n')
            f.write('echo.\n')
            f.write('HardwareMonitorServer.exe\n')
            f.write('echo.\n')
            f.write('pause\n')
        print(f"✓ 已创建: 启动服务端.bat")

        # 创建后台运行脚本(无控制台)
        run_silent_batch = package_dir / "后台运行.bat"
        with open(run_silent_batch, 'w', encoding='gbk') as f:
            f.write('@echo off\n')
            f.write('chcp 65001 >nul\n')
            f.write('start /min HardwareMonitorServer.exe\n')
            f.write('echo 服务端已在后台启动\n')
            f.write('echo 访问地址: http://localhost:5000\n')
            f.write('pause\n')
        print(f"✓ 已创建: 后台运行.bat")

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
        print(f"  ✓ 服务端部署包已创建: {package_dir}")
        print("=" * 70)
        print()
        print("部署包内容:")
        print("  - HardwareMonitorServer.exe (服务端主程序)")
        print("  - data/ (数据库目录,自动创建)")
        print("  - 启动服务端.bat (启动脚本)")
        print("  - 后台运行.bat (后台运行)")
        print("  - 使用说明.txt (详细文档)")
        print("  - 快速开始.txt (快速指南)")
        print()
        print("使用方法:")
        print("  1. 将整个文件夹复制到服务器电脑")
        print("  2. 双击 启动服务端.bat 启动服务端")
        print("  3. 浏览器访问 http://服务器IP:5000")
        print()

        return True

    def _generate_readme(self):
        """生成使用说明"""
        return """================================================================================
                    硬件监控系统服务端 - 使用说明
================================================================================

一、系统要求
-----------
- Windows 7/8/10/11 Server (64位推荐)
- 无需安装Python环境
- 需要开放端口5000(或自定义端口)

二、文件说明
-----------
HardwareMonitorServer.exe      - 服务端主程序(已包含Python环境)
data/                          - 数据库目录(自动创建)
启动服务端.bat                 - 启动脚本(带控制台窗口)
后台运行.bat                   - 后台运行脚本
使用说明.txt                   - 本文档
快速开始.txt                   - 快速入门指南

三、快速开始
-----------

1. 启动服务端
   双击 "启动服务端.bat"
   看到 "硬件监控系统服务端启动" 提示

2. 访问Web界面
   打开浏览器访问: http://localhost:5000
   或从其他电脑访问: http://服务器IP:5000

3. 配置客户端
   客户端的服务器地址需要指向服务端IP:
   http://服务器IP:5000

四、端口配置
-----------

默认端口: 5000

如需修改端口:
1. 编辑 app.py 文件
2. 找到最后一行: app.run(host='0.0.0.0', port=5000, debug=True)
3. 修改 port=5000 为需要的端口号
4. 重新打包

五、数据库说明
-----------

数据库文件: hardware_monitor.db
位置: 与exe同目录

包含表:
- groups: 分组信息
- clients: 客户端信息
- hardware_reports: 硬件信息历史记录

六、常见问题
-----------

Q1: 服务端启动失败?
A: 1. 检查5000端口是否被占用
   2. 尝试更换端口号
   3. 检查防火墙设置

Q2: Web界面无法访问?
A: 1. 确认服务端正在运行
   2. 检查浏览器地址是否正确
   3. 检查防火墙是否开放端口
   4. 从其他电脑访问需要使用服务器IP

Q3: 如何开放防火墙端口?
A: 管理员身份运行命令:
   netsh advfirewall firewall add rule name="HardwareMonitor" dir=in action=allow protocol=TCP localport=5000

Q4: 如何停止服务端?
A: 在控制台窗口按 Ctrl+C
   或在任务管理器中结束 HardwareMonitorServer.exe 进程

Q5: 客户端无法上报数据?
A: 1. 确认客户端配置的服务器地址正确
   2. 确认网络通畅
   3. 检查防火墙设置
   4. 查看服务端控制台输出

七、日志查看
-----------

服务端运行时会显示:
- 启动信息
- 客户端连接日志
- API请求记录

如需查看客户端信息,访问Web界面的客户端列表。

八、数据备份
-----------

数据库文件: hardware_monitor.db

备份方法:
1. 停止服务端
2. 复制 hardware_monitor.db 文件
3. 恢复时替换该文件并重启服务端

九、技术支持
-----------

如遇到问题,请提供以下信息:
1. 操作系统版本
2. 服务端控制台输出
3. 具体的错误信息

================================================================================
"""

    def _generate_quickstart(self):
        """生成快速开始指南"""
        return """================================================================================
                         快速开始 - 3步完成部署
================================================================================

第一步: 启动服务端 (10秒)
------------------------
双击 "启动服务端.bat"

看到提示:
  硬件监控系统服务端启动
  访问地址: http://localhost:5000

第二步: 访问Web界面 (30秒)
------------------------
打开浏览器访问: http://localhost:5000
或从其他电脑: http://服务器IP:5000

第三步: 配置客户端 (1分钟)
------------------------
1. 在客户端配置文件(config.json)中修改:
   "url": "http://服务器IP:5000"

2. 客户端会自动上报数据
3. 在Web界面查看客户端列表

完成!
-----
现在您可以:
✓ 查看所有客户端硬件信息
✓ 创建分组管理客户端
✓ 导出数据(CSV/JSON)
✓ 监控客户端在线状态

其他操作:
--------
- 后台运行: 双击 "后台运行.bat"
- 停止服务: 控制台按 Ctrl+C
- 开放端口: 见使用说明.txt

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

            # 步骤2: 打包exe
            if not self.build_server():
                print("\n✗ 打包失败")
                input("\n按回车键退出...")
                return False

            # 步骤3: 创建部署包
            self.create_deployment_package()

            print()
            print("=" * 70)
            print("  🎉 全部完成!")
            print("=" * 70)
            print()
            print("下一步:")
            print(f"  1. 测试: 运行 dist/HardwareMonitorServer.exe")
            print(f"  2. 部署: 复制 dist/HardwareMonitorServer_部署包 到服务器")
            print(f"  3. 启动: 双击 启动服务端.bat")
            print()

            return True

        except Exception as e:
            print(f"\n✗ 打包过程出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    tool = ServerBuildTool()
    success = tool.run()

    if not success:
        print("\n打包失败,请检查上述错误信息")

    input("\n按回车键退出...")
