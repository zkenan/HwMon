"""
自动修复MySQL数据库中错误的时间数据
将错误的年份自动修正为正确的当前年份
"""
import pymysql
from datetime import datetime

# MySQL配置
MYSQL_CONFIG = {
    'host': '192.168.20.17',
    'port': 3306,
    'user': 'HwMon',
    'password': 'kk7cy7SDWDMXC5XQ',
    'database': 'hwmon',
    'charset': 'utf8mb4'
}

def auto_fix_time():
    """自动修复时间问题"""
    print("=" * 60)
    print("自动修复MySQL时间数据")
    print("=" * 60)
    
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 1. 检查MySQL服务器时间
        print("\n1. 检查MySQL服务器时间:")
        cursor.execute("SELECT NOW()")
        mysql_time = cursor.fetchone()[0]
        mysql_year = mysql_time.year
        current_year = datetime.now().year
        
        print(f"   MySQL服务器时间: {mysql_time}")
        print(f"   Python本地时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if mysql_year == current_year:
            print(f"\n   ✅ 时间正常（{current_year}年），无需修复")
            return
        
        year_diff = mysql_year - current_year
        print(f"\n    错误发现：MySQL年份为 {mysql_year}，应该是 {current_year}年")
        print(f"   差值：{year_diff} 年")
        
        # 2. 自动修复所有表
        print(f"\n2. 开始自动修复时间数据（减去 {year_diff} 年）...\n")
        
        tables = [
            ('clients', 'last_report, created_at'),
            ('hardware_reports', 'timestamp'),
            ('hardware_history', 'timestamp'),
            ('alert_records', 'created_at'),
            ('client_baselines', 'baseline_timestamp'),
            ('`groups`', 'created_at'),
        ]
        
        total_fixed = 0
        for table, columns in tables:
            print(f"   修复 {table} 表...")
            col_list = [c.strip() for c in columns.split(',')]
            
            for col in col_list:
                cursor.execute(f"""
                    UPDATE {table} 
                    SET {col} = DATE_SUB({col}, INTERVAL %s YEAR)
                    WHERE YEAR({col}) = %s
                """, (year_diff, mysql_year))
                affected = cursor.rowcount
                total_fixed += affected
                if affected > 0:
                    print(f"      ✓ {col}: {affected}条记录")
            
            conn.commit()
        
        print(f"\n✅ 修复完成！共修复 {total_fixed} 条记录")
        print(f"   已将 {mysql_year}年 改为 {current_year}年")
        
        # 3. 验证
        print("\n3. 验证修复结果:")
        cursor.execute("SELECT NOW()")
        mysql_time = cursor.fetchone()[0]
        print(f"   MySQL当前时间: {mysql_time}")
        print(f"   Python当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"\n 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()
    
    print("\n" + "=" * 60)
    print("重要提示:")
    print("虽然数据库数据已修复，但MySQL服务器的操作系统时间仍然错误！")
    print("请联系服务器管理员修正系统时间，否则新数据仍会出错。")
    print("\nWindows服务器修正方法:")
    print("  1. 右键任务栏时间 -> 调整日期/时间")
    print("  2. 关闭'自动设置时间'")
    print("  3. 手动设置正确时间")
    print("\nLinux服务器修正方法:")
    print("  sudo timedatectl set-time 'YYYY-MM-DD HH:MM:SS'")
    print("=" * 60)

if __name__ == '__main__':
    auto_fix_time()
