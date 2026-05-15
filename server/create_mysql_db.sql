-- 创建硬件监控数据库
CREATE DATABASE IF NOT EXISTS hwmon DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建分组表
CREATE TABLE IF NOT EXISTS hwmon.groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建客户端表
CREATE TABLE IF NOT EXISTS hwmon.clients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL UNIQUE,
    hostname VARCHAR(255),
    local_ip VARCHAR(45),
    group_id INT,
    last_report DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL,
    INDEX idx_client_id (client_id),
    INDEX idx_group_id (group_id),
    INDEX idx_last_report (last_report)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建硬件信息历史表
CREATE TABLE IF NOT EXISTS hwmon.hardware_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL,
    report_data LONGTEXT,
    report_type VARCHAR(50) DEFAULT 'scheduled',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_client_id (client_id),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建硬件采集历史表
CREATE TABLE IF NOT EXISTS hwmon.hardware_history (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建客户端硬件基准表
CREATE TABLE IF NOT EXISTS hwmon.client_baselines (
    client_id VARCHAR(255) PRIMARY KEY,
    cpu_snapshot TEXT,
    gpu_snapshot TEXT,
    memory_snapshot TEXT,
    disk_snapshot TEXT,
    baseline_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建告警记录表
CREATE TABLE IF NOT EXISTS hwmon.alert_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    alert_detail LONGTEXT NOT NULL,
    resolved TINYINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_client_id (client_id),
    INDEX idx_resolved (resolved),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建邮件配置表
CREATE TABLE IF NOT EXISTS hwmon.email_config (
    id INT PRIMARY KEY,
    smtp_host VARCHAR(255) NOT NULL DEFAULT 'smtp.qq.com',
    smtp_port INT NOT NULL DEFAULT 465,
    smtp_user VARCHAR(255) NOT NULL DEFAULT '',
    smtp_password VARCHAR(255) NOT NULL DEFAULT '',
    sender_name VARCHAR(255) DEFAULT '硬件监控系统',
    recipients TEXT NOT NULL DEFAULT '[]',
    enabled TINYINT DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建告警设置表
CREATE TABLE IF NOT EXISTS hwmon.alert_settings (
    id INT PRIMARY KEY,
    monitor_cpu TINYINT DEFAULT 1,
    monitor_gpu TINYINT DEFAULT 1,
    monitor_memory TINYINT DEFAULT 1,
    monitor_disk TINYINT DEFAULT 1,
    monitor_network TINYINT DEFAULT 0,
    monitor_motherboard TINYINT DEFAULT 0,
    monitor_bios TINYINT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
