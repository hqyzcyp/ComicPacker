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


class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.messages = []
        
    def update(self, stage: str, current: int, total: int, message: str):
        """更新进度"""
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
                    jobs[job_id]['status'] = 'completed'
                    jobs[job_id]['end_time'] = datetime.now().isoformat()
                    jobs[job_id]['progress']['percentage'] = 100
                    tracker.update('completed', 100, 100, '转换完成！')
                    
            except Exception as e:
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
    os.makedirs(output_folder, exist_ok=True)
    zip_files = get_sorted_zip_files(folder_path)
    
    if not zip_files:
        raise ValueError(f"在 {folder_path} 中没有找到ZIP文件")
    
    total_batches = (len(zip_files) + batch_size - 1) // batch_size
    
    if progress_callback:
        progress_callback('scanning', 0, total_batches, f'找到 {len(zip_files)} 个ZIP文件，共 {total_batches} 个批次')
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(zip_files))
        batch_files = zip_files[start_idx:end_idx]
        
        if progress_callback:
            progress_callback('processing', batch_num, total_batches, 
                            f'处理批次 {batch_num + 1}/{total_batches}')
        
        # 调用原始函数（这里简化处理，实际应该集成到main.py的函数中）
        from main import create_pdf_from_chapters, extract_chapter_name
        
        first_chapter = extract_chapter_name(batch_files[0])
        last_chapter = extract_chapter_name(batch_files[-1])
        output_filename = f"{pdf_prefix}_{first_chapter}_to_{last_chapter}.pdf"
        
        create_pdf_from_chapters(batch_files, folder_path, output_filename, batch_num + 1, output_folder)
        
        if convert_to_mobi:
            from main import convert_pdf_to_mobi
            pdf_path = os.path.join(output_folder, output_filename)
            convert_pdf_to_mobi(pdf_path, output_folder, kindle_profile)


def pack_comics_by_book_with_progress(folder_path: str, pdf_prefix: str = "",
                                      output_folder: str = './output',
                                      convert_to_mobi: bool = False, 
                                      kindle_profile: str = 'KPW5',
                                      progress_callback: Optional[Callable] = None):
    """按书打包模式（带进度回调）"""
    print(f"[CONVERT] pack_comics_by_book_with_progress called with folder: {folder_path}")
    
    # 直接调用原始函数 - 它已经有完整的转换逻辑
    # 未来可以修改main.py来支持进度回调，现在先让它工作
    if progress_callback:
        progress_callback('processing', 0, 100, '开始按书打包转换...')
    
    try:
        # 调用原始的转换函数
        pack_comics_by_book(folder_path, pdf_prefix, output_folder, convert_to_mobi, kindle_profile)
        
        if progress_callback:
            progress_callback('completed', 100, 100, '按书打包完成')
    except Exception as e:
        print(f"[CONVERT] Error in pack_comics_by_book: {e}")
        raise


def convert_cbz_to_pdf_with_progress(folder_path: str, cbz_prefix: str = "",
                                     output_folder: str = './output',
                                     convert_to_mobi: bool = False,
                                     kindle_profile: str = 'KPW5',
                                     progress_callback: Optional[Callable] = None):
    """CBZ转PDF模式（带进度回调）"""
    print(f"[CONVERT] convert_cbz_to_pdf_with_progress called with folder: {folder_path}")
    
    if progress_callback:
        progress_callback('processing', 0, 100, '开始CBZ转PDF...')
    
    try:
        # 调用原始的转换函数
        convert_cbz_to_pdf(folder_path, cbz_prefix, output_folder, convert_to_mobi, kindle_profile)
        
        if progress_callback:
            progress_callback('completed', 100, 100, 'CBZ转PDF完成')
    except Exception as e:
        print(f"[CONVERT] Error in convert_cbz_to_pdf: {e}")
        raise


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


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """列出所有任务"""
    with jobs_lock:
        return jsonify({
            'jobs': list(jobs.values())
        })


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
                
                # 如果任务完成或失败，结束流
                if job['status'] in ['completed', 'failed']:
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
