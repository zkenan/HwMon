FROM python:3.9-slim

WORKDIR /app

# 先复制依赖清单，利用 Docker 层缓存：依赖不变时无需重新安装
COPY requirements.txt .

# 使用国内镜像源安装依赖（依赖版本以 requirements.txt 为准）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制应用代码
COPY . .

# 创建日志目录
RUN mkdir -p /app/logs

# 设置 Python 不缓冲输出
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python", "start_server.py"]
