import socket
import requests
import time

clients = [
    ('192.168.20.18', 'win-DL'),
    ('192.168.20.25', 'longxia')
]

print('=' * 50)
print('硬件监控客户端诊断工具')
print('=' * 50)

for ip, name in clients:
    print('\n--- %s (%s) ---' % (name, ip))
    
    # 1. Ping测试
    import subprocess
    try:
        result = subprocess.run(['ping', '-n', '1', '-w', '1000', ip], 
                              capture_output=True, text=True, timeout=5)
        if 'TTL' in result.stdout:
            print('  [1] Ping: OK')
        else:
            print('  [1] Ping: FAIL (客户端可能离线)')
    except:
        print('  [1] Ping: FAIL')
    
    # 2. 13301端口测试
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((ip, 13301))
        sock.close()
        if result == 0:
            print('  [2] 13301端口: 开放')
            # 测试HTTP
            try:
                resp = requests.get('http://%s:13301/api/status' % ip, timeout=3)
                print('      HTTP /api/status: %d' % resp.status_code)
                if resp.status_code == 200:
                    data = resp.json()
                    print('      状态: %s' % data.get('status', 'unknown'))
            except Exception as e:
                print('      HTTP请求: FAIL - %s' % e)
        else:
            print('  [2] 13301端口: 不可达 (WinError 10061)')
    except Exception as e:
        print('  [2] 13301端口: 测试失败 - %s' % e)

print('\n' + '=' * 50)
print('诊断完成')
print('=' * 50)
print('\n如果13301端口不可达，请:')
print('1. 确认客户端运行的是最新版HardwareMonitor.exe')
print('2. 以管理员身份运行客户端目录下的 fix_firewall.bat')
print('3. 或者使用 deploy.bat 一键重新部署')
