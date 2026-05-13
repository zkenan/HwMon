"""
硬件监控系统服务端
Flask Web应用,提供API和Web管理界面
支持高并发采集(1000+客户端)
"""

import os
import json
import sqlite3
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import io
import csv
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app)

DATABASE = 'hardware_monitor.db'

# 并发采集配置
COLLECT_CONFIG = {
    'max_workers': 50,        # 最大并发数(50并发约30秒完成1000台)
    'timeout': 15,            # 单个客户端请求超时(秒)
    'retry_times': 0,         # 失败重试次数
}


def init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # 创建分组表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 创建客户端表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL UNIQUE,
            hostname TEXT,
            local_ip TEXT,
            group_id INTEGER,
            last_report TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL
        )
    ''')

    # 检查并添加local_ip列(兼容旧数据库)
    try:
        cursor.execute("ALTER TABLE clients ADD COLUMN local_ip TEXT")
    except:
        pass

    # 创建硬件信息历史表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hardware_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            report_data TEXT,
            report_type TEXT DEFAULT 'scheduled',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
        )
    ''')

    # 检查并添加report_type列(兼容旧数据库)
    try:
        cursor.execute("ALTER TABLE hardware_reports ADD COLUMN report_type TEXT DEFAULT 'scheduled'")
    except:
        pass

    # 创建默认分组
    cursor.execute('INSERT OR IGNORE INTO groups (name, description) VALUES (?, ?)',
                   ('默认分组', '未分组的客户端'))

    conn.commit()
    conn.close()


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def collect_single_client(client_id, local_ip):
    """采集单个客户端(用于并发执行)"""
    if not local_ip:
        return {
            'client_id': client_id,
            'status': 'unknown_ip',
            'message': 'IP地址未知'
        }

    try:
        response = requests.post(
            f'http://{local_ip}:13301/api/collect',
            json={'trigger': 'server'},
            timeout=COLLECT_CONFIG['timeout']
        )

        if response.status_code == 200:
            return {
                'client_id': client_id,
                'status': 'success',
                'message': '采集成功'
            }
        else:
            return {
                'client_id': client_id,
                'status': 'failed',
                'message': f'HTTP {response.status_code}'
            }

    except requests.exceptions.Timeout:
        return {
            'client_id': client_id,
            'status': 'timeout',
            'message': '连接超时'
        }
    except requests.exceptions.ConnectionError:
        return {
            'client_id': client_id,
            'status': 'offline',
            'message': '无法连接,客户端可能离线或防火墙阻止'
        }
    except Exception as e:
        return {
            'client_id': client_id,
            'status': 'error',
            'message': str(e)
        }


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/report', methods=['POST'])
def receive_report():
    """接收客户端上报的硬件信息"""
    try:
        data = request.json
        client_id = data.get('client_id')
        hostname = data.get('hostname')
        hardware_info = data.get('hardware_info')
        local_ip = data.get('local_ip', '')
        report_type = data.get('report_type', 'scheduled')

        if not client_id:
            return jsonify({'error': '缺少client_id'}), 400

        conn = get_db()
        cursor = conn.cursor()

        # 更新或插入客户端信息
        cursor.execute('''
            INSERT INTO clients (client_id, hostname, local_ip, last_report)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                hostname = excluded.hostname,
                local_ip = excluded.local_ip,
                last_report = excluded.last_report
        ''', (client_id, hostname, local_ip, datetime.now().isoformat()))

        # 保存硬件信息历史记录
        cursor.execute('''
            INSERT INTO hardware_reports (client_id, report_data, report_type)
            VALUES (?, ?, ?)
        ''', (client_id, json.dumps(hardware_info, ensure_ascii=False), report_type))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': '接收成功'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients', methods=['GET'])
def get_clients():
    """获取所有客户端列表"""
    try:
        group_id = request.args.get('group_id')
        conn = get_db()
        cursor = conn.cursor()

        if group_id:
            cursor.execute('''
                SELECT c.*, g.name as group_name
                FROM clients c
                LEFT JOIN groups g ON c.group_id = g.id
                WHERE c.group_id = ?
                ORDER BY c.last_report DESC
            ''', (group_id,))
        else:
            cursor.execute('''
                SELECT c.*, g.name as group_name
                FROM clients c
                LEFT JOIN groups g ON c.group_id = g.id
                ORDER BY c.last_report DESC
            ''')

        clients = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({'status': 'success', 'data': clients})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/client/<client_id>', methods=['GET'])
