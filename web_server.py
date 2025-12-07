#!/usr/bin/env python3
"""
ComicPacker Web Server
提供Web界面用于管理漫画转换任务
"""

import os
import json
import time
import threading
import queue
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Callable
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import uuid

# 导入主程序的转换函数
from main import (
    pack_comics_to_pdf,
    pack_comics_by_book,
    convert_cbz_to_pdf,
    get_sorted_zip_files
)

app = Flask(__name__)
CORS(app)

# 全局变量
job_queue = queue.Queue()
jobs: Dict[str, dict] = {}
jobs_lock = threading.Lock()
cancelled_jobs = set()  # 跟踪被取消的任务


class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.messages = []
        
    def update(self, stage: str, current: int, total: int, message: str):
        """更新进度"""
        # 检查任务是否被取消
        if self.job_id in cancelled_jobs:
            print(f"[TRACKER] Job {self.job_id} cancellation detected")
            raise Exception(f"Job {self.job_id} was cancelled by user")
        
        with jobs_lock:
            if self.job_id in jobs:
                jobs[self.job_id]['progress'] = {
                    'stage': stage,
                    'current': current,
                    'total': total,
                    'message': message,
                    'percentage': int((current / total * 100) if total > 0 else 0)
                }
                jobs[self.job_id]['last_update'] = datetime.now().isoformat()
                
                # 添加到消息历史
                log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
                self.messages.append(log_entry)
                jobs[self.job_id]['logs'].append(log_entry)


def worker_thread():
    """后台工作线程，处理转换任务"""
    print("[WORKER] Worker thread started")
    while True:
        try:
            print("[WORKER] Waiting for job from queue...")
            job_id = job_queue.get()
            print(f"[WORKER] Got job from queue: {job_id}")
            
            with jobs_lock:
                if job_id not in jobs:
                    print(f"[WORKER] Job {job_id} not found in jobs dict, skipping")
                    continue
                    
                job = jobs[job_id]
                
                # 检查任务是否已被取消
                if job_id in cancelled_jobs:
                    print(f"[WORKER] Job {job_id} was cancelled before starting")
                    job['status'] = 'cancelled'
                    job['end_time'] = datetime.now().isoformat()
                    job['error'] = '任务已取消'
                    # 更新进度以通知前端
                    job['progress'] = {
                        'stage': 'cancelled',
                        'current': 0,
                        'total': 100,
                        'message': '任务在启动前被取消',
                        'percentage': 0
                    }
                    job['last_update'] = datetime.now().isoformat()
                    cancelled_jobs.discard(job_id)
                    job_queue.task_done()
                    continue
                
                job['status'] = 'running'
                job['start_time'] = datetime.now().isoformat()
                print(f"[WORKER] Job {job_id} status set to running")
                print(f"[WORKER] Job parameters: {job['parameters']}")
            
            # 创建进度跟踪器
            tracker = ProgressTracker(job_id)
            
            try:
                # 执行转换任务
                params = job['parameters']
                mode = params.get('mode', 'batch')
                
                print(f"[WORKER] Starting conversion in {mode} mode")
                tracker.update('init', 0, 100, f'开始 {mode} 模式转换...')
                
                if mode == 'batch':
                    print("[WORKER] Calling pack_comics_to_pdf_with_progress")
                    pack_comics_to_pdf_with_progress(
                        folder_path=params['folder'],
                        batch_size=params.get('batch_size', 10),
                        pdf_prefix=params.get('prefix', ''),
                        output_folder=params.get('output', './output'),
                        convert_to_mobi=params.get('convert_to_mobi', False),
                        kindle_profile=params.get('kindle_profile', 'KPW5'),
                        progress_callback=tracker.update
                    )
                elif mode == 'book':
                    print("[WORKER] Calling pack_comics_by_book_with_progress")
                    pack_comics_by_book_with_progress(
                        folder_path=params['folder'],
                        pdf_prefix=params.get('prefix', ''),
                        output_folder=params.get('output', './output'),
                        convert_to_mobi=params.get('convert_to_mobi', False),
                        kindle_profile=params.get('kindle_profile', 'KPW5'),
                        progress_callback=tracker.update
                    )
                elif mode == 'cbz':
                    print("[WORKER] Calling convert_cbz_to_pdf_with_progress")
                    convert_cbz_to_pdf_with_progress(
                        folder_path=params['folder'],
                        cbz_prefix=params.get('prefix', ''),
                        output_folder=params.get('output', './output'),
                        convert_to_mobi=params.get('convert_to_mobi', False),
                        kindle_profile=params.get('kindle_profile', 'KPW5'),
                        progress_callback=tracker.update
                    )
                
                # 任务完成
                print(f"[WORKER] Job {job_id} completed successfully")
                with jobs_lock:
                    # main.py已经通过progress_callback调用了completed状态
                    # 这里只需要确保status被设置（如果main.py没有设置的话）
                    if jobs[job_id]['status'] != 'completed':
                        jobs[job_id]['status'] = 'completed'
                    jobs[job_id]['end_time'] = datetime.now().isoformat()
                    if 'percentage' in jobs[job_id]['progress']:
                        jobs[job_id]['progress']['percentage'] = 100
                    
            except Exception as e:
                # 检查是否是取消异常
                if "cancelled" in str(e).lower() or job_id in cancelled_jobs:
                    print(f"[WORKER] Job {job_id} was cancelled")
                    with jobs_lock:
                        jobs[job_id]['status'] = 'cancelled'
                        jobs[job_id]['end_time'] = datetime.now().isoformat()
                        jobs[job_id]['error'] = '任务已取消'
                        # 更新进度以通知前端
                        jobs[job_id]['progress'] = {
                            'stage': 'cancelled',
                            'current': 0,
                            'total': 100,
                            'message': '任务已被用户取消',
                            'percentage': 0
                        }
                        jobs[job_id]['last_update'] = datetime.now().isoformat()
                        cancelled_jobs.discard(job_id)
                else:
                    # 任务失败
                    print(f"[WORKER] Job {job_id} failed with error: {e}")
                    import traceback
                    traceback.print_exc()
                    with jobs_lock:
                        jobs[job_id]['status'] = 'failed'
                        jobs[job_id]['end_time'] = datetime.now().isoformat()
                        jobs[job_id]['error'] = str(e)
                        tracker.update('error', 0, 100, f'转换失败: {str(e)}')
            
            finally:
                job_queue.task_done()
                print(f"[WORKER] Job {job_id} processing finished, task_done called")
                
        except Exception as e:
            print(f"[WORKER] Worker thread error: {e}")
            import traceback
            traceback.print_exc()


