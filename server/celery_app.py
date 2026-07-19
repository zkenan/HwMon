"""
Celery 配置模块
提供异步任务队列功能
"""

import os
import sys
import json
import logging

logger = logging.getLogger('hwmon')

# Redis 是否可用的标志
REDIS_AVAILABLE = False
celery = None


def load_config():
    """加载配置文件"""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    config_file = os.path.join(base_path, 'config.json')
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def init_celery():
    """初始化 Celery（延迟初始化，避免启动时连接失败）"""
    global celery, REDIS_AVAILABLE

    # 检查环境变量中是否有 REDIS_HOST，如果没有则跳过 Celery
    redis_host = os.environ.get('REDIS_HOST', '')
    if not redis_host or redis_host == 'localhost':
        # 没有配置 Redis，直接跳过 Celery
        logger.info("未配置 Redis，跳过 Celery 初始化，使用同步模式")
        celery = None
        REDIS_AVAILABLE = False
        return False

    try:
        import redis as redis_lib
        from celery import Celery
        from celery.schedules import crontab

        config = load_config()

        # Redis 配置
        REDIS_HOST = os.environ.get('REDIS_HOST') or config.get('redis', {}).get('host', 'localhost')
        REDIS_PORT = int(os.environ.get('REDIS_PORT') or config.get('redis', {}).get('port', 6379))
        REDIS_DB = int(os.environ.get('REDIS_DB') or config.get('redis', {}).get('db', 0))
        REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD') or config.get('redis', {}).get('password', None)

        # 先测试 Redis 连接
        try:
            r = redis_lib.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                socket_connect_timeout=3,
                socket_timeout=3
            )
            r.ping()
            r.close()
            logger.info(f"Redis 连接测试成功: {REDIS_HOST}:{REDIS_PORT}")
        except Exception as redis_err:
            logger.warning(f"Redis 不可用: {redis_err}. Celery 异步功能禁用，使用同步模式")
            celery = None
            REDIS_AVAILABLE = False
            return False

        # 构建 Redis URL
        if REDIS_PASSWORD:
            redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        else:
            redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

        # 创建 Celery 应用
        celery = Celery(
            'hwmon',
            broker=redis_url,
            backend=redis_url,
            include=['tasks']
        )

        # Celery 配置
        celery.conf.update(
            task_serializer='json',
            accept_content=['json'],
            result_serializer='json',
            timezone='Asia/Shanghai',
            enable_utc=True,
            task_track_started=True,
            task_time_limit=300,
            task_soft_time_limit=240,
            worker_prefetch_multiplier=4,
            worker_max_tasks_per_child=100,
            worker_concurrency=8,
            broker_connection_retry_on_startup=True,
            broker_connection_retry=True,
            broker_connection_max_retries=3,
        )

        # 定时任务调度
        celery.conf.beat_schedule = {
            'cleanup-old-records': {
                'task': 'tasks.cleanup_old_records',
                'schedule': crontab(minute=0, hour='*/2'),
            },
            'probe-all-targets': {
                'task': 'tasks.probe_all_targets',
                'schedule': 30.0,
            },
        }

        REDIS_AVAILABLE = True
        logger.info("Celery 配置初始化成功")
        return True

    except Exception as e:
        logger.warning(f"Celery 初始化失败: {e}. 异步任务功能禁用")
        celery = None
        REDIS_AVAILABLE = False
        return False


def is_celery_available():
    """检查 Celery 是否可用"""
    return REDIS_AVAILABLE and celery is not None
