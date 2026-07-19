"""
清理 HwMon 测试数据库中的旧数据
运行: python cleanup_db.py
"""
import pymysql
import json

# 从 config.json 读取数据库配置
import os
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server', 'config.json')
if not os.path.exists(config_path):
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

with open(config_path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

db = cfg.get('database', {})
print(f"连接数据库: {db.get('host')}:{db.get('port')}/{db.get('database')}")

conn = pymysql.connect(
    host=db.get('host', 'localhost'),
    port=db.get('port', 3306),
    user=db.get('user', 'root'),
    password=db.get('password', ''),
    database=db.get('database', 'hwmon'),
    charset='utf8mb4'
)
cursor = conn.cursor()

# 查看当前数据
tables = ['clients', 'alert_records', 'process_alert_records', 'hardware_reports', 'hardware_history', 'client_baselines']
print("\n=== 清理前数据 ===")
for t in tables:
    try:
        cursor.execute(f'SELECT COUNT(*) FROM `{t}`')
        count = cursor.fetchone()[0]
        print(f"  {t}: {count} 条")
    except Exception:
        print(f"  {t}: 表不存在")

# 清理
print("\n=== 清理中 ===")
for t in ['hardware_history', 'hardware_reports', 'alert_records', 'process_alert_records', 'client_baselines', 'clients']:
    try:
        cursor.execute(f'DELETE FROM `{t}`')
        print(f"  {t}: 已清空 ({cursor.rowcount} 条)")
    except Exception as e:
        print(f"  {t}: 跳过 ({e})")

conn.commit()

# 验证
print("\n=== 清理后数据 ===")
for t in tables:
    try:
        cursor.execute(f'SELECT COUNT(*) FROM `{t}`')
        count = cursor.fetchone()[0]
        print(f"  {t}: {count} 条")
    except Exception:
        print(f"  {t}: 表不存在")

conn.close()
print("\n清理完成!")
