"""
硬件监控系统服务端 - HwMonServer
Flask Web应用,提供API和Web管理界面
支持高并发采集(1000+客户端)
使用MySQL数据库支持高并发
"""

import os
import json
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for
from flask_cors import CORS
import io
import csv
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
import functools
import pymysql
from dbutils.pooled_db import PooledDB

app = Flask(__name__)
CORS(app)

# 加载配置文件
def load_config():
    """加载配置文件"""
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"警告: 无法加载配置文件 {config_file}: {e}")
        print("使用默认配置")
        return {
            'database': {
                'host': '192.168.20.17',
                'port': 3306,
                'user': 'HwMon',
                'password': 'kk7cy7SDWDMXC5XQ',
                'database': 'hwmon',
                'charset': 'utf8mb4'
            },
            'login': {
                'username': 'xapi',
                'password': 'Ai78965'
            },
            'server': {
                'port': 5000,
                'host': '0.0.0.0'
            },
            'collect': {
                'max_workers': 50,
                'timeout': 15,
                'retry_times': 0
            }
        }

CONFIG = load_config()

# 登录配置
app.secret_key = 'HwMon_secret_key_2026'  # 用于session加密
LOGIN_CONFIG = CONFIG.get('login', {
    'username': 'xapi',
    'password': 'Ai78965'
})

# MySQL数据库配置（从配置文件读取）
db_config = CONFIG.get('database', {})
MYSQL_CONFIG = {
    'host': db_config.get('host', '192.168.20.17'),
    'port': db_config.get('port', 3306),
    'user': db_config.get('user', 'HwMon'),
    'password': db_config.get('password', 'kk7cy7SDWDMXC5XQ'),
    'database': db_config.get('database', 'hwmon'),
    'charset': db_config.get('charset', 'utf8mb4'),
    'cursorclass': pymysql.cursors.DictCursor,
    'init_command': "SET time_zone='+08:00', innodb_lock_wait_timeout=10",  # 设置时区为东八区，锁等待超时10秒
    'connect_timeout': 10,  # 连接超时10秒
    'read_timeout': 30,     # 读取超时30秒
    'write_timeout': 30     # 写入超时30秒
}

# 数据库连接池
db_pool = None

# 并发采集配置（从配置文件读取）
collect_config = CONFIG.get('collect', {})
COLLECT_CONFIG = {
    'max_workers': collect_config.get('max_workers', 50),
    'timeout': collect_config.get('timeout', 15),
    'retry_times': collect_config.get('retry_times', 0),
}


def init_db_pool():
    """初始化数据库连接池"""
    global db_pool
    db_pool = PooledDB(
        creator=pymysql,
        maxconnections=100,     # 连接池最大连接数（增加到100支持高并发）
        mincached=10,           # 初始化时创建的空闲连接数
        maxcached=30,           # 连接池最多缓存的空闲连接数
        maxusage=1000,          # 单个连接最多被使用的次数
        blocking=True,          # 连接池满时是否阻塞等待
        ping=1,                 # 连接时检查连接是否可用
        **MYSQL_CONFIG
    )
    print("MySQL连接池初始化成功")
    print("数据库时区: 东八区 (北京时间)")


def get_db():
    """从连接池获取数据库连接"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = db_pool.connection()
            # 设置会话时区为东八区（北京时间）
            cursor = conn.cursor()
            cursor.execute("SET time_zone='+08:00'")
            return conn
        except Exception as e:
            if attempt < max_retries - 1:
                print(f'[WARN] 获取数据库连接失败，重试 {attempt + 1}/{max_retries}: {e}')
                import time
                time.sleep(0.5)
            else:
                raise e


def get_db_readonly():
    """获取只读数据库连接（用于查询操作，避免锁冲突）"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = db_pool.connection()
            cursor = conn.cursor()
            cursor.execute("SET time_zone='+08:00'")
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            return conn
        except Exception as e:
            if attempt < max_retries - 1:
                print(f'[WARN] 获取只读连接失败，重试 {attempt + 1}/{max_retries}: {e}')
                import time
                time.sleep(0.5)
            else:
                raise e


def init_tables():
    """初始化数据库表结构"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # 设置会话时区为东八区
        cursor.execute("SET time_zone='+08:00'")
        
        # 创建分组表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS `groups` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # 创建客户端表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id VARCHAR(255) NOT NULL UNIQUE,
                hostname VARCHAR(255),
                local_ip VARCHAR(45),
                group_id INT,
                last_report DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES `groups`(id) ON DELETE SET NULL,
                INDEX idx_client_id (client_id),
                INDEX idx_group_id (group_id),
                INDEX idx_last_report (last_report)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # 创建硬件信息历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hardware_reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id VARCHAR(255) NOT NULL,
                report_data LONGTEXT,
                report_type VARCHAR(50) DEFAULT 'scheduled',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_client_id (client_id),
                INDEX idx_timestamp (timestamp)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # 创建硬件采集历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hardware_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id VARCHAR(255) NOT NULL,
                cpu_info TEXT,
                memory_info TEXT,
                disk_info TEXT,
                gpu_info TEXT,
                snapshot LONGTEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_client_id (client_id),
                INDEX idx_timestamp (timestamp)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # 创建默认分组
        cursor.execute('INSERT IGNORE INTO `groups` (name, description) VALUES (%s, %s)',
                       ('默认分组', '未分组的客户端'))

        # 创建客户端硬件基准表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_baselines (
                client_id VARCHAR(255) PRIMARY KEY,
                cpu_snapshot TEXT,
                gpu_snapshot TEXT,
                memory_snapshot TEXT,
                disk_snapshot TEXT,
                baseline_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # 创建告警记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id VARCHAR(255) NOT NULL,
                alert_type VARCHAR(100) NOT NULL,
                alert_detail LONGTEXT NOT NULL,
                resolved TINYINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_client_id (client_id),
                INDEX idx_resolved (resolved),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # 创建邮件配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_config (
                id INT PRIMARY KEY,
                smtp_host VARCHAR(255) NOT NULL DEFAULT 'smtp.qq.com',
                smtp_port INT NOT NULL DEFAULT 465,
                smtp_user VARCHAR(255) NOT NULL DEFAULT '',
                smtp_password VARCHAR(255) NOT NULL DEFAULT '',
                sender_name VARCHAR(255) DEFAULT '硬件监控系统',
                recipients TEXT NOT NULL,
                enabled TINYINT DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        cursor.execute('INSERT IGNORE INTO email_config (id, recipients) VALUES (1, "[]")')

        # 创建告警设置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_settings (
                id INT PRIMARY KEY,
                monitor_cpu TINYINT DEFAULT 1,
                monitor_gpu TINYINT DEFAULT 1,
                monitor_memory TINYINT DEFAULT 1,
                monitor_disk TINYINT DEFAULT 1,
                monitor_network TINYINT DEFAULT 0,
                monitor_motherboard TINYINT DEFAULT 0,
                monitor_bios TINYINT DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        cursor.execute('INSERT IGNORE INTO alert_settings (id) VALUES (1)')

        conn.commit()
        print("数据库表初始化完成")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        raise
    finally:
        conn.close()



def login_required(f):
    """登录验证装饰器"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            # 如果是API请求，返回401
            if request.path.startswith('/api/'):
                return jsonify({'error': '未登录', 'need_login': True}), 401
            # 否则重定向到登录页面
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== 硬件变更检测与邮件告警 ====================

