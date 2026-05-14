"""
登录功能测试脚本
"""
import requests
import sys

BASE_URL = 'http://localhost:5000'

def test_login_page():
    """测试登录页面是否可访问"""
    print("=" * 60)
    print("测试1: 访问登录页面")
    print("=" * 60)
    
    try:
        response = requests.get(f'{BASE_URL}/login')
        if response.status_code == 200:
            print("✓ 登录页面可访问")
            print(f"  状态码: {response.status_code}")
            print(f"  页面大小: {len(response.text)} bytes")
        else:
            print(f"✗ 登录页面访问失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 请求失败: {str(e)}")
    
    print()

def test_homepage_redirect():
    """测试主页重定向到登录页"""
    print("=" * 60)
    print("测试2: 未登录访问主页（应重定向）")
    print("=" * 60)
    
    try:
        # 使用新的session，不携带cookie
        session = requests.Session()
        response = session.get(f'{BASE_URL}/', allow_redirects=False)
        
        if response.status_code in [302, 303]:
            print("✓ 未登录访问主页被重定向")
            print(f"  状态码: {response.status_code}")
            print(f"  重定向到: {response.headers.get('Location')}")
        elif response.status_code == 200:
            # 检查是否是登录页面
            if 'login' in response.url.lower():
                print("✓ 未登录访问主页跳转到登录页")
                print(f"  当前URL: {response.url}")
            else:
                print("✗ 未登录可以访问主页（安全问题）")
        else:
            print(f"? 状态码: {response.status_code}")
    except Exception as e:
        print(f"✗ 请求失败: {str(e)}")
    
    print()

def test_login_success():
    """测试登录成功"""
    print("=" * 60)
    print("测试3: 使用正确凭据登录")
    print("=" * 60)
    
    try:
        session = requests.Session()
        
        # 登录
        login_response = session.post(
            f'{BASE_URL}/api/login',
            json={'username': 'xapi', 'password': 'Ai78965'},
            headers={'Content-Type': 'application/json'}
        )
        
        login_result = login_response.json()
        
        if login_result.get('status') == 'success':
            print("✓ 登录成功")
            print(f"  消息: {login_result['message']}")
            
            # 检查登录状态
            check_response = session.get(f'{BASE_URL}/api/check-login')
            check_result = check_response.json()
            
            if check_result.get('logged_in'):
                print("✓ 登录状态检查通过")
                print(f"  用户名: {check_result.get('username')}")
            else:
                print("✗ 登录状态检查失败")
            
            # 尝试访问受保护的API
            clients_response = session.get(f'{BASE_URL}/api/clients')
            if clients_response.status_code == 200:
                print("✓ 登录后可以访问受保护的API")
            else:
                print(f"✗ 登录后无法访问API: {clients_response.status_code}")
        else:
            print(f"✗ 登录失败: {login_result.get('message')}")
    except Exception as e:
        print(f"✗ 请求失败: {str(e)}")
    
    print()

def test_login_failure():
    """测试登录失败"""
    print("=" * 60)
    print("测试4: 使用错误凭据登录")
    print("=" * 60)
    
    try:
        session = requests.Session()
        
        # 使用错误密码
        login_response = session.post(
            f'{BASE_URL}/api/login',
            json={'username': 'xapi', 'password': 'wrong_password'},
            headers={'Content-Type': 'application/json'}
        )
        
        if login_response.status_code == 401:
            print("✓ 错误密码被拒绝")
            print(f"  状态码: {login_response.status_code}")
            result = login_response.json()
            print(f"  消息: {result.get('message')}")
        else:
            print(f"✗ 错误密码未被拒绝: {login_response.status_code}")
    except Exception as e:
        print(f"✗ 请求失败: {str(e)}")
    
    print()

def test_logout():
    """测试登出功能"""
    print("=" * 60)
    print("测试5: 登出功能")
    print("=" * 60)
    
    try:
        session = requests.Session()
        
        # 先登录
        session.post(
            f'{BASE_URL}/api/login',
            json={'username': 'xapi', 'password': 'Ai78965'},
            headers={'Content-Type': 'application/json'}
        )
        
        # 确认已登录
        check_before = session.get(f'{BASE_URL}/api/check-login').json()
        print(f"登录前状态: {'已登录' if check_before.get('logged_in') else '未登录'}")
        
        # 登出
        logout_response = session.post(f'{BASE_URL}/api/logout')
        logout_result = logout_response.json()
        
        if logout_result.get('status') == 'success':
            print("✓ 登出成功")
            print(f"  消息: {logout_result['message']}")
            
            # 确认已登出
            check_after = session.get(f'{BASE_URL}/api/check-login').json()
            print(f"登出后状态: {'已登录' if check_after.get('logged_in') else '未登录'}")
            
            # 尝试访问受保护的API（应该失败）
            clients_response = session.get(f'{BASE_URL}/api/clients', allow_redirects=False)
            if clients_response.status_code in [302, 303, 401]:
                print("✓ 登出后无法访问受保护的API")
                print(f"  状态码: {clients_response.status_code}")
            else:
                print(f"✗ 登出后仍可访问API（安全问题）: {clients_response.status_code}")
        else:
            print(f"✗ 登出失败: {logout_result}")
    except Exception as e:
        print(f"✗ 请求失败: {str(e)}")
    
    print()

def test_report_api_no_auth():
    """测试客户端上报API无需认证"""
    print("=" * 60)
    print("测试6: 客户端上报API无需登录")
    print("=" * 60)
    
    try:
        session = requests.Session()
        
        # 不登录，直接调用上报API
        report_response = session.post(
            f'{BASE_URL}/api/report',
            json={
                'client_id': 'test_client',
                'hostname': 'test_host',
                'local_ip': '127.0.0.1',
                'hardware_info': {}
            },
            headers={'Content-Type': 'application/json'}
        )
        
        # 应该返回200或400（缺少数据），但不应该是401
        if report_response.status_code in [200, 400]:
            print("✓ 客户端上报API无需登录")
            print(f"  状态码: {report_response.status_code}")
        elif report_response.status_code == 401:
            print("✗ 客户端上报API需要登录（配置错误）")
        else:
            print(f"? 状态码: {report_response.status_code}")
    except Exception as e:
        print(f"✗ 请求失败: {str(e)}")
    
    print()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("硬件监控系统 - 登录功能测试")
    print("=" * 60 + "\n")
    
    # 检查服务器是否运行
    try:
        response = requests.get(f'{BASE_URL}/login', timeout=2)
        print("✓ 服务器运行正常\n")
    except Exception as e:
        print(f"✗ 无法连接到服务器: {str(e)}")
        print("请确保服务器正在运行 (python app.py)")
        sys.exit(1)
    
    # 执行测试
    test_login_page()
    test_homepage_redirect()
    test_login_success()
    test_login_failure()
    test_logout()
    test_report_api_no_auth()
    
    print("=" * 60)
    print("测试完成！")
    print("=" * 60)