def get_client_detail(client_id):
    """获取客户端详细信息"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 获取客户端基本信息
        cursor.execute('''
            SELECT c.*, g.name as group_name
            FROM clients c
            LEFT JOIN groups g ON c.group_id = g.id
            WHERE c.client_id = ?
        ''', (client_id,))

        client = cursor.fetchone()
        if not client:
            conn.close()
            return jsonify({'error': '客户端不存在'}), 404

        client_info = dict(client)

        # 获取最新的硬件报告
        cursor.execute('''
            SELECT report_data, report_type, timestamp
            FROM hardware_reports
            WHERE client_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (client_id,))

        report = cursor.fetchone()
        if report:
            client_info['latest_hardware'] = json.loads(report['report_data'])
            client_info['last_hardware_update'] = report['timestamp']
            client_info['last_report_type'] = report['report_type']

        conn.close()

        return jsonify({'status': 'success', 'data': client_info})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/collect/<client_id>', methods=['POST'])
def collect_from_client(client_id):
    """主动采集单个客户端"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 获取客户端信息
        cursor.execute('SELECT local_ip FROM clients WHERE client_id = ?', (client_id,))
        client = cursor.fetchone()

        if not client:
            conn.close()
            return jsonify({'error': '客户端不存在'}), 404

        local_ip = client['local_ip']
        conn.close()

        if not local_ip:
            return jsonify({'error': '客户端IP地址未知,无法采集'}), 400

        # 使用并发函数采集单个客户端
        result = collect_single_client(client_id, local_ip)

        if result['status'] == 'success':
            return jsonify({
                'status': 'success',
                'message': f'已向客户端 {client_id} 发送采集请求',
                'client_response': result
            })
        else:
            status_code = 500
            if result['status'] == 'timeout':
                status_code = 408
            elif result['status'] in ('offline', 'unknown_ip'):
                status_code = 404

            return jsonify({
                'status': result['status'],
                'message': result['message']
            }), status_code

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/collect/all', methods=['POST'])
def collect_all_clients():
    """一键采集: 并发向所有客户端发送采集请求"""
    try:
        # 获取采集参数(支持自定义并发数和超时)
        params = request.json or {}
        max_workers = params.get('max_workers', COLLECT_CONFIG['max_workers'])
        timeout = params.get('timeout', COLLECT_CONFIG['timeout'])

        # 临时覆盖配置
        old_workers = COLLECT_CONFIG['max_workers']
        old_timeout = COLLECT_CONFIG['timeout']
        COLLECT_CONFIG['max_workers'] = max_workers
        COLLECT_CONFIG['timeout'] = timeout

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('SELECT client_id, local_ip FROM clients')
        clients = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if not clients:
            COLLECT_CONFIG['max_workers'] = old_workers
            COLLECT_CONFIG['timeout'] = old_timeout
            return jsonify({
                'status': 'completed',
                'total': 0,
                'success': 0,
                'failed': 0,
                'results': [],
                'elapsed_seconds': 0
            })

        start_time = time.time()
        results = []

        # 使用线程池并发采集
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有采集任务
            futures = {
                executor.submit(collect_single_client, c['client_id'], c['local_ip']): c['client_id']
                for c in clients
            }

            # 收集结果
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({
                        'client_id': futures[future],
                        'status': 'error',
                        'message': str(e)
                    })

        elapsed = time.time() - start_time

        # 统计结果
        success_count = sum(1 for r in results if r['status'] == 'success')
        fail_count = len(results) - success_count

        # 恢复配置
        COLLECT_CONFIG['max_workers'] = old_workers
        COLLECT_CONFIG['timeout'] = old_timeout

        return jsonify({
            'status': 'completed',
            'total': len(clients),
            'success': success_count,
            'failed': fail_count,
            'elapsed_seconds': round(elapsed, 2),
            'concurrency': max_workers,
            'results': results
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/groups', methods=['GET'])
def get_groups():
    """获取所有分组"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT g.*, COUNT(c.id) as client_count
            FROM groups g
            LEFT JOIN clients c ON g.id = c.group_id
            GROUP BY g.id
            ORDER BY g.name
        ''')

        groups = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({'status': 'success', 'data': groups})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/groups', methods=['POST'])
def create_group():
    """创建新分组"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description', '')

        if not name:
            return jsonify({'error': '分组名称不能为空'}), 400

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('INSERT INTO groups (name, description) VALUES (?, ?)',
                       (name, description))

        conn.commit()
        group_id = cursor.lastrowid
        conn.close()

        return jsonify({'status': 'success', 'group_id': group_id})

    except sqlite3.IntegrityError:
        return jsonify({'error': '分组名称已存在'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/groups/<int:group_id>', methods=['PUT'])
def update_group(group_id):
    """更新分组"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description')

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('UPDATE groups SET name = ?, description = ? WHERE id = ?',
                       (name, description, group_id))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
def delete_group(group_id):
    """删除分组"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 检查是否是默认分组
        cursor.execute('SELECT name FROM groups WHERE id = ?', (group_id,))
        group = cursor.fetchone()
        if group and group['name'] == '默认分组':
            conn.close()
            return jsonify({'error': '不能删除默认分组'}), 400

        cursor.execute('DELETE FROM groups WHERE id = ?', (group_id,))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/<client_id>/group', methods=['PUT'])
def assign_client_to_group(client_id):
    """将客户端分配到分组"""
    try:
        data = request.json
        group_id = data.get('group_id')

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('UPDATE clients SET group_id = ? WHERE client_id = ?',
                       (group_id, client_id))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/<client_id>', methods=['DELETE'])
def delete_client(client_id):
    """删除客户端"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM clients WHERE client_id = ?', (client_id,))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/csv', methods=['GET'])
def export_csv():
    """导出所有客户端信息为CSV"""
    try:
        group_id = request.args.get('group_id')
        conn = get_db()
        cursor = conn.cursor()

        if group_id:
            cursor.execute('''
                SELECT c.client_id, c.hostname, c.local_ip, g.name as group_name,
                       c.last_report, c.created_at
                FROM clients c
                LEFT JOIN groups g ON c.group_id = g.id
                WHERE c.group_id = ?
                ORDER BY c.last_report DESC
            ''', (group_id,))
        else:
            cursor.execute('''
                SELECT c.client_id, c.hostname, c.local_ip, g.name as group_name,
                       c.last_report, c.created_at
                FROM clients c
                LEFT JOIN groups g ON c.group_id = g.id
                ORDER BY c.last_report DESC
            ''')

        clients = cursor.fetchall()

        # 创建CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['客户端ID(主机名)', 'IP地址', '分组', '最后上报时间', '创建时间'])

        for client in clients:
            writer.writerow([
                client['client_id'],
                client['local_ip'] or '-',
                client['group_name'] or '未分组',
                client['last_report'],
                client['created_at']
            ])

        conn.close()

        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'hardware_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/json', methods=['GET'])
def export_json():
    """导出所有客户端信息为JSON"""
    try:
        group_id = request.args.get('group_id')
        conn = get_db()
        cursor = conn.cursor()

        if group_id:
            cursor.execute('''
                SELECT c.*, g.name as group_name
                FROM clients c
                LEFT JOIN groups g ON c.group_id = g.id
                WHERE c.group_id = ?
                ORDER BY c.last_report DESC
            ''', (group_id,))
        else:
            cursor.execute('''
                SELECT c.*, g.name as group_name
                FROM clients c
                LEFT JOIN groups g ON c.group_id = g.id
                ORDER BY c.last_report DESC
            ''')

        clients = [dict(row) for row in cursor.fetchall()]

        # 获取每个客户端的最新硬件信息
        for client in clients:
            cursor.execute('''
                SELECT report_data, report_type, timestamp
                FROM hardware_reports
                WHERE client_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (client['client_id'],))

            report = cursor.fetchone()
            if report:
                client['latest_hardware'] = json.loads(report['report_data'])
                client['last_hardware_update'] = report['timestamp']
                client['last_report_type'] = report['report_type']

        conn.close()

        return send_file(
            io.BytesIO(json.dumps(clients, ensure_ascii=False, indent=2).encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'hardware_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['GET'])
def get_collect_config():
    """获取采集配置"""
    return jsonify({
        'status': 'success',
        'data': {
            'max_workers': COLLECT_CONFIG['max_workers'],
            'timeout': COLLECT_CONFIG['timeout'],
            'retry_times': COLLECT_CONFIG['retry_times']
        }
    })


if __name__ == '__main__':
    init_db()
    print("=" * 60)
    print("硬件监控系统服务端启动")
    print("访问地址: http://localhost:5000")
    print(f"并发配置: {COLLECT_CONFIG['max_workers']} workers, {COLLECT_CONFIG['timeout']}s timeout")
    print("=" * 60)

    try:
        # 生产环境: 使用waitress WSGI服务器(支持高并发,默认20线程)
        from waitress import serve
        print("使用 Waitress WSGI 服务器(生产模式)")
        serve(app, host='0.0.0.0', port=5000, threads=20, connection_limit=2000)
    except ImportError:
        # 开发环境: 使用Flask内置服务器
        print("Waitress未安装,使用Flask内置服务器(开发模式)")
        print("提示: pip install waitress 以启用高并发支持")
        app.run(host='0.0.0.0', port=5000, debug=True)
