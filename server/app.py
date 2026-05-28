"""
硬件监控系统服务端 - HwMonServer
Flask Web应用,提供API和Web管理界面
支持高并发采集(1000+客户端)
使用MySQL数据库支持高并发
"""

import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta

# 东八区固定时区偏移（确保所有时间戳使用 UTC+8，避免系统时区不一致问题）
TZ_CST = timezone(timedelta(hours=8), name='CST')
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
from ai_analyzer import analyze_process_alert, test_ai_connection

app = Flask(__name__)
CORS(app)

# 加载配置文件
import secrets

def load_config():
    """加载配置文件（从exe同级目录加载，不打包进exe）"""
    # 获取配置文件路径
    if getattr(sys, 'frozen', False):
        # PyInstaller打包后：从exe所在目录加载config.json
        base_path = os.path.dirname(sys.executable)
    else:
        # 开发环境的路径
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    config_file = os.path.join(base_path, 'config.json')
    
    # 默认配置（仅作为fallback，不应包含真实密码）
    default_config = {
        'database': {
            'host': 'localhost',
            'port': 3306,
            'user': 'root',
            'password': '',  # 空密码，必须通过config.json或环境变量配置
            'database': 'hwmon',
            'charset': 'utf8mb4'
        },
        'login': {
            'username': 'admin',
            'password': ''  # 空密码，必须配置
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
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # 合并默认配置
            for key in default_config:
                if key not in config:
                    config[key] = default_config[key]
            return config
    except Exception as e:
        print(f"警告: 无法加载配置文件 {config_file}: {e}")
        print("使用默认配置（请注意：默认配置不包含有效密码，请创建config.json）")
        return default_config

CONFIG = load_config()

# Session密钥 - 优先从环境变量读取，否则生成随机密钥
app.secret_key = os.environ.get('SECRET_KEY') or CONFIG.get('secret_key') or secrets.token_hex(32)

# 登录配置 - 优先从环境变量读取
LOGIN_CONFIG = {
    'username': os.environ.get('LOGIN_USERNAME') or CONFIG.get('login', {}).get('username', 'admin'),
    'password': os.environ.get('LOGIN_PASSWORD') or CONFIG.get('login', {}).get('password', '')
}

# 检查是否配置了有效密码
if not LOGIN_CONFIG['password']:
    print("⚠️  警告: 未配置登录密码！请设置 LOGIN_PASSWORD 环境变量或在 config.json 中配置")

# MySQL数据库配置（优先从环境变量读取）
db_config = CONFIG.get('database', {})
MYSQL_CONFIG = {
    'host': os.environ.get('DB_HOST') or db_config.get('host', 'localhost'),
    'port': int(os.environ.get('DB_PORT') or db_config.get('port', 3306)),
    'user': os.environ.get('DB_USER') or db_config.get('user', 'root'),
    'password': os.environ.get('DB_PASSWORD') or db_config.get('password', ''),
    'database': os.environ.get('DB_NAME') or db_config.get('database', 'hwmon'),
    'charset': os.environ.get('DB_CHARSET') or db_config.get('charset', 'utf8mb4'),
    'cursorclass': pymysql.cursors.DictCursor,
    'init_command': "SET time_zone='+08:00', innodb_lock_wait_timeout=10",
    'connect_timeout': 10,
    'read_timeout': 30,
    'write_timeout': 30
}

# 检查数据库配置
if not MYSQL_CONFIG['password']:
    print("⚠️  警告: 未配置数据库密码！请设置 DB_PASSWORD 环境变量或在 config.json 中配置")

# 数据库连接池
db_pool = None

# 并发采集配置（从配置文件读取）
collect_config = CONFIG.get('collect', {})
COLLECT_CONFIG = {
    'max_workers': collect_config.get('max_workers', 50),
    'timeout': collect_config.get('timeout', 15),
    'retry_times': collect_config.get('retry_times', 0),
}

# 硬件变更检测线程池（异步执行，不阻塞主流程）
hw_detection_executor = ThreadPoolExecutor(
    max_workers=20,  # 20个并发检测线程
    thread_name_prefix='hw_detect'
)


def init_db_pool():
    """初始化数据库连接池（优化为支持1500+客户端）"""
    global db_pool
    db_pool = PooledDB(
        creator=pymysql,
        maxconnections=300,     # 支持300并发（1500客户端/5分钟均匀分布）
        mincached=30,           # 预创建30个空闲连接
        maxcached=80,           # 最多缓存80个空闲连接
        maxusage=300,           # 每个连接使用300次后回收（更频繁刷新）
        blocking=False,         # 连接池满时不阻塞，快速失败
        ping=1,                 # 连接时检查连接是否可用
        **MYSQL_CONFIG
    )
    print("MySQL连接池初始化成功（配置：max=300, min=30, cache=80）")
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


from contextlib import contextmanager

@contextmanager
def get_db_safe():
    """安全的数据库连接上下文管理器（自动关闭连接）"""
    conn = None
    try:
        conn = get_db()
        yield conn
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@contextmanager
def get_db_readonly_safe():
    """安全的只读数据库连接上下文管理器（自动关闭连接）"""
    conn = None
    try:
        conn = get_db_readonly()
        yield conn
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


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
                INDEX idx_last_report (last_report),
                INDEX idx_last_report_desc (last_report DESC)
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
                INDEX idx_timestamp (timestamp),
                INDEX idx_client_timestamp (client_id, timestamp DESC)
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
                INDEX idx_created_at (created_at),
                INDEX idx_created_resolved (created_at DESC, resolved)
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
                alert_enabled TINYINT DEFAULT 1 COMMENT '告警开关：1=开启告警记录，0=关闭告警',
                email_enabled TINYINT DEFAULT 0 COMMENT '邮件开关：1=开启邮件通知，0=关闭邮件',
                monitor_cpu TINYINT DEFAULT 1,
                monitor_gpu TINYINT DEFAULT 1,
                monitor_memory TINYINT DEFAULT 1,
                monitor_disk TINYINT DEFAULT 1,
                monitor_network TINYINT DEFAULT 0,
                monitor_motherboard TINYINT DEFAULT 0,
                monitor_bios TINYINT DEFAULT 0,
                monitor_temperature TINYINT DEFAULT 0 COMMENT '监控温度传感器变化',
                monitor_fan TINYINT DEFAULT 0 COMMENT '监控风扇传感器变化',
                monitor_voltage TINYINT DEFAULT 0 COMMENT '监控电压传感器变化',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        cursor.execute('INSERT IGNORE INTO alert_settings (id) VALUES (1)')

        # 数据库迁移：为已存在的表添加新字段
        try:
            # 检查 alert_enabled 字段是否存在
            cursor.execute("SHOW COLUMNS FROM alert_settings LIKE 'alert_enabled'")
            if not cursor.fetchone():
                print('[INFO] 正在迁移数据库：添加 alert_enabled 字段')
                cursor.execute("ALTER TABLE alert_settings ADD COLUMN alert_enabled TINYINT DEFAULT 1 COMMENT '告警开关' AFTER id")
            
            # 检查 email_enabled 字段是否存在
            cursor.execute("SHOW COLUMNS FROM alert_settings LIKE 'email_enabled'")
            if not cursor.fetchone():
                print('[INFO] 正在迁移数据库：添加 email_enabled 字段')
                cursor.execute("ALTER TABLE alert_settings ADD COLUMN email_enabled TINYINT DEFAULT 0 COMMENT '邮件开关' AFTER alert_enabled")

            # 检查 monitor_temperature 字段是否存在
            cursor.execute("SHOW COLUMNS FROM alert_settings LIKE 'monitor_temperature'")
            if not cursor.fetchone():
                print('[INFO] 正在迁移数据库：添加 monitor_temperature 字段')
                cursor.execute("ALTER TABLE alert_settings ADD COLUMN monitor_temperature TINYINT DEFAULT 0 COMMENT '监控温度传感器变化'")

            # 检查 monitor_fan 字段是否存在
            cursor.execute("SHOW COLUMNS FROM alert_settings LIKE 'monitor_fan'")
            if not cursor.fetchone():
                print('[INFO] 正在迁移数据库：添加 monitor_fan 字段')
                cursor.execute("ALTER TABLE alert_settings ADD COLUMN monitor_fan TINYINT DEFAULT 0 COMMENT '监控风扇传感器变化'")

            # 检查 monitor_voltage 字段是否存在
            cursor.execute("SHOW COLUMNS FROM alert_settings LIKE 'monitor_voltage'")
            if not cursor.fetchone():
                print('[INFO] 正在迁移数据库：添加 monitor_voltage 字段')
                cursor.execute("ALTER TABLE alert_settings ADD COLUMN monitor_voltage TINYINT DEFAULT 0 COMMENT '监控电压传感器变化'")

            conn.commit()
            print('[INFO] 数据库字段迁移完成')
        except Exception as e:
            print(f'[WARN] 数据库字段迁移失败: {e}')
            # 不中断启动，继续运行

        # 数据库迁移：添加复合索引
        try:
            # 检查 hardware_history 表的复合索引
            cursor.execute("SHOW INDEX FROM hardware_history WHERE Key_name = 'idx_client_timestamp'")
            if not cursor.fetchone():
                print('[INFO] 正在添加硬件历史表复合索引')
                cursor.execute("ALTER TABLE hardware_history ADD INDEX idx_client_timestamp (client_id, timestamp DESC)")
            
            # 检查 clients 表的降序索引
            cursor.execute("SHOW INDEX FROM clients WHERE Key_name = 'idx_last_report_desc'")
            if not cursor.fetchone():
                print('[INFO] 正在添加客户端表降序索引')
                cursor.execute("ALTER TABLE clients ADD INDEX idx_last_report_desc (last_report DESC)")
            
            # 检查 alert_records 表的复合索引
            cursor.execute("SHOW INDEX FROM alert_records WHERE Key_name = 'idx_created_resolved'")
            if not cursor.fetchone():
                print('[INFO] 正在添加告警记录表复合索引')
                cursor.execute("ALTER TABLE alert_records ADD INDEX idx_created_resolved (created_at DESC, resolved)")
            
            conn.commit()
            print('[INFO] 数据库索引迁移完成')
        except Exception as e:
            print(f'[WARN] 数据库索引迁移失败: {e}')

        # 创建进程告警记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS process_alert_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id VARCHAR(255) NOT NULL,
                hostname VARCHAR(255),
                local_ip VARCHAR(45),
                alert_data LONGTEXT NOT NULL COMMENT '完整告警 JSON',
                alert_count INT DEFAULT 1 COMMENT '本次告警包含的进程数量',
                resolved TINYINT DEFAULT 0,
                ai_analyzed TINYINT DEFAULT 0 COMMENT '是否已进行 AI 研判',
                ai_result LONGTEXT COMMENT 'AI 研判结果',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_pa_client_id (client_id),
                INDEX idx_pa_resolved (resolved),
                INDEX idx_pa_created_at (created_at DESC),
                INDEX idx_pa_ai_analyzed (ai_analyzed)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # 创建 AI 配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_config (
                id INT PRIMARY KEY,
                enabled TINYINT DEFAULT 0 COMMENT 'AI 研判总开关',
                api_base_url VARCHAR(500) DEFAULT 'https://api.openai.com/v1' COMMENT 'API 基础地址',
                api_key VARCHAR(500) DEFAULT '' COMMENT 'API Key',
                model VARCHAR(100) DEFAULT 'gpt-4o-mini' COMMENT '模型名称',
                max_tokens INT DEFAULT 2000 COMMENT '最大输出 token 数',
                temperature DECIMAL(3,2) DEFAULT 0.30 COMMENT '温度参数',
                system_prompt TEXT COMMENT '系统提示词',
                auto_analyze TINYINT DEFAULT 1 COMMENT '收到告警后自动触发 AI 分析',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        cursor.execute('INSERT IGNORE INTO ai_config (id) VALUES (1)')

        # 创建 AI 监控主机表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_monitored_hosts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                client_id VARCHAR(255) NOT NULL UNIQUE,
                hostname VARCHAR(255),
                description TEXT,
                enabled TINYINT DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_amh_client_id (client_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # 创建主机探测目标表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS probe_targets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL COMMENT '主机名称',
                host VARCHAR(255) NOT NULL COMMENT 'IP或域名',
                port INT DEFAULT 80 COMMENT '探测端口',
                protocol VARCHAR(10) DEFAULT 'http' COMMENT 'http/https/tcp',
                path VARCHAR(500) DEFAULT '/' COMMENT 'HTTP路径',
                enabled TINYINT DEFAULT 1,
                description TEXT,
                last_status VARCHAR(20) DEFAULT 'unknown' COMMENT 'unknown/online/offline',
                last_probe_time DATETIME,
                last_response_time INT COMMENT '响应时间ms',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_pt_enabled (enabled)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # 创建主机探测告警表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS probe_alerts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                target_id INT NOT NULL,
                target_name VARCHAR(255),
                target_host VARCHAR(255),
                alert_type VARCHAR(50) DEFAULT 'offline' COMMENT 'offline/timeout/slow',
                status_code INT COMMENT 'HTTP状态码',
                response_time INT COMMENT '响应时间ms',
                error_message TEXT,
                resolved TINYINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_pa_target (target_id),
                INDEX idx_pa_resolved (resolved),
                INDEX idx_pa_created (created_at DESC),
                FOREIGN KEY (target_id) REFERENCES probe_targets(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

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
            'monitor_bios': 0,
            'monitor_temperature': 0,
            'monitor_fan': 0,
            'monitor_voltage': 0
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

    # 温度传感器对比 - 对比传感器列表和名称
    if alert_settings.get('monitor_temperature', 0):
        old_temp_raw = baseline_snapshots.get('temperature', '')
        new_temp = new_hardware.get('temperature', {})
        if old_temp_raw and new_temp:
            try:
                old_temps = json.loads(old_temp_raw)
            except (json.JSONDecodeError, TypeError):
                old_temps = {}
            old_sensors = old_temps.get('sensors', []) if isinstance(old_temps, dict) else []
            new_sensors = new_temp.get('sensors', [])
            if old_sensors and new_sensors:
                old_names = sorted([s.get('name', '') for s in old_sensors])
                new_names = sorted([s.get('name', '') for s in new_sensors])
                if old_names != new_names:
                    changes.append({
                        'type': 'temperature',
                        'label': '温度传感器',
                        'old': ', '.join(old_names) if old_names else '未知',
                        'new': ', '.join(new_names) if new_names else '未知'
                    })

    # 风扇传感器对比 - 对比传感器列表和名称
    if alert_settings.get('monitor_fan', 0):
        old_fan_raw = baseline_snapshots.get('fan', '')
        new_fan = new_hardware.get('fan', {})
        if old_fan_raw and new_fan:
            try:
                old_fans = json.loads(old_fan_raw)
            except (json.JSONDecodeError, TypeError):
                old_fans = {}
            old_sensors = old_fans.get('sensors', []) if isinstance(old_fans, dict) else []
            new_sensors = new_fan.get('sensors', [])
            if old_sensors and new_sensors:
                old_names = sorted([s.get('name', '') for s in old_sensors])
                new_names = sorted([s.get('name', '') for s in new_sensors])
                if old_names != new_names:
                    changes.append({
                        'type': 'fan',
                        'label': '风扇传感器',
                        'old': ', '.join(old_names) if old_names else '未知',
                        'new': ', '.join(new_names) if new_names else '未知'
                    })

    # 电压传感器对比 - 对比传感器列表和名称
    if alert_settings.get('monitor_voltage', 0):
        old_volt_raw = baseline_snapshots.get('voltage', '')
        new_volt = new_hardware.get('voltage', {})
        if old_volt_raw and new_volt:
            try:
                old_volts = json.loads(old_volt_raw)
            except (json.JSONDecodeError, TypeError):
                old_volts = {}
            old_sensors = old_volts.get('sensors', []) if isinstance(old_volts, dict) else []
            new_sensors = new_volt.get('sensors', [])
            if old_sensors and new_sensors:
                old_names = sorted([s.get('name', '') for s in old_sensors])
                new_names = sorted([s.get('name', '') for s in new_sensors])
                if old_names != new_names:
                    changes.append({
                        'type': 'voltage',
                        'label': '电压传感器',
                        'old': ', '.join(old_names) if old_names else '未知',
                        'new': ', '.join(new_names) if new_names else '未知'
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
            <tr><td style="padding:5px 10px;font-weight:bold;">变更时间:</td><td style="padding:5px 10px;">{datetime.now(TZ_CST).strftime("%Y-%m-%d %H:%M:%S")}</td></tr>
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
    """检查硬件变更（同步版本，保留以兼容）"""
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
                'bios': json.dumps(hardware_info.get('bios', {}), ensure_ascii=False) if hardware_info.get('bios') else '',
                'temperature': json.dumps(hardware_info.get('temperature', {}), ensure_ascii=False) if hardware_info.get('temperature') else '',
                'fan': json.dumps(hardware_info.get('fan', {}), ensure_ascii=False) if hardware_info.get('fan') else '',
                'voltage': json.dumps(hardware_info.get('voltage', {}), ensure_ascii=False) if hardware_info.get('voltage') else ''
            }

            changes = compare_hardware(baseline_snapshots, hardware_info, alert_settings)

            if changes:
                # 检查告警开关
                if alert_settings.get('alert_enabled', 1):
                    # 记录告警到数据库
                    alert_detail = json.dumps(changes, ensure_ascii=False)
                    cursor.execute('''
                        INSERT INTO alert_records (client_id, alert_type, alert_detail)
                        VALUES (%s, %s, %s)
                    ''', (client_id, 'hardware_change', alert_detail))
                    conn.commit()

                    print(f'[ALERT] 客户端 {client_id} 检测到硬件变更: {len(changes)} 项')
                else:
                    print(f'[INFO] 客户端 {client_id} 检测到硬件变更，但告警已关闭，未记录')

                # 检查邮件开关（独立于告警开关）
                if alert_settings.get('email_enabled', 0):
                    try:
                        email_sent = send_alert_email(client_id, hostname, local_ip, changes)
                        if email_sent:
                            print(f'[INFO] 已向管理员发送告警邮件')
                        else:
                            print(f'[WARN] 告警邮件发送失败（可能未配置或配置错误）')
                    except Exception as e:
                        print(f'[WARN] 发送邮件异常: {e}')
                else:
                    print(f'[INFO] 邮件通知已关闭，未发送邮件')
    except Exception as e:
        # 回滚事务
        try:
            conn.rollback()
        except:
            pass
        raise e


def _check_hardware_changes_async(client_id, hostname, local_ip, hardware_info,
                                   cpu_info, gpu_info, mem_info, disk_info):
    """异步硬件变更检测（独立线程，自己管理数据库连接）"""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # 复用原有逻辑
        _check_hardware_changes(cursor, conn, client_id, hostname, local_ip, hardware_info,
                                cpu_info, gpu_info, mem_info, disk_info)
    except Exception as e:
        print(f'[WARN] 异步硬件检测失败 {client_id}: {e}')
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


# =================================================================


def collect_single_client(client_id, local_ip):
    """采集单个客户端(用于并发执行) - 使用全局配置"""
    return collect_single_client_with_config(client_id, local_ip, COLLECT_CONFIG)


def collect_single_client_with_config(client_id, local_ip, config):
    """采集单个客户端(使用指定配置，避免全局状态污染)"""
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
            timeout=config['timeout']
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


@app.before_request
def _ensure_tables():
    """确保数据库表存在（首次请求时自动创建）"""
    if not hasattr(app, '_tables_initialized'):
        try:
            init_tables()
        except Exception:
            pass
        app._tables_initialized = True


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
        current_time = datetime.now(TZ_CST).strftime('%Y-%m-%d %H:%M:%S')
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

        # 【优化】移除实时DELETE，改为后台定时任务清理（见下方 cleanup_old_records 函数）
        # 这样每次上报不会执行耗时的DELETE操作，大幅提升性能
        conn.commit()  # 提交硬件历史相关操作

        # 【优化】步骤3: 硬件变更检测（异步执行，不阻塞主流程）
        # 提交到线程池异步执行，立即返回，不等待结果
        hw_detection_executor.submit(
            _check_hardware_changes_async,
            client_id, hostname, local_ip, hardware_info,
            cpu_info, gpu_info, mem_info, disk_info
        )

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

        # 验证参数范围
        max_workers = max(1, min(max_workers, 200))  # 限制在1-200之间
        timeout = max(5, min(timeout, 60))  # 限制在5-60秒之间

        conn = get_db_readonly()  # 只读查询使用只读连接
        cursor = conn.cursor()

        cursor.execute('SELECT client_id, local_ip FROM clients')
        clients = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if not clients:
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

        # 创建局部配置副本（避免修改全局配置）
        local_collect_config = {
            'max_workers': max_workers,
            'timeout': timeout,
            'retry_times': COLLECT_CONFIG['retry_times']
        }

        # 使用线程池并发采集
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有采集任务
            futures = {
                executor.submit(collect_single_client_with_config, c['client_id'], c['local_ip'], local_collect_config): c['client_id']
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

    except pymysql.err.IntegrityError:
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
            download_name=f'hardware_report_{datetime.now(TZ_CST).strftime("%Y%m%d_%H%M%S")}.csv'
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
            download_name=f'hardware_report_{datetime.now(TZ_CST).strftime("%Y%m%d_%H%M%S")}.json'
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
                   'CPU', '内存', '硬盘', '显卡', '运行时间', '温度(最高)', '风扇(最高)', '电压']
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
            uptime_str = '-'
            temp_str = '-'
            fan_str = '-'
            voltage_str = '-'

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

                # 运行时间
                if hardware.get('uptime') and not hardware['uptime'].get('error'):
                    uptime_str = hardware['uptime'].get('uptime_human', '-')

                # 温度（取最高值）
                if hardware.get('temperature') and hardware['temperature'].get('sensors'):
                    temps = hardware['temperature']['sensors']
                    if temps:
                        max_temp = max(s.get('value', 0) for s in temps)
                        temp_str = f"{max_temp}°C"

                # 风扇（取最高转速）
                if hardware.get('fan') and hardware['fan'].get('sensors'):
                    fans = hardware['fan']['sensors']
                    if fans:
                        max_fan = max(s.get('value', 0) for s in fans)
                        fan_str = f"{max_fan} RPM"

                # 电压
                if hardware.get('voltage') and hardware['voltage'].get('sensors'):
                    voltages = hardware['voltage']['sensors']
                    if voltages:
                        voltage_str = ' | '.join([f"{s.get('name','?')}:{s.get('value',0)}V" for s in voltages[:3]])

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
            ws.cell(row=row_idx, column=11, value=uptime_str)
            ws.cell(row=row_idx, column=12, value=temp_str)
            ws.cell(row=row_idx, column=13, value=fan_str)
            ws.cell(row=row_idx, column=14, value=voltage_str)

        # 调整列宽
        col_widths = [15, 20, 16, 15, 22, 22, 40, 12, 40, 30, 20, 15, 15, 30]
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
            download_name=f'hardware_report_{datetime.now(TZ_CST).strftime("%Y%m%d_%H%M%S")}.xlsx'
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

        # 输入验证
        if not client_ids:
            return jsonify({'error': '请选择要操作的客户端'}), 400
        
        # 限制批量操作数量，防止SQL过长
        MAX_BATCH_SIZE = 1000
        if len(client_ids) > MAX_BATCH_SIZE:
            return jsonify({'error': f'批量操作数量不能超过{MAX_BATCH_SIZE}个'}), 400
        
        # 验证client_ids格式（只允许字母、数字、下划线、连字符）
        import re
        for cid in client_ids:
            if not re.match(r'^[a-zA-Z0-9_-]+$', str(cid)):
                return jsonify({'error': f'无效的客户端ID: {cid}'}), 400

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
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 验证客户端存在
        cursor.execute('SELECT client_id FROM clients WHERE client_id = %s', (client_id,))
        if not cursor.fetchone():
            return jsonify({'error': '客户端不存在'}), 404

        # 获取最新的硬件报告
        cursor.execute('''
            SELECT report_data FROM hardware_reports
            WHERE client_id = %s ORDER BY timestamp DESC LIMIT 1
        ''', (client_id,))
        report = cursor.fetchone()

        if not report:
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

        return jsonify({'status': 'success', 'message': '基准已更新'})

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


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
        resolved = request.args.get('resolved')

        conn = get_db()
        cursor = conn.cursor()

        # 检查表是否存在
        try:
            cursor.execute("SELECT 1 FROM alert_records LIMIT 1")
        except Exception:
            conn.rollback()
            try:
                init_tables()
            except Exception:
                pass
            conn.close()
            return jsonify({'status': 'success', 'data': [], 'pagination': {'page': 1, 'per_page': per_page, 'total': 0, 'pages': 0}})

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
        count_query = query.replace('SELECT a.*, c.hostname, c.local_ip', 'SELECT COUNT(*) as total')
        cursor.execute(count_query, params)
        total = cursor.fetchone()['total']

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
        <p style="color:#718096; margin-top:20px;">发送时间: {datetime.now(TZ_CST).strftime("%Y-%m-%d %H:%M:%S")}</p>
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
        conn = get_db()  # 使用普通连接
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM alert_settings WHERE id = 1')
        row = cursor.fetchone()
        conn.close()

        if row:
            return jsonify({'status': 'success', 'data': dict(row)})
        else:
            return jsonify({'status': 'success', 'data': {
                'alert_enabled': 1,
                'email_enabled': 0,
                'monitor_cpu': 1,
                'monitor_gpu': 1,
                'monitor_memory': 1,
                'monitor_disk': 1,
                'monitor_network': 0,
                'monitor_motherboard': 0,
                'monitor_bios': 0,
                'monitor_temperature': 0,
                'monitor_fan': 0,
                'monitor_voltage': 0
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
                alert_enabled = %s,
                email_enabled = %s,
                monitor_cpu = %s,
                monitor_gpu = %s,
                monitor_memory = %s,
                monitor_disk = %s,
                monitor_network = %s,
                monitor_motherboard = %s,
                monitor_bios = %s,
                monitor_temperature = %s,
                monitor_fan = %s,
                monitor_voltage = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (
            1 if data.get('alert_enabled') else 0,
            1 if data.get('email_enabled') else 0,
            1 if data.get('monitor_cpu') else 0,
            1 if data.get('monitor_gpu') else 0,
            1 if data.get('monitor_memory') else 0,
            1 if data.get('monitor_disk') else 0,
            1 if data.get('monitor_network') else 0,
            1 if data.get('monitor_motherboard') else 0,
            1 if data.get('monitor_bios') else 0,
            1 if data.get('monitor_temperature') else 0,
            1 if data.get('monitor_fan') else 0,
            1 if data.get('monitor_voltage') else 0
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


# =================================================================
# 仪表盘统计 API
# =================================================================

@app.route('/api/dashboard', methods=['GET'])
@login_required
def get_dashboard():
    """获取仪表盘统计数据"""
    try:
        conn = get_db_readonly()
        cursor = conn.cursor()

        # 客户端总数
        cursor.execute('SELECT COUNT(*) as total FROM clients')
        total_clients = cursor.fetchone()['total']

        # 在线客户端（24小时内有上报）
        cursor.execute("SELECT COUNT(*) as online FROM clients WHERE last_report >= DATE_SUB(NOW(), INTERVAL 24 HOUR)")
        online_clients = cursor.fetchone()['online']

        # 分组数量
        cursor.execute('SELECT COUNT(*) as total FROM `groups`')
        total_groups = cursor.fetchone()['total']

        # 未解决告警数（硬件变更）
        cursor.execute('SELECT COUNT(*) as total FROM alert_records WHERE resolved = 0')
        unresolved_alerts = cursor.fetchone()['total']

        # 进程告警数
        cursor.execute('SELECT COUNT(*) as total FROM process_alert_records WHERE resolved = 0')
        process_alerts = cursor.fetchone()['total']

        # 探测告警数
        cursor.execute('SELECT COUNT(*) as total FROM probe_alerts WHERE resolved = 0')
        probe_alerts = cursor.fetchone()['total']

        # AI 已分析数
        cursor.execute('SELECT COUNT(*) as total FROM process_alert_records WHERE ai_analyzed = 1')
        ai_analyzed = cursor.fetchone()['total']

        # 最近 10 条上报记录
        cursor.execute('''
            SELECT c.client_id, c.hostname, c.local_ip, c.last_report, g.name as group_name
            FROM clients c
            LEFT JOIN `groups` g ON c.group_id = g.id
            ORDER BY c.last_report DESC
            LIMIT 10
        ''')
        recent_reports = [dict(row) for row in cursor.fetchall()]

        # 分组统计
        cursor.execute('''
            SELECT g.name, g.id, COUNT(c.id) as client_count
            FROM `groups` g
            LEFT JOIN clients c ON g.id = c.group_id
            GROUP BY g.id
            ORDER BY g.name
        ''')
        group_stats = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return jsonify({
            'status': 'success',
            'data': {
                'total_clients': total_clients,
                'online_clients': online_clients,
                'offline_clients': total_clients - online_clients,
                'total_groups': total_groups,
                'unresolved_alerts': unresolved_alerts,
                'process_alerts': process_alerts,
                'ai_analyzed': ai_analyzed,
                'probe_alerts': probe_alerts,
                'recent_reports': recent_reports,
                'group_stats': group_stats,
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =================================================================
# 进程告警 API
# =================================================================

@app.route('/api/process-alert', methods=['POST'])
def receive_process_alert():
    """接收客户端进程告警（无需登录，客户端上报用）"""
    try:
        data = request.json
        client_id = data.get('client_id')
        hostname = data.get('hostname', '')
        local_ip = data.get('local_ip', '')
        alerts = data.get('alerts', [])
        system_summary = data.get('system_summary', {})
        timestamp = data.get('timestamp', '')

        if not client_id:
            return jsonify({'error': '缺少 client_id'}), 400

        if not alerts:
            return jsonify({'error': '告警列表为空'}), 400

        conn = get_db()
        cursor = conn.cursor()

        # 确保客户端存在
        current_time = datetime.now(TZ_CST).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO clients (client_id, hostname, local_ip, last_report)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                hostname = VALUES(hostname),
                local_ip = VALUES(local_ip),
                last_report = VALUES(last_report)
        ''', (client_id, hostname, local_ip, current_time))

        # 保存进程告警
        alert_data = json.dumps({
            "alerts": alerts,
            "system_summary": system_summary,
            "timestamp": timestamp
        }, ensure_ascii=False)

        cursor.execute('''
            INSERT INTO process_alert_records (client_id, hostname, local_ip, alert_data, alert_count)
            VALUES (%s, %s, %s, %s, %s)
        ''', (client_id, hostname, local_ip, alert_data, len(alerts)))

        alert_id = cursor.lastrowid
        conn.commit()

        # 检查是否需要触发 AI 分析（异步）
        def _async_ai_analyze(aid, cid, adata):
            """异步执行 AI 分析"""
            try:
                ai_conn = get_db()
                ai_cursor = ai_conn.cursor()

                # 检查该主机是否在 AI 监控列表中
                ai_cursor.execute('SELECT id FROM ai_monitored_hosts WHERE client_id = %s AND enabled = 1', (cid,))
                if not ai_cursor.fetchone():
                    ai_conn.close()
                    return

                # 获取 AI 配置
                ai_cursor.execute('SELECT * FROM ai_config WHERE id = 1')
                ai_cfg = ai_cursor.fetchone()
                if not ai_cfg or not ai_cfg.get('enabled') or not ai_cfg.get('auto_analyze'):
                    ai_conn.close()
                    return

                ai_cfg = dict(ai_cfg)

                # 调用 AI 分析
                alert_json = json.loads(adata)
                result = analyze_process_alert(alert_json, ai_cfg)

                if result and not result.get('error'):
                    # 保存分析结果
                    ai_cursor.execute('''
                        UPDATE process_alert_records SET ai_analyzed = 1, ai_result = %s WHERE id = %s
                    ''', (json.dumps(result, ensure_ascii=False), aid))
                    ai_conn.commit()
                elif result and result.get('error'):
                    # 保存错误信息
                    ai_cursor.execute('''
                        UPDATE process_alert_records SET ai_analyzed = 1, ai_result = %s WHERE id = %s
                    ''', (json.dumps(result, ensure_ascii=False), aid))
                    ai_conn.commit()

                ai_conn.close()
            except Exception as e:
                print(f'[WARN] AI 异步分析失败 (alert_id={aid}): {e}')

        # 提交到线程池异步执行
        hw_detection_executor.submit(_async_ai_analyze, alert_id, client_id, alert_data)

        conn.close()
        return jsonify({'status': 'success', 'message': '进程告警接收成功', 'alert_id': alert_id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/process-alerts', methods=['GET'])
@login_required
def get_process_alerts():
    """获取进程告警列表（支持分页、按主机筛选）"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        client_id = request.args.get('client_id')
        resolved = request.args.get('resolved')

        conn = get_db_readonly()
        cursor = conn.cursor()

        query = 'SELECT * FROM process_alert_records WHERE 1=1'
        count_query = 'SELECT COUNT(*) FROM process_alert_records WHERE 1=1'
        params = []

        if client_id:
            query += ' AND client_id = %s'
            count_query += ' AND client_id = %s'
            params.append(client_id)

        if resolved is not None:
            query += ' AND resolved = %s'
            count_query += ' AND resolved = %s'
            params.append(1 if resolved == 'true' else 0)

        # 获取总数
        cursor.execute(count_query, params)
        total = cursor.fetchone()['COUNT(*)']

        # 分页查询
        query += ' ORDER BY created_at DESC LIMIT %s OFFSET %s'
        cursor.execute(query, params + [per_page, (page - 1) * per_page])

        alerts = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            if row_dict.get('alert_data'):
                row_dict['alert_data'] = json.loads(row_dict['alert_data'])
            if row_dict.get('ai_result'):
                row_dict['ai_result'] = json.loads(row_dict['ai_result'])
            alerts.append(row_dict)

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


@app.route('/api/process-alerts/<int:alert_id>', methods=['PUT'])
@login_required
def resolve_process_alert(alert_id):
    """标记进程告警为已处理"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE process_alert_records SET resolved = 1 WHERE id = %s', (alert_id,))
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': '告警记录不存在'}), 404
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': '已标记为已处理'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/process-alerts/batch-resolve', methods=['PUT'])
@login_required
def batch_resolve_process_alerts():
    """批量标记进程告警为已处理"""
    try:
        data = request.json
        alert_ids = data.get('alert_ids', [])
        if not alert_ids:
            return jsonify({'error': '请选择要处理的告警'}), 400
        conn = get_db()
        cursor = conn.cursor()
        placeholders = ','.join(['%s' for _ in alert_ids])
        cursor.execute(f'UPDATE process_alert_records SET resolved = 1 WHERE id IN ({placeholders})', alert_ids)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'affected': affected})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/process-alerts/<int:alert_id>/reanalyze', methods=['POST'])
@login_required
def reanalyze_process_alert(alert_id):
    """手动触发单条告警的 AI 研判"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM process_alert_records WHERE id = %s', (alert_id,))
        alert = cursor.fetchone()
        if not alert:
            conn.close()
            return jsonify({'error': '告警记录不存在'}), 404

        # 获取 AI 配置
        cursor.execute('SELECT * FROM ai_config WHERE id = 1')
        ai_cfg = cursor.fetchone()
        if not ai_cfg or not ai_cfg.get('enabled'):
            conn.close()
            return jsonify({'error': 'AI 未启用'}), 400

        ai_cfg = dict(ai_cfg)
        alert_data = json.loads(alert['alert_data'])

        # 调用 AI 分析
        result = analyze_process_alert(alert_data, ai_cfg)

        if result:
            cursor.execute('''
                UPDATE process_alert_records SET ai_analyzed = 1, ai_result = %s WHERE id = %s
            ''', (json.dumps(result, ensure_ascii=False), alert_id))
            conn.commit()

        conn.close()
        return jsonify({'status': 'success', 'result': result})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =================================================================
# AI 配置 API
# =================================================================

@app.route('/api/ai/config', methods=['GET'])
@login_required
def get_ai_config():
    """获取 AI 配置（api_key 脱敏返回）"""
    try:
        conn = get_db_readonly()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM ai_config WHERE id = 1')
        row = cursor.fetchone()
        conn.close()
        if row:
            config = dict(row)
            if config.get('api_key'):
                key = config['api_key']
                if len(key) > 8:
                    config['api_key'] = key[:4] + '****' + key[-4:]
            # Decimal 字段需要转为 float 才能 JSON 序列化
            if 'temperature' in config:
                config['temperature'] = float(config['temperature'])
            return jsonify({'status': 'success', 'data': config})
        return jsonify({'status': 'success', 'data': {
            'enabled': 0, 'api_base_url': 'https://api.openai.com/v1',
            'api_key': '', 'model': 'gpt-4o-mini', 'max_tokens': 2000,
            'temperature': 0.3, 'system_prompt': '', 'auto_analyze': 1
        }})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/config', methods=['PUT'])
@login_required
def update_ai_config():
    """更新 AI 配置"""
    try:
        data = request.json
        conn = get_db()
        cursor = conn.cursor()

        # 如果 api_key 是脱敏的，保留原值
        if data.get('api_key') and '****' in data['api_key']:
            cursor.execute('SELECT api_key FROM ai_config WHERE id = 1')
            old = cursor.fetchone()
            data['api_key'] = old['api_key'] if old else ''

        cursor.execute('''
            UPDATE ai_config SET
                enabled = %s, api_base_url = %s, api_key = %s, model = %s,
                max_tokens = %s, temperature = %s, system_prompt = %s, auto_analyze = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (
            1 if data.get('enabled') else 0,
            data.get('api_base_url', 'https://api.openai.com/v1'),
            data.get('api_key', ''),
            data.get('model', 'gpt-4o-mini'),
            data.get('max_tokens', 2000),
            float(data.get('temperature', 0.3)),
            data.get('system_prompt', ''),
            1 if data.get('auto_analyze') else 0
        ))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'AI 配置已更新'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/config/test', methods=['POST'])
@login_required
def test_ai_config():
    """测试 AI 接口连通性"""
    try:
        data = request.json
        success, message = test_ai_connection(data)
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/config/models', methods=['POST'])
@login_required
def fetch_ai_models():
    """获取 AI 模型列表（OpenAI 兼容 /models 端点）"""
    try:
        data = request.json
        api_base_url = data.get('api_base_url', '').rstrip('/')
        api_key = data.get('api_key', '')
        if not api_base_url or not api_key:
            return jsonify({'error': '请填写 API 地址和 Key'}), 400

        url = f"{api_base_url}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        d = resp.json()
        models = [m.get('id', '') for m in d.get('data', []) if m.get('id')]
        return jsonify({'status': 'success', 'models': sorted(models)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =================================================================
# AI 监控主机管理 API
# =================================================================

@app.route('/api/ai/hosts', methods=['GET'])
@login_required
def get_ai_hosts():
    """获取 AI 监控主机列表"""
    try:
        conn = get_db_readonly()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM ai_monitored_hosts ORDER BY added_at DESC')
        hosts = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({'status': 'success', 'data': hosts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/hosts', methods=['POST'])
@login_required
def add_ai_host():
    """添加 AI 监控主机"""
    try:
        data = request.json
        client_id = data.get('client_id')
        if not client_id:
            return jsonify({'error': '请选择要添加的客户端'}), 400

        hostname = data.get('hostname', '')
        description = data.get('description', '')

        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO ai_monitored_hosts (client_id, hostname, description)
                VALUES (%s, %s, %s)
            ''', (client_id, hostname, description))
            conn.commit()
            host_id = cursor.lastrowid
            conn.close()
            return jsonify({'status': 'success', 'host_id': host_id})
        except pymysql.err.IntegrityError:
            conn.close()
            return jsonify({'error': '该主机已在监控列表中'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/hosts/<int:host_id>', methods=['DELETE'])
@login_required
def delete_ai_host(host_id):
    """移除 AI 监控主机"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM ai_monitored_hosts WHERE id = %s', (host_id,))
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': '主机不存在'}), 404
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': '已移除'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =================================================================
# 主机探测模块 API
# =================================================================

@app.route('/api/probe/targets', methods=['GET'])
@login_required
def get_probe_targets():
    """获取探测目标列表"""
    try:
        conn = get_db_readonly()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM probe_targets ORDER BY created_at DESC')
        targets = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({'status': 'success', 'data': targets})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/probe/targets', methods=['POST'])
@login_required
def add_probe_target():
    """添加探测目标"""
    try:
        data = request.json
        name = data.get('name', '').strip()
        host = data.get('host', '').strip()
        port = int(data.get('port', 80))
        protocol = data.get('protocol', 'http')
        path = data.get('path', '/')
        description = data.get('description', '')

        if not name or not host:
            return jsonify({'error': '名称和地址不能为空'}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO probe_targets (name, host, port, protocol, path, description)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (name, host, port, protocol, path, description))
        conn.commit()
        target_id = cursor.lastrowid
        conn.close()
        return jsonify({'status': 'success', 'target_id': target_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/probe/targets/<int:target_id>', methods=['PUT'])
@login_required
def update_probe_target(target_id):
    try:
        data = request.json
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''UPDATE probe_targets SET name=%s, host=%s, port=%s, protocol=%s, path=%s, description=%s, enabled=%s WHERE id=%s''',
            (data.get('name'), data.get('host'), int(data.get('port',80)), data.get('protocol','http'), data.get('path','/'), data.get('description',''), 1 if data.get('enabled',True) else 0, target_id))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/probe/targets/<int:target_id>', methods=['DELETE'])
@login_required
def delete_probe_target(target_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM probe_targets WHERE id = %s', (target_id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/probe/targets/<int:target_id>/test', methods=['POST'])
@login_required
def test_probe_target(target_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM probe_targets WHERE id = %s', (target_id,))
        target = cursor.fetchone()
        conn.close()
        if not target:
            return jsonify({'error': '目标不存在'}), 404
        result = _probe_single_target(dict(target))
        return jsonify({'status': 'success', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/probe/alerts', methods=['GET'])
@login_required
def get_probe_alerts():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        resolved = request.args.get('resolved')
        conn = get_db_readonly()
        cursor = conn.cursor()
        query = 'SELECT * FROM probe_alerts WHERE 1=1'
        count_q = 'SELECT COUNT(*) as total FROM probe_alerts WHERE 1=1'
        params = []
        if resolved is not None:
            query += ' AND resolved = %s'
            count_q += ' AND resolved = %s'
            params.append(1 if resolved == 'true' else 0)
        cursor.execute(count_q, params)
        total = cursor.fetchone()['total']
        query += ' ORDER BY created_at DESC LIMIT %s OFFSET %s'
        cursor.execute(query, params + [per_page, (page - 1) * per_page])
        alerts = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({'status': 'success', 'data': alerts, 'pagination': {'page': page, 'per_page': per_page, 'total': total, 'pages': (total + per_page - 1) // per_page}})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/probe/alerts/<int:alert_id>/resolve', methods=['PUT'])
@login_required
def resolve_probe_alert(alert_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE probe_alerts SET resolved = 1 WHERE id = %s', (alert_id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/probe/alerts/batch-resolve', methods=['PUT'])
@login_required
def batch_resolve_probe_alerts():
    try:
        data = request.json
        ids = data.get('ids', [])
        if not ids:
            return jsonify({'error': '请选择告警'}), 400
        conn = get_db()
        cursor = conn.cursor()
        ph = ','.join(['%s' for _ in ids])
        cursor.execute(f'UPDATE probe_alerts SET resolved = 1 WHERE id IN ({ph})', ids)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'affected': affected})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _probe_single_target(target):
    import socket as _socket
    import subprocess as _sp
    import platform as _pf
    host = target['host']
    port = int(target.get('port', 80))
    protocol = target.get('protocol', 'http')
    path = target.get('path', '/')
    result = {'host': host, 'port': port, 'protocol': protocol, 'status': 'unknown', 'status_code': None, 'response_time': None, 'error': None}
    start = time.time()
    try:
        if protocol == 'ping':
            # ICMP Ping
            param = '-n' if _pf.system().lower() == 'windows' else '-c'
            r = _sp.run(['ping', param, '1', '-w' if _pf.system().lower() == 'windows' else '-W', '5', host],
                        capture_output=True, text=True, timeout=10)
            elapsed = int((time.time() - start) * 1000)
            result['response_time'] = elapsed
            result['status'] = 'online' if r.returncode == 0 else 'offline'
            if r.returncode != 0:
                result['error'] = 'Ping 失败'
        elif protocol in ('http', 'https'):
            resp = requests.get(f"{protocol}://{host}:{port}{path}", timeout=10, verify=False)
            result['status_code'] = resp.status_code
            result['response_time'] = int((time.time() - start) * 1000)
            result['status'] = 'online' if resp.status_code < 500 else 'offline'
        else:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            sock.settimeout(10)
            r = sock.connect_ex((host, port))
            result['response_time'] = int((time.time() - start) * 1000)
            sock.close()
            result['status'] = 'online' if r == 0 else 'offline'
    except Exception as e:
        result['status'] = 'offline'
        result['error'] = str(e)[:200]
    return result


def probe_all_targets():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM probe_targets WHERE enabled = 1')
        targets = [dict(row) for row in cursor.fetchall()]
        if not targets:
            conn.close()
            return
        for target in targets:
            result = _probe_single_target(target)
            cursor.execute('UPDATE probe_targets SET last_status=%s, last_probe_time=NOW(), last_response_time=%s WHERE id=%s',
                (result['status'], result.get('response_time'), target['id']))
            if result['status'] == 'offline':
                cursor.execute('SELECT id FROM probe_alerts WHERE target_id = %s AND resolved = 0 LIMIT 1', (target['id'],))
                if not cursor.fetchone():
                    cursor.execute('INSERT INTO probe_alerts (target_id, target_name, target_host, alert_type, error_message) VALUES (%s,%s,%s,%s,%s)',
                        (target['id'], target['name'], target['host'], 'offline', result.get('error','')))
            else:
                cursor.execute('UPDATE probe_alerts SET resolved = 1 WHERE target_id = %s AND resolved = 0 AND alert_type = "offline"', (target['id'],))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[WARN] Probe error: {e}')


# =================================================================
# 后台定时任务
# =================================================================

def cleanup_old_records():
    import time as tmod
    while True:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT client_id, COUNT(*) as cnt FROM hardware_history GROUP BY client_id HAVING COUNT(*) > 10')
            for row in cursor.fetchall():
                try:
                    cursor.execute('DELETE FROM hardware_history WHERE id NOT IN (SELECT id FROM (SELECT id FROM hardware_history WHERE client_id=%s ORDER BY timestamp DESC LIMIT 10) AS t) AND client_id=%s', (row['client_id'], row['client_id']))
                except: pass
            conn.commit()
            conn.close()
        except: pass
        tmod.sleep(1800)


if __name__ == '__main__':
    init_db_pool()
    init_tables()

    import threading
    threading.Thread(target=cleanup_old_records, daemon=True).start()
    print('[INFO] cleanup started')

    def _probe_loop():
        while True:
            try:
                probe_all_targets()
            except: pass
            time.sleep(30)
    threading.Thread(target=_probe_loop, daemon=True).start()
    print('[INFO] probe started (30s)')
    print("=" * 50)
    print("HwMon Server v5.0.0 - http://localhost:5000")
    print("=" * 50)
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=5000, threads=20, connection_limit=2000)
    except ImportError:
        app.run(host='0.0.0.0', port=5000, debug=True)