def compare_hardware(baseline_snapshots, new_hardware, alert_settings=None):
    """
    对比新硬件数据与基准快照，返回变更列表。
    baseline_snapshots: {'cpu': JSON, 'gpu': JSON, 'memory': JSON, 'disk': JSON}
    new_hardware: 完整的硬件信息dict
    alert_settings: 告警设置dict，包含monitor_cpu, monitor_gpu等字段
    返回: [{'type': 'cpu', 'label': 'CPU', 'old': '...', 'new': '...'}, ...]
    """
    changes = []

    # 如果没有提供告警设置，使用默认设置（全部监控）
    if alert_settings is None:
        alert_settings = {
            'monitor_cpu': 1,
            'monitor_gpu': 1,
            'monitor_memory': 1,
            'monitor_disk': 1,
            'monitor_network': 0,
            'monitor_motherboard': 0,
            'monitor_bios': 0
        }

    # CPU对比 - 对比型号名称
    if alert_settings.get('monitor_cpu', 1):
        old_cpu = json.loads(baseline_snapshots.get('cpu', '[]')) if baseline_snapshots.get('cpu') else []
        new_cpu = new_hardware.get('cpu', [])
        if old_cpu and new_cpu:
            old_names = sorted([c.get('name', '') for c in old_cpu])
            new_names = sorted([c.get('name', '') for c in new_cpu])
            if old_names != new_names:
                changes.append({
                    'type': 'cpu',
                    'label': 'CPU',
                    'old': ', '.join(old_names) if old_names else '未知',
                    'new': ', '.join(new_names) if new_names else '未知'
                })

    # GPU对比 - 对比型号名称
    if alert_settings.get('monitor_gpu', 1):
        old_gpu = json.loads(baseline_snapshots.get('gpu', '[]')) if baseline_snapshots.get('gpu') else []
        new_gpu = new_hardware.get('gpu', [])
        if old_gpu and new_gpu:
            old_names = sorted([g.get('name', '') for g in old_gpu])
            new_names = sorted([g.get('name', '') for g in new_gpu])
            if old_names != new_names:
                changes.append({
                    'type': 'gpu',
                    'label': 'GPU',
                    'old': ', '.join(old_names) if old_names else '未知',
                    'new': ', '.join(new_names) if new_names else '未知'
                })

    # 内存对比 - 对比总容量
    if alert_settings.get('monitor_memory', 1):
        old_mem = json.loads(baseline_snapshots.get('memory', '{}')) if baseline_snapshots.get('memory') else {}
        new_mem = new_hardware.get('memory', {})
        if old_mem and new_mem:
            old_total = old_mem.get('total_capacity', 0)
            new_total = new_mem.get('total_capacity', 0)
            # 计算单条容量总和作为总容量
            if not old_total and old_mem.get('modules'):
                old_total = sum(m.get('capacity', 0) for m in old_mem['modules'])
            if not new_total and new_mem.get('modules'):
                new_total = sum(m.get('capacity', 0) for m in new_mem['modules'])
            if old_total and new_total and old_total != new_total:
                old_gb = old_total / (1024**3)
                new_gb = new_total / (1024**3)
                changes.append({
                    'type': 'memory',
                    'label': '内存',
                    'old': f'{old_gb:.1f} GB',
                    'new': f'{new_gb:.1f} GB'
                })

    # 硬盘对比 - 对比数量、型号和容量
    if alert_settings.get('monitor_disk', 1):
        old_disk = json.loads(baseline_snapshots.get('disk', '[]')) if baseline_snapshots.get('disk') else []
        new_disk = new_hardware.get('disk', [])
        if old_disk and new_disk:
            old_info = sorted([(d.get('model', ''), d.get('size', 0)) for d in old_disk])
            new_info = sorted([(d.get('model', ''), d.get('size', 0)) for d in new_disk])
            if len(old_disk) != len(new_disk) or old_info != new_info:
                old_str = ', '.join([f"{d.get('model','?')}({d.get('size',0)//(1024**3)}GB)" for d in old_disk])
                new_str = ', '.join([f"{d.get('model','?')}({d.get('size',0)//(1024**3)}GB)" for d in new_disk])
                changes.append({
                    'type': 'disk',
                    'label': '硬盘',
                    'old': old_str or '未知',
                    'new': new_str or '未知'
                })

    # 网卡对比 - 对比网卡数量和描述
    if alert_settings.get('monitor_network', 0):
        old_network = json.loads(baseline_snapshots.get('network', '[]')) if baseline_snapshots.get('network') else []
        new_network = new_hardware.get('network', [])
        if old_network and new_network:
            old_descs = sorted([n.get('description', '') for n in old_network])
            new_descs = sorted([n.get('description', '') for n in new_network])
            if old_descs != new_descs:
                changes.append({
                    'type': 'network',
                    'label': '网卡',
                    'old': ', '.join(old_descs) if old_descs else '未知',
                    'new': ', '.join(new_descs) if new_descs else '未知'
                })

    # 主板对比 - 对比制造商和型号
    if alert_settings.get('monitor_motherboard', 0):
        old_mb = json.loads(baseline_snapshots.get('motherboard', '{}')) if baseline_snapshots.get('motherboard') else {}
        new_mb = new_hardware.get('motherboard', {})
        if old_mb and new_mb:
            old_info = f"{old_mb.get('manufacturer', '')}-{old_mb.get('product', '')}"
            new_info = f"{new_mb.get('manufacturer', '')}-{new_mb.get('product', '')}"
            if old_info != new_info:
                changes.append({
                    'type': 'motherboard',
                    'label': '主板',
                    'old': old_info or '未知',
                    'new': new_info or '未知'
                })

    # BIOS对比 - 对比制造商和版本
    if alert_settings.get('monitor_bios', 0):
        old_bios = json.loads(baseline_snapshots.get('bios', '{}')) if baseline_snapshots.get('bios') else {}
        new_bios = new_hardware.get('bios', {})
        if old_bios and new_bios:
            old_info = f"{old_bios.get('manufacturer', '')}-{old_bios.get('version', '')}"
            new_info = f"{new_bios.get('manufacturer', '')}-{new_bios.get('version', '')}"
            if old_info != new_info:
                changes.append({
                    'type': 'bios',
                    'label': 'BIOS',
                    'old': old_info or '未知',
                    'new': new_info or '未知'
                })

    return changes


