#!/usr/bin/env python3
"""HwMon Server v5.0.1 启动脚本

数据库 / Redis / 登录 / 密钥等配置全部从环境变量读取。
生产部署时由 docker-compose.yml 注入（见项目根目录 .env 文件）。
未设置必填项时会在启动前给出明确提示，不再静默回退到开发环境默认值。
"""
import sys
import os

REQUIRED_KEYS = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME',
                 'REDIS_HOST', 'SECRET_KEY']

missing = [k for k in REQUIRED_KEYS if not os.environ.get(k)]
if missing:
    print(f"[启动失败] 缺少必要的环境变量: {', '.join(missing)}")
    print("请通过 docker-compose.yml / .env 注入，或参考 .env.example 配置。")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 确保环境变量在导入 app 之前已就绪
print(f"DB_HOST: {os.environ.get('DB_HOST')}")
print(f"DB_PORT: {os.environ.get('DB_PORT', '3306')}")
print(f"DB_USER: {os.environ.get('DB_USER')}")
print(f"DB_NAME: {os.environ.get('DB_NAME')}")
print(f"REDIS_HOST: {os.environ.get('REDIS_HOST')}")

from app import create_app
from waitress import serve

app = create_app()
print("HwMon Server v5.0.1 starting on port 5000...")
serve(app, host='0.0.0.0', port=5000, threads=50)
