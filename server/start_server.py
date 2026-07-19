#!/usr/bin/env python3
"""启动服务器"""
import sys
import os

# 设置环境变量（仅在未设置时使用默认值）
def set_env_if_not_set(key, default):
    if key not in os.environ:
        os.environ[key] = default

set_env_if_not_set('DB_HOST', '192.168.20.27')
set_env_if_not_set('DB_PORT', '3306')
set_env_if_not_set('DB_USER', 'hwmon')
set_env_if_not_set('DB_PASSWORD', 'hwmon')
set_env_if_not_set('DB_NAME', 'hwmon')
set_env_if_not_set('REDIS_HOST', '192.168.20.27')
set_env_if_not_set('REDIS_PORT', '6379')
set_env_if_not_set('REDIS_PASSWORD', 'redis_S5RBDd')
set_env_if_not_set('LOGIN_USERNAME', 'admin')
set_env_if_not_set('LOGIN_PASSWORD', 'admin123')
set_env_if_not_set('SECRET_KEY', 'hwmon-secret-key')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 确保环境变量在导入 app 之前设置
print(f"DB_HOST: {os.environ.get('DB_HOST')}")
print(f"DB_PORT: {os.environ.get('DB_PORT')}")
print(f"DB_USER: {os.environ.get('DB_USER')}")
print(f"DB_NAME: {os.environ.get('DB_NAME')}")

from app import create_app
from waitress import serve

app = create_app()
print("Starting server on port 5000...")
serve(app, host='0.0.0.0', port=5000, threads=20)
