"""
初始化MySQL数据库
创建数据库和表结构
"""
import pymysql

# MySQL配置
MYSQL_CONFIG = {
    'host': '192.168.20.17',
    'port': 3306,
    'user': 'HwMon',
    'password': 'kk7cy7SDWDMXC5XQ',
    'charset': 'utf8mb4'
}

def init_database():
    """初始化数据库"""
    print("正在连接MySQL服务器...")
    
    # 连接到MySQL服务器（不指定数据库）
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 创建数据库
        print("创建数据库 hwmon...")
        cursor.execute('CREATE DATABASE IF NOT EXISTS hwmon CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        print("✓ 数据库创建成功")
        
        # 使用数据库
        cursor.execute('USE hwmon')
        
        # 创建分组表
        print("创建 groups 表...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS `groups` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        print("✓ groups 表创建成功")

        # 创建客户端表
        print("创建 clients 表...")
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
        print("✓ clients 表创建成功")

        # 创建硬件信息历史表
        print("创建 hardware_reports 表...")
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
        print("✓ hardware_reports 表创建成功")

        # 创建硬件采集历史表
        print("创建 hardware_history 表...")
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
        print("✓ hardware_history 表创建成功")

        # 创建客户端硬件基准表
        print("创建 client_baselines 表...")
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
        print("✓ client_baselines 表创建成功")

        # 创建告警记录表
        print("创建 alert_records 表...")
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
        print("✓ alert_records 表创建成功")

        # 创建邮件配置表
        print("创建 email_config 表...")
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
        print("✓ email_config 表创建成功")

        # 创建告警设置表
        print("创建 alert_settings 表...")
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
        print("✓ alert_settings 表创建成功")

        # 创建默认分组
        print("创建默认分组...")
        cursor.execute('INSERT IGNORE INTO `groups` (name, description) VALUES (%s, %s)',
                       ('默认分组', '未分组的客户端'))
        print("✓ 默认分组创建成功")

        conn.commit()
        print("\n✅ 数据库初始化完成！")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ 数据库初始化失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    init_database()