# 启动工作线程
worker = threading.Thread(target=worker_thread, daemon=True)
worker.start()


# ============= 带进度回调的转换函数 =============

def pack_comics_to_pdf_with_progress(folder_path: str, batch_size: int = 10, 
                                     pdf_prefix: str = "", output_folder: str = './output',
                                     convert_to_mobi: bool = False, kindle_profile: str = 'KPW5',
                                     progress_callback: Optional[Callable] = None):
    """批次模式转换（带进度回调）"""
    pack_comics_to_pdf(folder_path, batch_size, pdf_prefix, output_folder,
                      convert_to_mobi, kindle_profile, progress_callback)


def pack_comics_by_book_with_progress(folder_path: str, pdf_prefix: str = "",
                                      output_folder: str = './output',
                                      convert_to_mobi: bool = False, 
                                      kindle_profile: str = 'KPW5',
                                      progress_callback: Optional[Callable] = None):
    """按书打包模式（带进度回调）"""
    print(f"[CONVERT] pack_comics_by_book_with_progress called with folder: {folder_path}")
    
    # 直接调用main.py中的函数，它会通过progress_callback报告所有进度
    pack_comics_by_book(folder_path, pdf_prefix, output_folder, 
                       convert_to_mobi, kindle_profile, progress_callback)


def convert_cbz_to_pdf_with_progress(folder_path: str, cbz_prefix: str = "",
                                     output_folder: str = './output',
                                     convert_to_mobi: bool = False,
                                     kindle_profile: str = 'KPW5',
                                     progress_callback: Optional[Callable] = None):
    """CBZ转PDF模式（带进度回调）"""
    convert_cbz_to_pdf(folder_path, cbz_prefix, output_folder, 
                        convert_to_mobi, kindle_profile, progress_callback)


