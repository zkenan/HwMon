"""
告警设置功能测试脚本
"""
import requests
import json

BASE_URL = 'http://localhost:5000'

def test_get_alert_settings():
    """测试获取告警设置"""
    print("=" * 60)
    print("测试1: 获取告警设置")
    print("=" * 60)
    
    try:
        response = requests.get(f'{BASE_URL}/api/alert-settings')
        result = response.json()
        
        if result['status'] == 'success':
            settings = result['data']
            print("✓ 获取成功")
            print(f"  CPU监控: {'启用' if settings['monitor_cpu'] else '禁用'}")
            print(f"  GPU监控: {'启用' if settings['monitor_gpu'] else '禁用'}")
            print(f"  内存监控: {'启用' if settings['monitor_memory'] else '禁用'}")
            print(f"  硬盘监控: {'启用' if settings['monitor_disk'] else '禁用'}")
            print(f"  网卡监控: {'启用' if settings['monitor_network'] else '禁用'}")
            print(f"  主板监控: {'启用' if settings['monitor_motherboard'] else '禁用'}")
            print(f"  BIOS监控: {'启用' if settings['monitor_bios'] else '禁用'}")
        else:
            print(f"✗ 获取失败: {result.get('error')}")
    except Exception as e:
        print(f"✗ 请求失败: {str(e)}")
    
    print()

def test_update_alert_settings():
    """测试更新告警设置 - 只监控CPU和内存"""
    print("=" * 60)
    print("测试2: 更新告警设置（仅监控CPU和内存）")
    print("=" * 60)
    
    try:
        new_settings = {
            'monitor_cpu': True,
            'monitor_gpu': False,
            'monitor_memory': True,
            'monitor_disk': False,
            'monitor_network': False,
            'monitor_motherboard': False,
            'monitor_bios': False
        }
        
        response = requests.put(
            f'{BASE_URL}/api/alert-settings',
            json=new_settings,
            headers={'Content-Type': 'application/json'}
        )
        result = response.json()
        
        if result['status'] == 'success':
            print("✓ 更新成功")
            print(f"  消息: {result['message']}")
            
            # 验证更新
            verify_response = requests.get(f'{BASE_URL}/api/alert-settings')
            verify_result = verify_response.json()
            if verify_result['status'] == 'success':
                settings = verify_result['data']
                print("\n验证当前设置:")
                print(f"  CPU监控: {'启用' if settings['monitor_cpu'] else '禁用'}")
                print(f"  GPU监控: {'启用' if settings['monitor_gpu'] else '禁用'}")
                print(f"  内存监控: {'启用' if settings['monitor_memory'] else '禁用'}")
                print(f"  硬盘监控: {'启用' if settings['monitor_disk'] else '禁用'}")
                print(f"  网卡监控: {'启用' if settings['monitor_network'] else '禁用'}")
                print(f"  主板监控: {'启用' if settings['monitor_motherboard'] else '禁用'}")
                print(f"  BIOS监控: {'启用' if settings['monitor_bios'] else '禁用'}")
        else:
            print(f"✗ 更新失败: {result.get('error')}")
    except Exception as e:
        print(f"✗ 请求失败: {str(e)}")
    
    print()

def test_restore_default_settings():
    """测试恢复默认设置"""
    print("=" * 60)
    print("测试3: 恢复默认告警设置")
    print("=" * 60)
    
    try:
        default_settings = {
            'monitor_cpu': True,
            'monitor_gpu': True,
            'monitor_memory': True,
            'monitor_disk': True,
            'monitor_network': False,
            'monitor_motherboard': False,
            'monitor_bios': False
        }
        
        response = requests.put(
            f'{BASE_URL}/api/alert-settings',
            json=default_settings,
            headers={'Content-Type': 'application/json'}
        )
        result = response.json()
        
        if result['status'] == 'success':
            print("✓ 恢复成功")
            print(f"  消息: {result['message']}")
        else:
            print(f"✗ 恢复失败: {result.get('error')}")
    except Exception as e:
        print(f"✗ 请求失败: {str(e)}")
    
    print()

if __name__ == '__main__':
    print("\n硬件监控系统 - 告警设置功能测试\n")
    
    # 检查服务器是否运行
    try:
        response = requests.get(f'{BASE_URL}/api/groups')
        if response.status_code == 200:
            print("✓ 服务器运行正常\n")
        else:
            print(f"✗ 服务器返回异常状态码: {response.status_code}\n")
            exit(1)
    except Exception as e:
        print(f"✗ 无法连接到服务器: {str(e)}")
        print("请确保服务器正在运行 (python app.py)")
        exit(1)
    
    # 执行测试
    test_get_alert_settings()
    test_update_alert_settings()
    test_get_alert_settings()
    test_restore_default_settings()
    test_get_alert_settings()
    
    print("=" * 60)
    print("测试完成！")
    print("=" * 60)
