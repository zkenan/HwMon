"""
数据库迁移脚本：SQLite -> MySQL
"""
import sqlite3
import pymysql
import json

# SQLite配置
SQLITE_DB = 'hardware_monitor.db'

# MySQL配置
MYSQL_CONFIG = {
    'host': '192.168.20.17',
    'port': 3306,
    'user': 'HwMon',
    'password': 'kk7cy7SDWDMXC5XQ',
    'database': 'hwmon',
    'charset': 'utf8mb4'
}

def migrate_data():
    """迁移SQLite数据到MySQL"""
    print("开始迁移数据...")
    
    # 连接SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    # 连接MySQL
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cursor = mysql_conn.cursor()
    
    try:
        # 迁移groups表
        print("迁移分组数据...")
        sqlite_cursor.execute('SELECT * FROM groups')
        groups = sqlite_cursor.fetchall()
        for g in groups:
            mysql_cursor.execute('''
                INSERT INTO groups (id, name, description, created_at) 
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE name=VALUES(name)
            ''', (g['id'], g['name'], g['description'], g['created_at']))
        print(f"  迁移了 {len(groups)} 个分组")
        
        # 迁移clients表
        print("迁移客户端数据...")
        sqlite_cursor.execute('SELECT * FROM clients')
        clients = sqlite_cursor.fetchall()
        for c in clients:
            mysql_cursor.execute('''
                INSERT INTO clients (id, client_id, hostname, local_ip, group_id, last_report, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE hostname=VALUES(hostname), local_ip=VALUES(local_ip)
            ''', (c['id'], c['client_id'], c['hostname'], c['local_ip'], 
                  c['group_id'], c['last_report'], c['created_at']))
        print(f"  迁移了 {len(clients)} 个客户端")
        
        # 迁移hardware_reports表
        print("迁移硬件报告数据...")
        sqlite_cursor.execute('SELECT * FROM hardware_reports')
        reports = sqlite_cursor.fetchall()
        for r in reports:
            mysql_cursor.execute('''
                INSERT INTO hardware_reports (id, client_id, report_data, report_type, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            ''', (r['id'], r['client_id'], r['report_data'], r['report_type'], r['timestamp']))
        print(f"  迁移了 {len(reports)} 条硬件报告")
        
        # 迁移hardware_history表
        print("迁移硬件历史数据...")
        sqlite_cursor.execute('SELECT * FROM hardware_history')
        history = sqlite_cursor.fetchall()
        for h in history:
            mysql_cursor.execute('''
                INSERT INTO hardware_history (id, client_id, cpu_info, memory_info, disk_info, gpu_info, snapshot, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (h['id'], h['client_id'], h['cpu_info'], h['memory_info'], 
                  h['disk_info'], h['gpu_info'], h['snapshot'], h['timestamp']))
        print(f"  迁移了 {len(history)} 条硬件历史")
        
        # 迁移client_baselines表
        print("迁移基准数据...")
        sqlite_cursor.execute('SELECT * FROM client_baselines')
        baselines = sqlite_cursor.fetchall()
        for b in baselines:
            mysql_cursor.execute('''
                INSERT INTO client_baselines (client_id, cpu_snapshot, gpu_snapshot, memory_snapshot, disk_snapshot, baseline_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE cpu_snapshot=VALUES(cpu_snapshot)
            ''', (b['client_id'], b['cpu_snapshot'], b['gpu_snapshot'], 
                  b['memory_snapshot'], b['disk_snapshot'], b['baseline_timestamp']))
        print(f"  迁移了 {len(baselines)} 个基准")
        
        # 迁移alert_records表
        print("迁移告警记录...")
        sqlite_cursor.execute('SELECT * FROM alert_records')
        alerts = sqlite_cursor.fetchall()
        for a in alerts:
            mysql_cursor.execute('''
                INSERT INTO alert_records (id, client_id, alert_type, alert_detail, resolved, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (a['id'], a['client_id'], a['alert_type'], a['alert_detail'], 
                  a['resolved'], a['created_at']))
        print(f"  迁移了 {len(alerts)} 条告警记录")
        
        # 迁移email_config表
        print("迁移邮件配置...")
        sqlite_cursor.execute('SELECT * FROM email_config')
        email_configs = sqlite_cursor.fetchall()
        for e in email_configs:
            mysql_cursor.execute('''
                INSERT INTO email_config (id, smtp_host, smtp_port, smtp_user, smtp_password, sender_name, recipients, enabled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE smtp_host=VALUES(smtp_host)
            ''', (e['id'], e['smtp_host'], e['smtp_port'], e['smtp_user'], 
                  e['smtp_password'], e['sender_name'], e['recipients'], e['enabled']))
        print(f"  迁移了 {len(email_configs)} 条邮件配置")
        
        # 迁移alert_settings表
        print("迁移告警设置...")
        sqlite_cursor.execute('SELECT * FROM alert_settings')
        settings = sqlite_cursor.fetchall()
        for s in settings:
            mysql_cursor.execute('''
                INSERT INTO alert_settings (id, monitor_cpu, monitor_gpu, monitor_memory, monitor_disk, monitor_network, monitor_motherboard, monitor_bios)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE monitor_cpu=VALUES(monitor_cpu)
            ''', (s['id'], s['monitor_cpu'], s['monitor_gpu'], s['monitor_memory'], 
                  s['monitor_disk'], s['monitor_network'], s['monitor_motherboard'], s['monitor_bios']))
        print(f"  迁移了 {len(settings)} 条告警设置")
        
        mysql_conn.commit()
        print("\n✓ 数据迁移完成！")
        
    except Exception as e:
        mysql_conn.rollback()
        print(f"\n✗ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sqlite_conn.close()
        mysql_conn.close()

if __name__ == '__main__':
    migrate_data()