def get_email_config(conn):
    """获取邮件配置"""
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM email_config WHERE id = 1')
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def send_alert_email(client_id, hostname, local_ip, changes):
    """发送硬件变更告警邮件"""
    try:
        conn = get_db_readonly()  # 只读查询使用只读连接
        config = get_email_config(conn)
        conn.close()

        if not config or not config.get('enabled'):
            return False

        recipients = json.loads(config.get('recipients', '[]'))
        if not recipients:
            return False

        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = config['smtp_host']
        smtp_port = config['smtp_port']
        smtp_user = config['smtp_user']
        smtp_password = config['smtp_password']
        sender_name = config.get('sender_name', '硬件监控系统')

        # 构建邮件内容
        change_lines = []
        for c in changes:
            change_lines.append(f'<p><strong>{c["label"]}:</strong> {c["old"]} → {c["new"]}</p>')

        html_body = f'''
        <html><body style="font-family:Microsoft YaHei,Arial,sans-serif;">
        <h2 style="color:#e53e3e;">【硬件变更告警】</h2>
        <table style="border-collapse:collapse;">
            <tr><td style="padding:5px 10px;font-weight:bold;">客户端:</td><td style="padding:5px 10px;">{hostname or client_id}</td></tr>
            <tr><td style="padding:5px 10px;font-weight:bold;">IP地址:</td><td style="padding:5px 10px;">{local_ip or '-'}</td></tr>
            <tr><td style="padding:5px 10px;font-weight:bold;">变更时间:</td><td style="padding:5px 10px;">{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
        </table>
        <h3 style="margin-top:20px;">变更详情:</h3>
        {''.join(change_lines)}
        <hr style="margin:20px 0;">
        <p style="color:#718096;">如需重置基准，请登录硬件监控系统进行操作。</p>
        </body></html>
        '''

        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'【硬件变更告警】客户端 {hostname or client_id} 检测到硬件变更'
        msg['From'] = f'{sender_name} <{smtp_user}>'
        msg['To'] = ', '.join(recipients)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        # 发送邮件
        server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipients, msg.as_string())
        server.quit()
        return True

    except Exception as e:
        import traceback
        print(f'邮件发送失败: {str(e)}')
        print(traceback.format_exc())
        return False


def _check_hardware_changes(cursor, conn, client_id, hostname, local_ip, hardware_info,
                            cpu_info, gpu_info, mem_info, disk_info):
    """检查硬件变更（独立事务，不阻塞主流程）"""
    try:
        # 检查是否有基准数据
        cursor.execute('SELECT * FROM client_baselines WHERE client_id = %s', (client_id,))
        baseline = cursor.fetchone()

        if not baseline:
            # 首次上报：自动创建基准
            cursor.execute('''
                INSERT INTO client_baselines (client_id, cpu_snapshot, gpu_snapshot, memory_snapshot, disk_snapshot)
                VALUES (%s, %s, %s, %s, %s)
            ''', (client_id, cpu_info, gpu_info, mem_info, disk_info))
            conn.commit()
            print(f'[INFO] 客户端 {client_id} 首次上报，已自动创建基准')
        else:
            # 有基准：对比硬件变化
            # 获取告警设置
            cursor.execute('SELECT * FROM alert_settings WHERE id = 1')
            alert_settings_row = cursor.fetchone()
            alert_settings = dict(alert_settings_row) if alert_settings_row else None

            baseline_snapshots = {
                'cpu': baseline['cpu_snapshot'],
                'gpu': baseline['gpu_snapshot'],
                'memory': baseline['memory_snapshot'],
                'disk': baseline['disk_snapshot'],
                'network': json.dumps(hardware_info.get('network', []), ensure_ascii=False) if hardware_info.get('network') else '',
                'motherboard': json.dumps(hardware_info.get('motherboard', {}), ensure_ascii=False) if hardware_info.get('motherboard') else '',
                'bios': json.dumps(hardware_info.get('bios', {}), ensure_ascii=False) if hardware_info.get('bios') else ''
            }

            changes = compare_hardware(baseline_snapshots, hardware_info, alert_settings)

            if changes:
                # 发现变更：记录告警
                alert_detail = json.dumps(changes, ensure_ascii=False)
                cursor.execute('''
                    INSERT INTO alert_records (client_id, alert_type, alert_detail)
                    VALUES (%s, %s, %s)
                ''', (client_id, 'hardware_change', alert_detail))
                conn.commit()

                print(f'[ALERT] 客户端 {client_id} 检测到硬件变更: {len(changes)} 项')

                # 尝试发送邮件（不阻塞主流程）
                try:
                    email_sent = send_alert_email(client_id, hostname, local_ip, changes)
                    if email_sent:
                        print(f'[INFO] 已向管理员发送告警邮件')
                    else:
                        print(f'[WARN] 告警邮件发送失败（可能未配置或配置错误）')
                except Exception as e:
                    print(f'[WARN] 发送邮件异常: {e}')
    except Exception as e:
        # 回滚事务
        try:
            conn.rollback()
        except:
            pass
        raise e


# =================================================================


def collect_single_client(client_id, local_ip):
    """采集单个客户端(用于并发执行)"""
    if not local_ip:
        return {
            'client_id': client_id,
            'status': 'unknown_ip',
            'message': 'IP地址未知'
        }

    try:
        response = requests.post(
            f'http://{local_ip}:13301/api/collect',
            json={'trigger': 'server'},
            timeout=COLLECT_CONFIG['timeout']
        )

        if response.status_code == 200:
            return {
                'client_id': client_id,
                'status': 'success',
                'message': '采集成功'
            }
        else:
            return {
                'client_id': client_id,
                'status': 'failed',
                'message': f'HTTP {response.status_code}'
            }

    except requests.exceptions.Timeout:
        return {
            'client_id': client_id,
            'status': 'timeout',
            'message': '连接超时'
        }
    except requests.exceptions.ConnectionError:
        return {
            'client_id': client_id,
            'status': 'offline',
            'message': '无法连接,客户端可能离线或防火墙阻止'
        }
    except Exception as e:
        return {
            'client_id': client_id,
            'status': 'error',
            'message': str(e)
        }


@app.route('/')
def index():
    """主页"""
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')


