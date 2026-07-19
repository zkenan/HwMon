"""
Redis 缓存模块
提供缓存装饰器和缓存管理功能
"""

import os
import json
import logging
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger('hwmon')

# 全局 Redis 连接池
redis_pool = None
redis_client = None


def init_redis():
    """初始化 Redis 连接池"""
    global redis_pool, redis_client
    try:
        import redis

        # 在函数内部读取环境变量，确保在导入时已经设置
        redis_host = os.environ.get('REDIS_HOST', 'localhost')
        redis_port = int(os.environ.get('REDIS_PORT', 6379))
        redis_db = int(os.environ.get('REDIS_DB', 0))
        redis_password = os.environ.get('REDIS_PASSWORD', None)

        logger.info(f"Redis 配置: host={redis_host}, port={redis_port}, db={redis_db}, password={'***' if redis_password else 'None'}")

        redis_pool = redis.ConnectionPool(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        redis_client = redis.Redis(connection_pool=redis_pool)
        redis_client.ping()
        logger.info("Redis 连接成功")
        return True
    except Exception as e:
        logger.warning(f"Redis 连接失败: {e}. 缓存功能禁用")
        redis_client = None
        return False


def get_redis():
    """获取 Redis 客户端"""
    return redis_client


def cache_result(ttl: int = 300, prefix: str = 'hwmon'):
    """缓存函数结果"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            client = get_redis()
            if not client:
                return func(*args, **kwargs)

            # 生成缓存键
            key = f"{prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"

            # 尝试获取缓存
            try:
                cached = client.get(key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass

            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            try:
                client.setex(key, ttl, json.dumps(result, ensure_ascii=False))
            except Exception:
                pass

            return result
        return wrapper
    return decorator


def invalidate_cache(pattern: str):
    """清除匹配模式的缓存"""
    client = get_redis()
    if not client:
        return
    try:
        keys = client.keys(pattern)
        if keys:
            client.delete(*keys)
    except Exception:
        pass


def get_cache(key: str) -> Optional[Any]:
    """获取缓存值"""
    client = get_redis()
    if not client:
        logger.warning(f'get_cache: Redis client is None, key={key}')
        return None
    try:
        cached = client.get(key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.error(f'get_cache failed: key={key}, error={e}')
    return None


def _json_serializer(obj):
    """自定义 JSON 序列化器，处理 datetime 类型"""
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    if hasattr(obj, 'strftime'):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    return str(obj)


def set_cache(key: str, value: Any, ttl: int = 300):
    """设置缓存值"""
    client = get_redis()
    if not client:
        return
    try:
        serialized = json.dumps(value, ensure_ascii=False, default=_json_serializer)
        client.setex(key, ttl, serialized)
    except Exception as e:
        logger.error(f'set_cache failed: key={key}, error={e}')
