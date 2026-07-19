"""
缓存失效管理器
在数据更新时清除相关缓存
"""

from cache import invalidate_cache


def on_client_update(client_id: str):
    """客户端更新时清除相关缓存"""
    invalidate_cache('hwmon:dashboard:*')
    invalidate_cache(f'hwmon:client:{client_id}:*')


def on_group_update(group_id: int = None):
    """分组更新时清除相关缓存"""
    invalidate_cache('hwmon:dashboard:*')
    invalidate_cache('hwmon:groups:*')


def on_alert_update():
    """告警更新时清除相关缓存"""
    invalidate_cache('hwmon:dashboard:*')


def on_alert_settings_update():
    """告警设置更新时清除相关缓存"""
    invalidate_cache('hwmon:alert_settings:*')


def on_email_config_update():
    """邮件配置更新时清除相关缓存"""
    invalidate_cache('hwmon:email_config:*')