@app.route('/login')
def login():
    """登录页面"""
    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    """登录API"""
    try:
        data = request.json
        username = data.get('username', '')
        password = data.get('password', '')

        if username == LOGIN_CONFIG['username'] and password == LOGIN_CONFIG['password']:
            session['logged_in'] = True
            session['username'] = username
            return jsonify({'status': 'success', 'message': '登录成功'})
        else:
            return jsonify({'status': 'error', 'message': '用户名或密码错误'}), 401

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """登出API"""
    session.clear()
    return jsonify({'status': 'success', 'message': '已登出'})


@app.route('/api/check-login', methods=['GET'])
def check_login():
    """检查登录状态"""
    if 'logged_in' in session:
        return jsonify({'status': 'success', 'logged_in': True, 'username': session.get('username')})
    else:
        return jsonify({'status': 'success', 'logged_in': False})


@app.route('/api/report', methods=['POST'])
def receive_report():
    """接收客户端上报的硬件信息（含基准管理和变更检测）"""
    # 重试机制：最多重试3次
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return _process_report(attempt + 1, max_retries)
        except Exception as e:
            error_msg = str(e)
            if 'Lock wait timeout' in error_msg and attempt < max_retries - 1:
                print(f'[WARN] 数据库锁超时，重试 {attempt + 1}/{max_retries}')
                import time
                time.sleep(0.5 * (attempt + 1))  # 递增延迟
                continue
            else:
                import traceback
                traceback.print_exc()
                return jsonify({'error': error_msg}), 500


def _process_report(attempt, max_retries):
    """处理客户端上报数据（内部函数）"""
    try:
        data = request.json
        client_id = data.get('client_id')
        hostname = data.get('hostname')
        hardware_info = data.get('hardware_info')
        local_ip = data.get('local_ip', '')
        report_type = data.get('report_type', 'scheduled')

        if not client_id:
            return jsonify({'error': '缺少client_id'}), 400

        conn = get_db()
        cursor = conn.cursor()

        # 步骤1: 快速更新客户端信息（单独事务，减少锁持有时间）
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO clients (client_id, hostname, local_ip, last_report)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                hostname = VALUES(hostname),
                local_ip = VALUES(local_ip),
                last_report = VALUES(last_report)
        ''', (client_id, hostname, local_ip, current_time))
        conn.commit()  # 立即提交，释放锁

        # 步骤2: 保存硬件报告（单独事务）
        cursor.execute('''
            INSERT INTO hardware_reports (client_id, report_data, report_type)
            VALUES (%s, %s, %s)
        ''', (client_id, json.dumps(hardware_info, ensure_ascii=False), report_type))

        # 提取关键硬件指标
        cpu_info = json.dumps(hardware_info.get('cpu', []), ensure_ascii=False) if hardware_info.get('cpu') else ''
        mem_info = json.dumps(hardware_info.get('memory', {}), ensure_ascii=False) if hardware_info.get('memory') else ''
        disk_info = json.dumps(hardware_info.get('disk', []), ensure_ascii=False) if hardware_info.get('disk') else ''
        gpu_info = json.dumps(hardware_info.get('gpu', []), ensure_ascii=False) if hardware_info.get('gpu') else ''

        cursor.execute('''
            INSERT INTO hardware_history (client_id, cpu_info, memory_info, disk_info, gpu_info, snapshot)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (client_id, cpu_info, mem_info, disk_info, gpu_info, json.dumps(hardware_info, ensure_ascii=False)))

        # 清理历史记录，只保留最近10条
        cursor.execute('''
            DELETE FROM hardware_history
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id FROM hardware_history
                    WHERE client_id = %s
                    ORDER BY timestamp DESC
                    LIMIT 10
                ) AS tmp
            )
            AND client_id = %s
        ''', (client_id, client_id))
        conn.commit()  # 提交硬件历史相关操作

        # 步骤3: 硬件变更检测（异步处理，不阻塞主流程）
        try:
            _check_hardware_changes(cursor, conn, client_id, hostname, local_ip, hardware_info,
                                    cpu_info, gpu_info, mem_info, disk_info)
        except Exception as e:
            # 变更检测失败不影响主流程
            print(f'[WARN] 硬件变更检测失败: {e}')

        conn.close()
        return jsonify({'status': 'success', 'message': '接收成功'})

    except Exception as e:
        raise e  # 抛出异常，由外层重试机制处理


@app.route('/api/clients', methods=['GET'])
@login_required
def get_clients():
    """获取所有客户端列表（支持排序和过滤）"""
    try:
        group_id = request.args.get('group_id')
        sort_by = request.args.get('sort_by', 'last_report')  # 默认按最后上报时间排序
        order = request.args.get('order', 'desc')  # 默认降序
        
        conn = get_db_readonly()  # 使用只读连接避免锁冲突
        cursor = conn.cursor()

        # 验证排序字段
        valid_sort_fields = ['hostname', 'local_ip', 'group_name', 'last_report', 'created_at']
        if sort_by not in valid_sort_fields:
            sort_by = 'last_report'
        
        # 验证排序方向
        order = 'DESC' if order.lower() == 'desc' else 'ASC'
        
        # 构建查询
        if group_id == 'ungrouped':
            # 查询未分组的客户端
            cursor.execute(f'''
                SELECT c.*, g.name as group_name
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                WHERE c.group_id IS NULL
                ORDER BY c.{sort_by} {order}
            ''')
        elif group_id:
            cursor.execute(f'''
                SELECT c.*, g.name as group_name
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                WHERE c.group_id = %s
                ORDER BY c.{sort_by} {order}
            ''', (group_id,))
        else:
            cursor.execute(f'''
                SELECT c.*, g.name as group_name
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                ORDER BY c.{sort_by} {order}
            ''')

        clients = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({'status': 'success', 'data': clients})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/client/<client_id>', methods=['GET'])
