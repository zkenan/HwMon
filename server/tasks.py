"""
Celery 任务定义模块
提供异步任务处理功能
"""

import json
import time
import logging
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from celery_app import celery, is_celery_available
from cache import get_cache, set_cache

logger = logging.getLogger('hwmon')

# 东八区时区
TZ_CST = timezone(timedelta(hours=8), name='CST')

# 独立线程池用于硬件检测
hw_detection_executor = ThreadPoolExecutor(
    max_workers=20,
    thread_name_prefix='hw_detect'
)

# 独立线程池用于 AI 分析
ai_analysis_executor = ThreadPoolExecutor(
    max_workers=10,
    thread_name_prefix='ai_analysis'
)


def get_db():
    """获取数据库连接"""
    from app import db_pool
    conn = db_pool.connection()
    cursor = conn.cursor()
    cursor.execute("SET time_zone='+08:00'")
    return conn


def get_db_readonly():
    """获取只读数据库连接"""
    from app import db_pool
    conn = db_pool.connection()
    cursor = conn.cursor()
    cursor.execute("SET time_zone='+08:00'")
    cursor.execute("SET SESSION TRANSACTION READ ONLY")
    return conn


def task_or_func(func):
    """装饰器：如果 Celery 不可用则作为普通函数执行"""
    if is_celery_available() and celery is not None:
        return celery.task(bind=True, max_retries=3)(func)
    else:
        # Celery 不可用时，返回一个可调用的包装器
        def sync_wrapper(*args, **kwargs):
            logger.warning(f"Celery 不可用，同步执行任务: {func.__name__}")
            # 模拟 self 对象
            class FakeSelf:
                def retry(self, exc=None, countdown=60):
                    raise exc
            return func(FakeSelf(), *args, **kwargs)
        sync_wrapper.delay = sync_wrapper
        sync_wrapper.apply_async = sync_wrapper
        sync_wrapper.__name__ = func.__name__
        return sync_wrapper