# ============= API路由 =============

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/browse', methods=['POST'])
def browse_files():
    """浏览服务器文件系统"""
    try:
        data = request.json
        #todo need fix to set default path
        path = data.get('path', '/vol2/1000/qb/down/comic/')
        
        # 安全检查：防止访问系统敏感目录
        abs_path = os.path.abspath(path)
        
        if not os.path.exists(abs_path):
            return jsonify({'error': '路径不存在'}), 404
        
        if not os.path.isdir(abs_path):
            return jsonify({'error': '不是目录'}), 400
        
        # 列出目录内容
        items = []
        try:
            for item in sorted(os.listdir(abs_path)):
                item_path = os.path.join(abs_path, item)
                is_dir = os.path.isdir(item_path)
                
                # 统计文件信息
                file_count = 0
                if is_dir:
                    try:
                        # 统计ZIP/CBZ文件数量
                        file_count = len([f for f in os.listdir(item_path) 
                                        if f.endswith(('.zip', '.cbz'))])
                    except:
                        file_count = 0
                
                items.append({
                    'name': item,
                    'path': item_path,
                    'is_dir': is_dir,
                    'file_count': file_count if is_dir else None
                })
        except PermissionError:
            return jsonify({'error': '没有权限访问此目录'}), 403
        
        return jsonify({
            'path': abs_path,
            'parent': str(Path(abs_path).parent) if abs_path != '/' else None,
            'items': items
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/detect-mode', methods=['POST'])
def detect_mode():
    """检测文件夹内容并返回推荐的转换模式"""
    try:
        data = request.json
        folder_path = data.get('path')
        
        if not folder_path or not os.path.exists(folder_path):
            return jsonify({'error': '路径不存在'}), 404
        
        if not os.path.isdir(folder_path):
            return jsonify({'error': '不是目录'}), 400
        
        # 统计文件类型
        cbz_count = 0
        zip_count = 0
        vol_files_count = 0  # 统计以Vol开头的文件
        
        try:
            for item in os.listdir(folder_path):
                item_lower = item.lower()
                
                # 检查是否以Vol开头
                if item.startswith('Vol') or item.startswith('vol'):
                    vol_files_count += 1
                
                if item_lower.endswith('.cbz'):
                    cbz_count += 1
                elif item_lower.endswith('.zip'):
                    zip_count += 1
        except PermissionError:
            return jsonify({'error': '没有权限访问此目录'}), 403
        
        # 根据文件类型推荐模式
        if cbz_count > 0:
            recommended_mode = 'cbz'
        elif zip_count > 0:
            recommended_mode = 'book'
        else:
            recommended_mode = 'book'  # 默认
        
        return jsonify({
            'recommended_mode': recommended_mode,
            'cbz_count': cbz_count,
            'zip_count': zip_count,
            'total_files': cbz_count + zip_count,
            'has_vol_files': vol_files_count > 0,
            'vol_files_count': vol_files_count
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/system-stats', methods=['GET'])
def get_system_stats():
    """获取系统资源使用情况"""
    try:
        import psutil
        
        # 获取CPU使用率（1秒采样）
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # 获取内存使用情况
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_gb = memory.used / (1024 ** 3)
        memory_total_gb = memory.total / (1024 ** 3)
        
        return jsonify({
            'cpu_percent': round(cpu_percent, 1),
            'memory_percent': round(memory_percent, 1),
            'memory_used_gb': round(memory_used_gb, 2),
            'memory_total_gb': round(memory_total_gb, 2)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    """获取所有任务"""
    with jobs_lock:
        # 返回所有任务，按创建时间倒序
        job_list = sorted(jobs.values(), key=lambda x: x['created_time'], reverse=True)
        return jsonify({'jobs': job_list})


@app.route('/api/jobs/clear', methods=['POST'])
def clear_jobs():
    """清除所有已完成、失败和取消的任务"""
    try:
        with jobs_lock:
            # 只保留正在运行和等待中的任务
            jobs_to_keep = {
                job_id: job for job_id, job in jobs.items()
                if job['status'] in ['running', 'pending']
            }
            jobs.clear()
            jobs.update(jobs_to_keep)
            
            cleared_count = len(jobs) - len(jobs_to_keep)
            print(f"[API] Cleared {cleared_count} completed jobs")
            
            return jsonify({
                'success': True,
                'message': f'已清除 {cleared_count} 条历史记录'
            })
    except Exception as e:
        print(f"[API] Error clearing jobs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs', methods=['POST'])
def create_job():
    """创建新的转换任务"""
    try:
        params = request.json
        print(f"[DEBUG] 收到转换请求: {params}")  # 调试日志
        
        # 验证参数
        if 'folder' not in params:
            print("[DEBUG] 错误: 缺少folder参数")
            return jsonify({'error': '缺少folder参数'}), 400
        
        if not os.path.exists(params['folder']):
            print(f"[DEBUG] 错误: 文件夹不存在 - {params['folder']}")
            return jsonify({'error': '文件夹不存在'}), 400
        
        # 创建任务
        job_id = str(uuid.uuid4())
        print(f"[DEBUG] 创建任务 ID: {job_id}")
        
        job = {
            'id': job_id,
            'status': 'pending',
            'parameters': params,
            'created_time': datetime.now().isoformat(),
            'start_time': None,
            'end_time': None,
            'progress': {
                'stage': 'pending',
                'current': 0,
                'total': 100,
                'message': '等待开始...',
                'percentage': 0
            },
            'logs': [],
            'error': None
        }
        
        with jobs_lock:
            jobs[job_id] = job
        
        # 添加到队列
        job_queue.put(job_id)
        print(f"[DEBUG] 任务已添加到队列，当前队列大小: {job_queue.qsize()}")
        
        return jsonify({
            'job_id': job_id,
            'status': 'pending'
        })
        
    except Exception as e:
        print(f"[DEBUG] 创建任务时出错: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """获取任务详情"""
    with jobs_lock:
        if job_id not in jobs:
            return jsonify({'error': '任务不存在'}), 404
        return jsonify(jobs[job_id])


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    """取消任务"""
    try:
        with jobs_lock:
            if job_id not in jobs:
                return jsonify({'error': '任务不存在'}), 404
            
            job = jobs[job_id]
            
            # 只能取消运行中或等待中的任务
            if job['status'] not in ['pending', 'running']:
                return jsonify({'error': f"无法取消状态为 {job['status']} 的任务"}), 400
            
            # 标记任务为取消
            cancelled_jobs.add(job_id)
            print(f"[API] Job {job_id} marked for cancellation")
            
            return jsonify({
                'success': True,
                'message': '任务取消请求已发送'
            })
            
    except Exception as e:
        print(f"[API] Error cancelling job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    """删除任务"""
    try:
        with jobs_lock:
            if job_id not in jobs:
                return jsonify({'error': '任务不存在'}), 404
            
            job = jobs[job_id]
            
            # 只能删除已完成、失败或取消的任务
            if job['status'] in ['pending', 'running']:
                return jsonify({'error': f"无法删除状态为 {job['status']} 的任务"}), 400
            
            # 删除任务
            del jobs[job_id]
            print(f"[API] Job {job_id} deleted")
            
            return jsonify({
                'success': True,
                'message': '任务已删除'
            })
            
    except Exception as e:
        print(f"[API] Error deleting job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/progress/<job_id>')
def progress_stream(job_id):
    """SSE进度流"""
    def generate():
        last_update = None
        
        while True:
            with jobs_lock:
                if job_id not in jobs:
                    yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                    break
                
                job = jobs[job_id]
                current_update = job.get('last_update')
                
                # 只在有更新时发送
                if current_update != last_update:
                    last_update = current_update
                    yield f"data: {json.dumps(job)}\n\n"
                    
                    # 在发送更新后检查是否为终止状态
                    if job['status'] in ['completed', 'failed', 'cancelled']:
                        time.sleep(1)  # 确保客户端收到最后的更新
                        break
            
            time.sleep(0.5)  # 每0.5秒检查一次
    
    return Response(generate(), mimetype='text/event-stream')


if __name__ == '__main__':
    print("=" * 60)
    print("ComicPacker Web Server")
    print("=" * 60)
    print("服务器地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
