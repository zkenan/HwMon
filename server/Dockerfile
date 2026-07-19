FROM python:3.9-slim

WORKDIR /app

# 使用国内镜像源安装依赖
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    flask flask-cors requests waitress openpyxl pymysql DBUtils \
    cryptography python-dotenv gunicorn redis celery

# 复制应用代码
COPY . .

# 创建日志目录
RUN mkdir -p /app/logs

# 设置Python不缓冲输出
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python", "start_server.py"]