@task_or_func
def process_client_report(self, client_id, hostname, hardware_info, local_ip):
    """异步处理客户端上报数据"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 更新客户端信息
        current_time = datetime.now(TZ_CST).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO clients (client_id, hostname, local_ip, last_report)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                hostname = VALUES(hostname),
                local_ip = VALUES(local_ip),
                last_report = VALUES(last_report)
        ''', (client_id, hostname, local_ip, current_time))
        conn.commit()

        # 保存硬件报告
        cursor.execute('''
            INSERT INTO hardware_reports (client_id, report_data, report_type)
            VALUES (%s, %s, %s)
        ''', (client_id, json.dumps(hardware_info, ensure_ascii=False), 'scheduled'))

        # 保存硬件历史
        cpu_info = json.dumps(hardware_info.get('cpu', []), ensure_ascii=False) if hardware_info.get('cpu') else ''
        mem_info = json.dumps(hardware_info.get('memory', {}), ensure_ascii=False) if hardware_info.get('memory') else ''
        disk_info = json.dumps(hardware_info.get('disk', []), ensure_ascii=False) if hardware_info.get('disk') else ''
        gpu_info = json.dumps(hardware_info.get('gpu', []), ensure_ascii=False) if hardware_info.get('gpu') else ''

        cursor.execute('''
            INSERT INTO hardware_history (client_id, cpu_info, memory_info, disk_info, gpu_info, snapshot)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (client_id, cpu_info, mem_info, disk_info, gpu_info, json.dumps(hardware_info, ensure_ascii=False)))
        conn.commit()

        conn.close()

        # 异步硬件变更检测
        hw_detection_executor.submit(
            check_hardware_changes_async,
            client_id, hostname, local_ip, hardware_info,
            cpu_info, gpu_info, mem_info, disk_info
        )

        # 清除相关缓存
        from cache_invalidation import on_client_update
        on_client_update(client_id)

        return {'status': 'success', 'client_id': client_id}

    except Exception as exc:
        logger.error(f'处理客户端上报失败: {exc}')
        self.retry(exc=exc, countdown=60)


@task_or_func
def process_process_alert(self, client_id, hostname, local_ip, alerts, system_summary):
    """异步处理进程告警"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 确保客户端存在
        current_time = datetime.now(TZ_CST).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO clients (client_id, hostname, local_ip, last_report)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                hostname = VALUES(hostname),
                local_ip = VALUES(local_ip),
                last_report = VALUES(last_report)
        ''', (client_id, hostname, local_ip, current_time))

        # 保存进程告警
        alert_data = json.dumps({
            "alerts": alerts,
            "system_summary": system_summary,
            "timestamp": datetime.now(TZ_CST).isoformat()
        }, ensure_ascii=False)

        cursor.execute('''
            INSERT INTO process_alert_records (client_id, hostname, local_ip, alert_data, alert_count)
            VALUES (%s, %s, %s, %s, %s)
        ''', (client_id, hostname, local_ip, alert_data, len(alerts)))

        alert_id = cursor.lastrowid
        conn.commit()

        conn.close()

        # 异步 AI 分析
        ai_analysis_executor.submit(
            async_ai_analyze,
            alert_id, client_id, alert_data
        )

        return {'status': 'success', 'alert_id': alert_id}

    except Exception as exc:
        logger.error(f'处理进程告警失败: {exc}')
        self.retry(exc=exc, countdown=60)


@task_or_func
def probe_all_targets():
    """异步探测所有目标"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM probe_targets WHERE enabled = 1')
        targets = [dict(row) for row in cursor.fetchall()]

        if not targets:
            conn.close()
            return {'status': 'no_targets'}

        # 并发探测
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(_probe_single_target, target): target['id']
                for target in targets
            }

            for future in as_completed(futures):
                target_id = futures[future]
                try:
                    result = future.result()
                    cursor.execute('''
                        UPDATE probe_targets
                        SET last_status=%s, last_probe_time=NOW(), last_response_time=%s
                        WHERE id=%s
                    ''', (result['status'], result.get('response_time'), target_id))

                    if result['status'] == 'offline':
                        cursor.execute('''
                            SELECT id FROM probe_alerts
                            WHERE target_id = %s AND resolved = 0 LIMIT 1
                        ''', (target_id,))
                        if not cursor.fetchone():
                            cursor.execute('''
                                INSERT INTO probe_alerts (target_id, target_name, target_host, alert_type, error_message)
                                VALUES (%s,%s,%s,%s,%s)
                            ''', (target_id, result.get('name'), result.get('host'), 'offline', result.get('error', '')))
                    else:
                        cursor.execute('''
                            UPDATE probe_alerts SET resolved = 1
                            WHERE target_id = %s AND resolved = 0 AND alert_type = "offline"
                        ''', (target_id,))
                except Exception as e:
                    logger.warning(f'探测目标 {target_id} 失败: {e}')

        conn.commit()
        conn.close()
        return {'status': 'success', 'probed': len(targets)}

    except Exception as e:
        logger.error(f'探测所有目标失败: {e}')
        return {'status': 'error', 'message': str(e)}


@task_or_func
def cleanup_old_records():
    """清理旧记录（使用批量删除优化）"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 批量删除超过10条的旧记录
        cursor.execute('''
            DELETE FROM hardware_history
            WHERE id IN (
                SELECT id FROM (
                    SELECT id FROM hardware_history
                    WHERE client_id IN (
                        SELECT client_id FROM hardware_history
                        GROUP BY client_id
                        HAVING COUNT(*) > 10
                    )
                    ORDER BY timestamp DESC
                    LIMIT 10000
                ) AS t
            )
        ''')

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        logger.info(f'清理完成: 删除了 {affected} 条记录')
        return {'status': 'success', 'deleted': affected}

    except Exception as e:
        logger.error(f'清理旧记录失败: {e}')
        return {'status': 'error', 'message': str(e)}


def _probe_single_target(target):
    """探测单个目标"""
    import requests

    protocol = target.get('protocol', 'http')
    host = target['host']
    port = target.get('port', 80)
    path = target.get('path', '/')
    url = f"{protocol}://{host}:{port}{path}"

    try:
        start = time.time()
        response = requests.get(url, timeout=10, verify=False)
        response_time = int((time.time() - start) * 1000)

        return {
            'status': 'online',
            'response_time': response_time,
            'name': target.get('name'),
            'host': host
        }
    except requests.exceptions.Timeout:
        return {
            'status': 'timeout',
            'response_time': None,
            'error': '连接超时',
            'name': target.get('name'),
            'host': host
        }
    except Exception as e:
        return {
            'status': 'offline',
            'response_time': None,
            'error': str(e),
            'name': target.get('name'),
            'host': host
        }


def check_hardware_changes_async(client_id, hostname, local_ip, hardware_info,
                                  cpu_info, gpu_info, mem_info, disk_info):
    """异步硬件变更检测"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 获取基准数据
        cursor.execute('SELECT * FROM client_baselines WHERE client_id = %s', (client_id,))
        baseline = cursor.fetchone()

        if not baseline:
            # 首次上报，创建基准
            cursor.execute('''
                INSERT INTO client_baselines (client_id, cpu_snapshot, gpu_snapshot, memory_snapshot, disk_snapshot)
                VALUES (%s, %s, %s, %s, %s)
            ''', (client_id, cpu_info, gpu_info, mem_info, disk_info))
            conn.commit()
            logger.info(f'客户端 {client_id} 首次上报，已创建基准')
        else:
            # 检查硬件变更
            from app import compare_hardware

            # 获取告警设置（带缓存）
            alert_settings = get_alert_settings_cached()

            baseline_snapshots = {
                'cpu': baseline['cpu_snapshot'],
                'gpu': baseline['gpu_snapshot'],
                'memory': baseline['memory_snapshot'],
                'disk': baseline['disk_snapshot'],
            }

            changes = compare_hardware(baseline_snapshots, hardware_info, alert_settings)

            if changes and alert_settings.get('alert_enabled', 1):
                # 记录告警
                alert_detail = json.dumps(changes, ensure_ascii=False)
                cursor.execute('''
                    INSERT INTO alert_records (client_id, alert_type, alert_detail)
                    VALUES (%s, %s, %s)
                ''', (client_id, 'hardware_change', alert_detail))
                conn.commit()
                logger.info(f'客户端 {client_id} 硬件变更: {len(changes)} 项')

        conn.close()

    except Exception as e:
        logger.warning(f'异步硬件检测失败 {client_id}: {e}')


def get_alert_settings_cached():
    """获取告警设置（带缓存）"""
    # 尝试从缓存获取
    cache_key = 'hwmon:alert_settings:1'
    cached = get_cache(cache_key)
    if cached:
        return cached

    # 缓存未命中，查询数据库
    try:
        conn = get_db_readonly()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM alert_settings WHERE id = 1')
        row = cursor.fetchone()
        conn.close()

        settings = dict(row) if row else {
            'alert_enabled': 1,
            'email_enabled': 0,
            'monitor_cpu': 1,
            'monitor_gpu': 1,
            'monitor_memory': 1,
            'monitor_disk': 1,
            'monitor_network': 0,
            'monitor_motherboard': 0,
            'monitor_bios': 0,
            'monitor_temperature': 0,
            'monitor_fan': 0,
            'monitor_voltage': 0
        }

        # 写入缓存（5分钟TTL）
        set_cache(cache_key, settings, ttl=300)

        return settings

    except Exception as e:
        logger.warning(f'获取告警设置失败: {e}')
        return {
            'alert_enabled': 1,
            'email_enabled': 0,
            'monitor_cpu': 1,
            'monitor_gpu': 1,
            'monitor_memory': 1,
            'monitor_disk': 1,
        }


def async_ai_analyze(alert_id, client_id, alert_data):
    """异步 AI 分析"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 检查是否在 AI 监控列表
        cursor.execute('SELECT id FROM ai_monitored_hosts WHERE client_id = %s AND enabled = 1', (client_id,))
        if not cursor.fetchone():
            conn.close()
            return

        # 获取 AI 配置
        cursor.execute('SELECT * FROM ai_config WHERE id = 1')
        ai_cfg = cursor.fetchone()
        if not ai_cfg or not ai_cfg.get('enabled') or not ai_cfg.get('auto_analyze'):
            conn.close()
            return

        from ai_analyzer import analyze_process_alert
        alert_json = json.loads(alert_data)
        result = analyze_process_alert(alert_json, dict(ai_cfg))

        if result:
            cursor.execute('''
                UPDATE process_alert_records
                SET ai_analyzed = 1, ai_result = %s
                WHERE id = %s
            ''', (json.dumps(result, ensure_ascii=False), alert_id))
            conn.commit()

        conn.close()

    except Exception as e:
        logger.warning(f'AI 异步分析失败 (alert_id={alert_id}): {e}')
