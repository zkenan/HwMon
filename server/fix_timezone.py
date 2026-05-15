"""
修复MySQL数据库中错误的时间数据
将2026年的错误时间修正为正确的当前时间
"""
import pymysql
from datetime import datetime, timedelta

# MySQL配置
MYSQL_CONFIG = {
    'host': '192.168.20.17',
    'port': 3306,
    'user': 'HwMon',
    'password': 'kk7cy7SDWDMXC5XQ',
    'database': 'hwmon',
    'charset': 'utf8mb4'
}

def check_and_fix_time():
    """检查并修复时间问题"""
    print("=" * 60)
    print("检查MySQL服务器系统时间")
    print("=" * 60)
    
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 1. 检查MySQL服务器时间
        print("\n1. 检查MySQL服务器系统时间:")
        cursor.execute("SELECT NOW(), @@version")
        mysql_info = cursor.fetchone()
        mysql_time = mysql_info[0]
        print(f"   MySQL时间: {mysql_time}")
        print(f"   MySQL版本: {mysql_info[1]}")
        print(f"   Python时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 检查是否年份错误
        mysql_year = mysql_time.year
        current_year = datetime.now().year
        
        if mysql_year != current_year:
            print(f"\n   ⚠ 错误发现：MySQL服务器年份为 {mysql_year}，但应该是 {current_year}！")
            print(f"   差值：{mysql_year - current_year} 年")
            
            # 询问是否修复
            fix = input(f"\n是否要修复所有时间数据（将年份从 {mysql_year} 改为 {current_year}）？(y/n): ")
            if fix.lower() == 'y':
                year_diff = mysql_year - current_year
                print(f"\n2. 开始修复时间数据（减去 {year_diff} 年）...")
                
                # 修复clients表
                print("   修复 clients 表...")
                cursor.execute("""
                    UPDATE clients 
                    SET last_report = DATE_SUB(last_report, INTERVAL %s YEAR),
                        created_at = DATE_SUB(created_at, INTERVAL %s YEAR)
                    WHERE YEAR(last_report) = %s OR YEAR(created_at) = %s
                """, (year_diff, year_diff, mysql_year, mysql_year))
                affected = cursor.rowcount
                conn.commit()
                print(f"   ✓ clients表修复完成（{affected}条记录）")
                
                # 修复hardware_reports表
                print("   修复 hardware_reports 表...")
                cursor.execute("""
                    UPDATE hardware_reports 
                    SET timestamp = DATE_SUB(timestamp, INTERVAL %s YEAR)
                    WHERE YEAR(timestamp) = %s
                """, (year_diff, mysql_year))
                affected = cursor.rowcount
                conn.commit()
                print(f"   ✓ hardware_reports表修复完成（{affected}条记录）")
                
                # 修复hardware_history表
                print("   修复 hardware_history 表...")
                cursor.execute("""
                    UPDATE hardware_history 
                    SET timestamp = DATE_SUB(timestamp, INTERVAL %s YEAR)
                    WHERE YEAR(timestamp) = %s
                """, (year_diff, mysql_year))
                affected = cursor.rowcount
                conn.commit()
                print(f"   ✓ hardware_history表修复完成（{affected}条记录）")
                
                # 修复alert_records表
                print("   修复 alert_records 表...")
                cursor.execute("""
                    UPDATE alert_records 
                    SET created_at = DATE_SUB(created_at, INTERVAL %s YEAR)
                    WHERE YEAR(created_at) = %s
                """, (year_diff, mysql_year))
                affected = cursor.rowcount
                conn.commit()
                print(f"   ✓ alert_records表修复完成（{affected}条记录）")
                
                # 修复client_baselines表
                print("   修复 client_baselines 表...")
                cursor.execute("""
                    UPDATE client_baselines 
                    SET baseline_timestamp = DATE_SUB(baseline_timestamp, INTERVAL %s YEAR)
                    WHERE YEAR(baseline_timestamp) = %s
                """, (year_diff, mysql_year))
                affected = cursor.rowcount
                conn.commit()
                print(f"   ✓ client_baselines表修复完成（{affected}条记录）")
                
                # 修复`groups`表
                print("   修复 groups 表...")
                cursor.execute("""
                    UPDATE `groups` 
                    SET created_at = DATE_SUB(created_at, INTERVAL %s YEAR)
                    WHERE YEAR(created_at) = %s
                """, (year_diff, mysql_year))
                affected = cursor.rowcount
                conn.commit()
                print(f"   ✓ groups表修复完成（{affected}条记录）")
                
                print(f"\n✅ 所有时间数据修复完成！已将 {mysql_year}年 改为 {current_year}年")
            else:
                print("已取消修复")
        else:
            print(f"   ✓ 时间正常（{current_year}年）")
        
        # 最终验证
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
    print("问题根源：MySQL服务器的操作系统时间设置错误！")
    print(f"当前MySQL服务器时间显示为 {mysql_year}年")
    print("请联系服务器管理员修正系统时间：")
    print("  Windows: date 命令或控制面板")
    print("  Linux: date -s 或 timedatectl 命令")
    print("=" * 60)

if __name__ == '__main__':
    check_and_fix_time()