@login_required
def get_client_detail(client_id):
    """获取客户端详细信息"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 获取客户端基本信息
        cursor.execute('''
            SELECT c.*, g.name as group_name
            FROM clients c
            LEFT JOIN `groups` g ON c.group_id = g.id
            WHERE c.client_id = %s
        ''', (client_id,))

        client = cursor.fetchone()
        if not client:
            conn.close()
            return jsonify({'error': '客户端不存在'}), 404

        client_info = dict(client)

        # 获取最新的硬件报告
        cursor.execute('''
            SELECT report_data, report_type, timestamp
            FROM hardware_reports
            WHERE client_id = %s
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (client_id,))

        report = cursor.fetchone()
        if report:
            client_info['latest_hardware'] = json.loads(report['report_data'])
            client_info['last_hardware_update'] = report['timestamp']
            client_info['last_report_type'] = report['report_type']

        conn.close()

        return jsonify({'status': 'success', 'data': client_info})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/collect/<client_id>', methods=['POST'])
@login_required
def collect_from_client(client_id):
    """主动采集单个客户端"""
    try:
        conn = get_db_readonly()  # 只读查询使用只读连接
        cursor = conn.cursor()

        # 获取客户端信息
        cursor.execute('SELECT local_ip FROM clients WHERE client_id = %s', (client_id,))
        client = cursor.fetchone()

        if not client:
            conn.close()
            return jsonify({'error': '客户端不存在'}), 404

        local_ip = client['local_ip']
        conn.close()

        if not local_ip:
            return jsonify({'error': '客户端IP地址未知,无法采集'}), 400

        # 使用并发函数采集单个客户端
        result = collect_single_client(client_id, local_ip)

        if result['status'] == 'success':
            return jsonify({
                'status': 'success',
                'message': f'已向客户端 {client_id} 发送采集请求',
                'client_response': result
            })
        else:
            status_code = 500
            if result['status'] == 'timeout':
                status_code = 408
            elif result['status'] in ('offline', 'unknown_ip'):
                status_code = 404

            return jsonify({
                'status': result['status'],
                'message': result['message']
            }), status_code

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/collect/all', methods=['POST'])
@login_required
def collect_all_clients():
    """一键采集: 并发向所有客户端发送采集请求"""
    try:
        # 获取采集参数(支持自定义并发数和超时)
        params = request.json or {}
        max_workers = params.get('max_workers', COLLECT_CONFIG['max_workers'])
        timeout = params.get('timeout', COLLECT_CONFIG['timeout'])

        # 临时覆盖配置
        old_workers = COLLECT_CONFIG['max_workers']
        old_timeout = COLLECT_CONFIG['timeout']
        COLLECT_CONFIG['max_workers'] = max_workers
        COLLECT_CONFIG['timeout'] = timeout

        conn = get_db_readonly()  # 只读查询使用只读连接
        cursor = conn.cursor()

        cursor.execute('SELECT client_id, local_ip FROM clients')
        clients = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if not clients:
            COLLECT_CONFIG['max_workers'] = old_workers
            COLLECT_CONFIG['timeout'] = old_timeout
            return jsonify({
                'status': 'completed',
                'total': 0,
                'success': 0,
                'failed': 0,
                'results': [],
                'elapsed_seconds': 0
            })

        start_time = time.time()
        results = []

        # 使用线程池并发采集
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有采集任务
            futures = {
                executor.submit(collect_single_client, c['client_id'], c['local_ip']): c['client_id']
                for c in clients
            }

            # 收集结果
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({
                        'client_id': futures[future],
                        'status': 'error',
                        'message': str(e)
                    })

        elapsed = time.time() - start_time

        # 统计结果
        success_count = sum(1 for r in results if r['status'] == 'success')
        fail_count = len(results) - success_count

        # 恢复配置
        COLLECT_CONFIG['max_workers'] = old_workers
        COLLECT_CONFIG['timeout'] = old_timeout

        return jsonify({
            'status': 'completed',
            'total': len(clients),
            'success': success_count,
            'failed': fail_count,
            'elapsed_seconds': round(elapsed, 2),
            'concurrency': max_workers,
            'results': results
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/groups', methods=['GET'])
@login_required
def get_groups():
    """获取所有分组"""
    try:
        conn = get_db_readonly()  # 只读查询使用只读连接
        cursor = conn.cursor()

        cursor.execute('''
            SELECT g.*, COUNT(c.id) as client_count
            FROM `groups` g
            LEFT JOIN clients c ON g.id = c.group_id
            GROUP BY g.id
            ORDER BY g.name
        ''')

        groups = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({'status': 'success', 'data': groups})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/groups', methods=['POST'])
@login_required
def create_group():
    """创建新分组"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description', '')

        if not name:
            return jsonify({'error': '分组名称不能为空'}), 400

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('INSERT INTO `groups` (name, description) VALUES (%s, %s)',
                       (name, description))

        conn.commit()
        group_id = cursor.lastrowid
        conn.close()

        return jsonify({'status': 'success', 'group_id': group_id})

    except sqlite3.IntegrityError:
        return jsonify({'error': '分组名称已存在'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/groups/<int:group_id>', methods=['PUT'])
@login_required
def update_group(group_id):
    """更新分组"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description')

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('UPDATE `groups` SET name = %s, description = %s WHERE id = %s',
                       (name, description, group_id))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
@login_required
def delete_group(group_id):
    """删除分组"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 检查是否是默认分组
        cursor.execute('SELECT name FROM `groups` WHERE id = %s', (group_id,))
        group = cursor.fetchone()
        if group and group['name'] == '默认分组':
            conn.close()
            return jsonify({'error': '不能删除默认分组'}), 400

        cursor.execute('DELETE FROM `groups` WHERE id = %s', (group_id,))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/<client_id>/group', methods=['PUT'])
@login_required
def assign_client_to_group(client_id):
    """将客户端分配到分组"""
    try:
        data = request.json
        group_id = data.get('group_id')

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('UPDATE clients SET group_id = %s WHERE client_id = %s',
                       (group_id, client_id))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/<client_id>', methods=['DELETE'])
@login_required
def delete_client(client_id):
    """删除客户端"""
    try:
        conn = get_db()  # 写操作使用普通连接
        cursor = conn.cursor()

        cursor.execute('DELETE FROM clients WHERE client_id = %s', (client_id,))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/csv', methods=['GET'])
@login_required
def export_csv():
    """导出所有客户端信息为CSV"""
    try:
        group_id = request.args.get('group_id')
        conn = get_db_readonly()  # 只读查询使用只读连接
        cursor = conn.cursor()

        if group_id:
            cursor.execute('''
                SELECT c.client_id, c.hostname, c.local_ip, g.name as group_name,
                       c.last_report, c.created_at
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                WHERE c.group_id = %s
                ORDER BY c.last_report DESC
            ''', (group_id,))
        else:
            cursor.execute('''
                SELECT c.client_id, c.hostname, c.local_ip, g.name as group_name,
                       c.last_report, c.created_at
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                ORDER BY c.last_report DESC
            ''')

        clients = cursor.fetchall()

        # 创建CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['客户端ID(主机名)', 'IP地址', '分组', '最后上报时间', '创建时间'])

        for client in clients:
            writer.writerow([
                client['client_id'],
                client['local_ip'] or '-',
                client['group_name'] or '未分组',
                client['last_report'],
                client['created_at']
            ])

        conn.close()

        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'hardware_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/json', methods=['GET'])
@login_required
def export_json():
    """导出所有客户端信息为JSON"""
    try:
        group_id = request.args.get('group_id')
        conn = get_db_readonly()  # 只读查询使用只读连接
        cursor = conn.cursor()

        if group_id:
            cursor.execute('''
                SELECT c.*, g.name as group_name
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                WHERE c.group_id = %s
                ORDER BY c.last_report DESC
            ''', (group_id,))
        else:
            cursor.execute('''
                SELECT c.*, g.name as group_name
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                ORDER BY c.last_report DESC
            ''')

        clients = [dict(row) for row in cursor.fetchall()]

        # 获取每个客户端的最新硬件信息
        for client in clients:
            cursor.execute('''
                SELECT report_data, report_type, timestamp
                FROM hardware_reports
                WHERE client_id = %s
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (client['client_id'],))

            report = cursor.fetchone()
            if report:
                client['latest_hardware'] = json.loads(report['report_data'])
                client['last_hardware_update'] = report['timestamp']
                client['last_report_type'] = report['report_type']

        conn.close()

        return send_file(
            io.BytesIO(json.dumps(clients, ensure_ascii=False, indent=2).encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'hardware_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/excel', methods=['GET'])
@login_required
def export_excel():
    """导出客户端硬件信息为Excel文件"""
    try:
        group_id = request.args.get('group_id')
        client_ids_param = request.args.get('client_ids')  # 逗号分隔的client_id列表

        conn = get_db_readonly()  # 只读查询使用只读连接
        cursor = conn.cursor()

        # 构建查询
        if client_ids_param:
            client_ids = [cid.strip() for cid in client_ids_param.split(',') if cid.strip()]
            placeholders = ','.join(['%s' for _ in client_ids])
            cursor.execute(f'''
                SELECT c.client_id, c.hostname, c.local_ip, g.name as group_name,
                       c.last_report, c.created_at
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                WHERE c.client_id IN ({placeholders})
                ORDER BY c.last_report DESC
            ''', client_ids)
        elif group_id:
            cursor.execute('''
                SELECT c.client_id, c.hostname, c.local_ip, g.name as group_name,
                       c.last_report, c.created_at
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                WHERE c.group_id = %s
                ORDER BY c.last_report DESC
            ''', (group_id,))
        else:
            cursor.execute('''
                SELECT c.client_id, c.hostname, c.local_ip, g.name as group_name,
                       c.last_report, c.created_at
                FROM clients c
                LEFT JOIN `groups` g ON c.group_id = g.id
                ORDER BY c.last_report DESC
            ''')

        clients = cursor.fetchall()

        # 创建Excel工作簿
        wb = Workbook()
        ws = wb.active
        ws.title = '客户端列表'

        # 表头样式
        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='667eea', end_color='667eea', fill_type='solid')
        header_alignment = Alignment(horizontal='center', vertical='center')

        # 表头
        headers = ['主机名', '客户端ID', 'IP地址', '分组', '最后上报时间', '创建时间',
                   'CPU', '内存', '硬盘', '显卡']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment

        # 填充数据
        for row_idx, client in enumerate(clients, 2):
            client_dict = dict(client)
            client_id = client_dict['client_id']

            # 获取最新硬件信息
            cursor.execute('''
                SELECT report_data FROM hardware_reports
                WHERE client_id = %s ORDER BY timestamp DESC LIMIT 1
            ''', (client_id,))
            report = cursor.fetchone()

            # 提取关键指标
            cpu_str = '-'
            mem_str = '-'
            disk_str = '-'
            gpu_str = '-'

            if report:
                hardware = json.loads(report['report_data'])

                # CPU
                if hardware.get('cpu') and isinstance(hardware['cpu'], list):
                    cpu_names = [c.get('name', '?') for c in hardware['cpu']]
                    cpu_cores = [f"{c.get('cores', '?')}核" for c in hardware['cpu']]
                    cpu_str = ' | '.join([f"{n}({cores})" for n, cores in zip(cpu_names, cpu_cores)])

                # 内存
                if hardware.get('memory'):
                    total = hardware['memory'].get('total_capacity', 0)
                    if total:
                        mem_str = f"{total / (1024**3):.1f} GB"
                    elif hardware['memory'].get('modules'):
                        total = sum(m.get('capacity', 0) for m in hardware['memory']['modules'])
                        mem_str = f"{total / (1024**3):.1f} GB"

                # 硬盘
                if hardware.get('disk') and isinstance(hardware['disk'], list):
                    disk_models = [d.get('model', '?') for d in hardware['disk']]
                    disk_sizes = [f"{d.get('size', 0) / (1024**3):.0f}GB" for d in hardware['disk']]
                    disk_str = ' | '.join([f"{m}({s})" for m, s in zip(disk_models, disk_sizes)])

                # 显卡
                if hardware.get('gpu') and isinstance(hardware['gpu'], list):
                    gpu_names = [g.get('name', '?') for g in hardware['gpu']]
                    gpu_str = ' | '.join(gpu_names)

            ws.cell(row=row_idx, column=1, value=client_dict.get('hostname') or client_id)
            ws.cell(row=row_idx, column=2, value=client_id)
            ws.cell(row=row_idx, column=3, value=client_dict.get('local_ip') or '-')
            ws.cell(row=row_idx, column=4, value=client_dict.get('group_name') or '未分组')
            ws.cell(row=row_idx, column=5, value=client_dict.get('last_report') or '-')
            ws.cell(row=row_idx, column=6, value=client_dict.get('created_at') or '-')
            ws.cell(row=row_idx, column=7, value=cpu_str)
            ws.cell(row=row_idx, column=8, value=mem_str)
            ws.cell(row=row_idx, column=9, value=disk_str)
            ws.cell(row=row_idx, column=10, value=gpu_str)

        # 调整列宽
        col_widths = [15, 20, 16, 15, 22, 22, 40, 12, 40, 30]
        for i, width in enumerate(col_widths, 1):
            ws.column_dimensions[chr(64 + i) if i <= 26 else 'A' + chr(64 + i - 26)].width = width

        conn.close()

        # 保存到内存并返回
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'hardware_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/batch-group', methods=['PUT'])
@login_required
def batch_assign_group():
    """批量分配客户端到分组"""
    try:
        data = request.json
        client_ids = data.get('client_ids', [])
        group_id = data.get('group_id')

        if not client_ids:
            return jsonify({'error': '请选择要操作的客户端'}), 400

        conn = get_db()
        cursor = conn.cursor()

        placeholders = ','.join(['%s' for _ in client_ids])
        cursor.execute(f'''
            UPDATE clients SET group_id = %s
            WHERE client_id IN ({placeholders})
        ''', [group_id] + client_ids)

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'affected': affected,
            'message': f'成功将 {affected} 个客户端分配到分组'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/client/<client_id>/history', methods=['GET'])
@login_required
def get_client_history(client_id):
    """获取客户端硬件采集历史记录（最近10条）"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 验证客户端存在
        cursor.execute('SELECT client_id FROM clients WHERE client_id = %s', (client_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': '客户端不存在'}), 404

        # 获取最近10条历史记录
        cursor.execute('''
            SELECT cpu_info, memory_info, disk_info, gpu_info, snapshot, timestamp
            FROM hardware_history
            WHERE client_id = %s
            ORDER BY timestamp DESC
            LIMIT 10
        ''', (client_id,))

        history = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            # 解析快照
            if row_dict.get('snapshot'):
                snapshot = json.loads(row_dict['snapshot'])
            else:
                snapshot = {}
            row_dict['snapshot'] = snapshot
            history.append(row_dict)

        conn.close()

        return jsonify({'status': 'success', 'data': history})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/batch-delete', methods=['DELETE'])
@login_required
def batch_delete_clients():
    """批量删除客户端"""
    try:
        data = request.json
        client_ids = data.get('client_ids', [])

        if not client_ids:
            return jsonify({'error': '请选择要删除的客户端'}), 400

        conn = get_db()
        cursor = conn.cursor()

        placeholders = ','.join(['%s' for _ in client_ids])
        cursor.execute(f'DELETE FROM clients WHERE client_id IN ({placeholders})', client_ids)
        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'affected': affected,
            'message': f'成功删除 {affected} 个客户端'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/client/<client_id>/baseline', methods=['GET'])
@login_required
def get_client_baseline(client_id):
    """获取客户端的硬件基准信息"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM client_baselines WHERE client_id = %s', (client_id,))
        baseline = cursor.fetchone()

        if not baseline:
            conn.close()
            return jsonify({'status': 'not_found', 'message': '该客户端尚未建立基准'})

        baseline_dict = dict(baseline)
        # 解析JSON字段
        for key in ['cpu_snapshot', 'gpu_snapshot', 'memory_snapshot', 'disk_snapshot']:
            if baseline_dict.get(key):
                baseline_dict[key] = json.loads(baseline_dict[key])

        conn.close()
        return jsonify({'status': 'success', 'data': baseline_dict})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/client/<client_id>/baseline', methods=['POST'])
@login_required
def set_client_baseline(client_id):
    """手动设置/重置客户端的硬件基准（使用当前最新上报数据）"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 验证客户端存在
        cursor.execute('SELECT client_id FROM clients WHERE client_id = %s', (client_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': '客户端不存在'}), 404

        # 获取最新的硬件报告
        cursor.execute('''
            SELECT report_data FROM hardware_reports
            WHERE client_id = %s ORDER BY timestamp DESC LIMIT 1
        ''', (client_id,))
        report = cursor.fetchone()

        if not report:
            conn.close()
            return jsonify({'error': '该客户端尚未上报任何硬件数据'}), 400

        hardware_info = json.loads(report['report_data'])

        # 提取关键指标
        cpu_info = json.dumps(hardware_info.get('cpu', []), ensure_ascii=False) if hardware_info.get('cpu') else ''
        mem_info = json.dumps(hardware_info.get('memory', {}), ensure_ascii=False) if hardware_info.get('memory') else ''
        disk_info = json.dumps(hardware_info.get('disk', []), ensure_ascii=False) if hardware_info.get('disk') else ''
        gpu_info = json.dumps(hardware_info.get('gpu', []), ensure_ascii=False) if hardware_info.get('gpu') else ''

        # 插入或更新基准
        cursor.execute('''
            INSERT INTO client_baselines (client_id, cpu_snapshot, gpu_snapshot, memory_snapshot, disk_snapshot)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cpu_snapshot = VALUES(cpu_snapshot),
                gpu_snapshot = VALUES(gpu_snapshot),
                memory_snapshot = VALUES(memory_snapshot),
                disk_snapshot = VALUES(disk_snapshot),
                baseline_timestamp = CURRENT_TIMESTAMP
        ''', (client_id, cpu_info, gpu_info, mem_info, disk_info))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': '基准设置成功'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/client/<client_id>/alerts', methods=['GET'])
@login_required
def get_client_alerts(client_id):
    """获取指定客户端的告警记录"""
    try:
        resolved = request.args.get('resolved')  # 'true' or 'false' or None for all

        conn = get_db()
        cursor = conn.cursor()

        query = '''
            SELECT a.*, c.hostname, c.local_ip
            FROM alert_records a
            LEFT JOIN clients c ON a.client_id = c.client_id
            WHERE a.client_id = %s
        '''
        params = [client_id]

        if resolved is not None:
            query += ' AND a.resolved = %s'
            params.append(1 if resolved == 'true' else 0)

        query += ' ORDER BY a.created_at DESC'

        cursor.execute(query, params)
        alerts = [dict(row) for row in cursor.fetchall()]

        # 解析alert_detail JSON
        for alert in alerts:
            if alert.get('alert_detail'):
                alert['alert_detail'] = json.loads(alert['alert_detail'])

        conn.close()
        return jsonify({'status': 'success', 'data': alerts})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts', methods=['GET'])
@login_required
def get_all_alerts():
    """获取所有告警记录（支持分页和过滤）"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        resolved = request.args.get('resolved')  # 'true' or 'false' or None

        conn = get_db_readonly()  # 只读查询使用只读连接
        cursor = conn.cursor()

        query = '''
            SELECT a.*, c.hostname, c.local_ip
            FROM alert_records a
            LEFT JOIN clients c ON a.client_id = c.client_id
            WHERE 1=1
        '''
        params = []

        if resolved is not None:
            query += ' AND a.resolved = %s'
            params.append(1 if resolved == 'true' else 0)

        # 获取总数
        count_query = query.replace('SELECT a.*, c.hostname, c.local_ip', 'SELECT COUNT(*)')
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # 分页查询
        query += ' ORDER BY a.created_at DESC LIMIT %s OFFSET %s'
        params.extend([per_page, (page - 1) * per_page])

        cursor.execute(query, params)
        alerts = [dict(row) for row in cursor.fetchall()]

        # 解析alert_detail JSON
        for alert in alerts:
            if alert.get('alert_detail'):
                alert['alert_detail'] = json.loads(alert['alert_detail'])

        conn.close()
        return jsonify({
            'status': 'success',
            'data': alerts,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/<int:alert_id>', methods=['PUT'])
@login_required
def resolve_alert(alert_id):
    """标记单个告警为已解决"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('UPDATE alert_records SET resolved = 1 WHERE id = %s', (alert_id,))

        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': '告警记录不存在'}), 404

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': '告警已标记为已解决'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/batch-resolve', methods=['PUT'])
@login_required
def batch_resolve_alerts():
    """批量标记告警为已解决"""
    try:
        data = request.json
        alert_ids = data.get('alert_ids', [])

        if not alert_ids:
            return jsonify({'error': '请选择要解决的告警'}), 400

        conn = get_db()
        cursor = conn.cursor()

        placeholders = ','.join(['%s' for _ in alert_ids])
        cursor.execute(f'UPDATE alert_records SET resolved = 1 WHERE id IN ({placeholders})', alert_ids)
        affected = cursor.rowcount

        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'affected': affected,
            'message': f'成功标记 {affected} 个告警为已解决'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/email-config', methods=['GET'])
@login_required
def get_email_config_api():
    """获取邮件配置"""
    try:
        conn = get_db_readonly()  # 只读查询使用只读连接
        config = get_email_config(conn)
        conn.close()

        if not config:
            return jsonify({'error': '邮件配置不存在'}), 404

        # 隐藏密码字段（返回时不显示完整密码）
        config_copy = dict(config)
        if config_copy.get('smtp_password'):
            config_copy['smtp_password'] = '******'

        return jsonify({'status': 'success', 'data': config_copy})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/email-config', methods=['PUT'])
@login_required
def update_email_config():
    """更新邮件配置"""
    try:
        data = request.json

        conn = get_db()
        cursor = conn.cursor()

        # 检查是否需要保留原密码
        if data.get('smtp_password') == '******':
            # 获取原密码
            cursor.execute('SELECT smtp_password FROM email_config WHERE id = 1')
            row = cursor.fetchone()
            old_password = row['smtp_password'] if row else ''
            data['smtp_password'] = old_password

        cursor.execute('''
            UPDATE email_config SET
                smtp_host = %s,
                smtp_port = %s,
                smtp_user = %s,
                smtp_password = %s,
                sender_name = %s,
                recipients = %s,
                enabled = %s
            WHERE id = 1
        ''', (
            data.get('smtp_host', 'smtp.qq.com'),
            data.get('smtp_port', 465),
            data.get('smtp_user', ''),
            data.get('smtp_password', ''),
            data.get('sender_name', '硬件监控系统'),
            json.dumps(data.get('recipients', [])),
            1 if data.get('enabled') else 0
        ))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': '邮件配置已更新'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/email-config/test', methods=['POST'])
@login_required
def test_email_config():
    """测试邮件配置（发送测试邮件）"""
    try:
        data = request.json

        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = data.get('smtp_host', 'smtp.qq.com')
        smtp_port = data.get('smtp_port', 465)
        smtp_user = data.get('smtp_user', '')
        smtp_password = data.get('smtp_password', '')
        sender_name = data.get('sender_name', '硬件监控系统')
        test_recipient = data.get('test_recipient', '')

        if not smtp_user or not smtp_password or not test_recipient:
            return jsonify({'error': '请填写完整的SMTP配置和测试收件人'}), 400

        # 构建测试邮件
        html_body = f'''
        <html><body style="font-family:Microsoft YaHei,Arial,sans-serif;">
        <h2 style="color:#38a169;">【邮件配置测试】</h2>
        <p>这是一封来自硬件监控系统的测试邮件。</p>
        <p>如果您收到此邮件，说明SMTP配置正确。</p>
        <p style="color:#718096; margin-top:20px;">发送时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </body></html>
        '''

        msg = MIMEMultipart('alternative')
        msg['Subject'] = '【测试邮件】硬件监控系统配置测试'
        msg['From'] = f'{sender_name} <{smtp_user}>'
        msg['To'] = test_recipient
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        # 发送邮件
        server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [test_recipient], msg.as_string())
        server.quit()

        return jsonify({'status': 'success', 'message': '测试邮件发送成功'})

    except smtplib.SMTPAuthenticationError:
        return jsonify({'error': 'SMTP认证失败，请检查用户名和密码'}), 400
    except smtplib.SMTPConnectError:
        return jsonify({'error': '无法连接到SMTP服务器，请检查主机和端口'}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'邮件发送失败: {str(e)}'}), 500


@app.route('/api/alert-settings', methods=['GET'])
@login_required
def get_alert_settings():
    """获取告警设置"""
    try:
        conn = get_db_readonly()  # 只读查询使用只读连接
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM alert_settings WHERE id = 1')
        row = cursor.fetchone()
        conn.close()

        if row:
            return jsonify({'status': 'success', 'data': dict(row)})
        else:
            return jsonify({'status': 'success', 'data': {
                'monitor_cpu': 1,
                'monitor_gpu': 1,
                'monitor_memory': 1,
                'monitor_disk': 1,
                'monitor_network': 0,
                'monitor_motherboard': 0,
                'monitor_bios': 0
            }})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/alert-settings', methods=['PUT'])
@login_required
def update_alert_settings():
    """更新告警设置"""
    try:
        data = request.json

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE alert_settings SET
                monitor_cpu = %s,
                monitor_gpu = %s,
                monitor_memory = %s,
                monitor_disk = %s,
                monitor_network = %s,
                monitor_motherboard = %s,
                monitor_bios = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (
            1 if data.get('monitor_cpu') else 0,
            1 if data.get('monitor_gpu') else 0,
            1 if data.get('monitor_memory') else 0,
            1 if data.get('monitor_disk') else 0,
            1 if data.get('monitor_network') else 0,
            1 if data.get('monitor_motherboard') else 0,
            1 if data.get('monitor_bios') else 0
        ))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': '告警设置已更新'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['GET'])
@login_required
def get_collect_config():
    """获取采集配置"""
    return jsonify({
        'status': 'success',
        'data': {
            'max_workers': COLLECT_CONFIG['max_workers'],
            'timeout': COLLECT_CONFIG['timeout'],
            'retry_times': COLLECT_CONFIG['retry_times']
        }
    })


if __name__ == '__main__':
    # 初始化数据库连接池
    init_db_pool()
    # 初始化表结构
    init_tables()
    
    print("=" * 60)
    print("硬件监控系统服务端启动")
    print("访问地址: http://localhost:5000")
    print(f"并发配置: {COLLECT_CONFIG['max_workers']} workers, {COLLECT_CONFIG['timeout']}s timeout")
    print("=" * 60)

    try:
        # 生产环境: 使用waitress WSGI服务器(支持高并发,默认20线程)
        from waitress import serve
        print("使用 Waitress WSGI 服务器(生产模式)")
        serve(app, host='0.0.0.0', port=5000, threads=20, connection_limit=2000)
    except ImportError:
        # 开发环境: 使用Flask内置服务器
        print("Waitress未安装,使用Flask内置服务器(开发模式)")
        print("提示: pip install waitress 以启用高并发支持")
        app.run(host='0.0.0.0', port=5000, debug=True)
