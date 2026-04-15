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
import sys
import io
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Callable
from flask import Flask, render_template, request, jsonify, Response, send_file
from flask_cors import CORS
import uuid

# 导入主程序的转换函数
from main import (
    pack_comics_to_pdf,
    pack_comics_by_book,
    convert_cbz_to_pdf,
    convert_pdf_folder_to_mobi,
    natural_sort_key,
    extract_volume_number,
    sanitize_output_component
)

app = Flask(__name__)
CORS(app)

# 全局变量
job_queue = queue.Queue()
jobs: Dict[str, dict] = {}
jobs_lock = threading.Lock()
cancelled_jobs = set()  # 跟踪被取消的任务
console_output = []  # 存储最新的控制台输出
console_output_lock = threading.Lock()
config_lock = threading.Lock()
MAX_CONSOLE_LINES = 20  # 最多保留20行输出
COMIC_FILE_EXTENSIONS = {'.zip', '.cbz', '.pdf'}
CONVERTIBLE_COMIC_EXTENSIONS = {'.zip', '.cbz', '.pdf'}
DOWNLOADABLE_FILE_EXTENSIONS = COMIC_FILE_EXTENSIONS | {'.mobi', '.epub'}
FOLDER_METADATA_BLACKLIST = {
    '完结', '未完', '连载中', '已完结', '未完结', '电子版', '掃圖', '扫图', '生肉',
    '熟肉', 'pdf', 'zip', 'cbz', 'bili', '哔哩哔哩', '合集', '单行本'
}
CONFIG_PATH = Path(__file__).with_name('config.toml')
BROWSE_ROOT = Path('/mnt').resolve()


def configure_server_logging():
    """抑制 Flask/Werkzeug 的常规访问日志，只保留关键任务日志。"""
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.ERROR)
    werkzeug_logger.propagate = False

    # 隐藏 Flask 自带开发服务器 banner/debug 提示，终端只保留关键业务日志。
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *args, **kwargs: None
    except Exception:
        pass


def is_allowed_path(path: Path) -> bool:
    """判断路径是否位于允许访问的 /mnt/ 范围内。"""
    return path == BROWSE_ROOT or BROWSE_ROOT in path.parents


def resolve_allowed_path(path_value: str, require_exists: bool = True,
                         require_dir: bool = False,
                         require_file: bool = False) -> Path:
    """解析并校验路径，限制只能访问 /mnt/ 下的文件。"""
    if not path_value:
        raise ValueError('路径不能为空')

    raw_path = Path(path_value).expanduser()
    candidate = (BROWSE_ROOT / raw_path).resolve(strict=False) if not raw_path.is_absolute() else raw_path.resolve(strict=False)

    if not is_allowed_path(candidate):
        raise PermissionError('只允许访问 /mnt/ 下的文件')

    if require_exists and not candidate.exists():
        raise FileNotFoundError('路径不存在')

    if candidate.exists():
        if require_dir and not candidate.is_dir():
            raise NotADirectoryError('不是目录')
        if require_file and not candidate.is_file():
            raise IsADirectoryError('不是文件')

    return candidate


def get_default_comic_folder() -> Path:
    """获取默认漫画目录，优先使用常见样本目录。"""
    candidates = [
        Path('/mnt/data/down/comic'),
        BROWSE_ROOT
    ]

    for candidate in candidates:
        try:
            resolved = resolve_allowed_path(str(candidate), require_exists=True, require_dir=True)
            return resolved
        except Exception:
            continue

    return BROWSE_ROOT


def derive_output_folder_from_comic_folder(comic_folder: str) -> Path:
    """根据漫画目录生成默认输出目录：上一级目录下的 comic_output。"""
    comic_path = resolve_allowed_path(comic_folder, require_exists=True, require_dir=True)
    parent_dir = comic_path.parent

    if not is_allowed_path(parent_dir):
        parent_dir = BROWSE_ROOT

    output_dir = (parent_dir / 'comic_output').resolve(strict=False)
    if not is_allowed_path(output_dir):
        output_dir = BROWSE_ROOT / 'comic_output'

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def parse_simple_toml(content: str) -> dict:
    """解析当前项目所需的最小 TOML 子集（仅 key = \"value\"）。"""
    result = {}

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or line.startswith('['):
            continue
        if '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if value.startswith('"') and value.endswith('"'):
            try:
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                result[key] = value.strip('"')
        else:
            result[key] = value.strip().strip('"').strip("'")

    return result


def write_app_config(config: dict):
    """将当前 Web 配置写入 config.toml。"""
    content = '\n'.join([
        '# ComicPacker Web configuration',
        f'comic_folder = {json.dumps(config["comic_folder"], ensure_ascii=False)}',
        f'output_folder = {json.dumps(config["output_folder"], ensure_ascii=False)}',
        ''
    ])
    CONFIG_PATH.write_text(content, encoding='utf-8')


def load_app_config() -> dict:
    """读取并规范化 Web 配置；若不存在则自动创建。"""
    with config_lock:
        default_comic_folder = get_default_comic_folder()
        default_output_folder = derive_output_folder_from_comic_folder(str(default_comic_folder))

        config = {
            'comic_folder': str(default_comic_folder),
            'output_folder': str(default_output_folder)
        }

        if CONFIG_PATH.exists():
            parsed = parse_simple_toml(CONFIG_PATH.read_text(encoding='utf-8'))
            for key in ('comic_folder', 'output_folder'):
                if parsed.get(key):
                    config[key] = parsed[key]

        try:
            config['comic_folder'] = str(
                resolve_allowed_path(config['comic_folder'], require_exists=True, require_dir=True)
            )
        except Exception:
            config['comic_folder'] = str(default_comic_folder)

        try:
            output_path = resolve_allowed_path(config['output_folder'], require_exists=False)
            if output_path.exists() and not output_path.is_dir():
                raise NotADirectoryError('输出路径不是目录')
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            output_path = derive_output_folder_from_comic_folder(config['comic_folder'])

        config['output_folder'] = str(output_path)
        write_app_config(config)
        return config


def update_default_paths(comic_folder: str) -> dict:
    """更新默认漫画目录，并同步输出目录到上一级的 comic_output。"""
    with config_lock:
        comic_path = resolve_allowed_path(comic_folder, require_exists=True, require_dir=True)
        output_path = derive_output_folder_from_comic_folder(str(comic_path))
        config = {
            'comic_folder': str(comic_path),
            'output_folder': str(output_path)
        }
        write_app_config(config)
        return config


def list_comic_files(folder_path: str, extensions: Optional[set] = None) -> List[str]:
    """按自然顺序列出目录中的漫画文件。"""
    target_extensions = {ext.lower() for ext in (extensions or COMIC_FILE_EXTENSIONS)}
    items = []

    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if not os.path.isfile(item_path):
            continue
        if Path(item).suffix.lower() in target_extensions:
            items.append(item)

    items.sort(key=natural_sort_key)
    return items


def extract_title_from_filename(file_stem: str) -> str:
    """从 `漫画名 Vol.xx` 风格文件名中提取漫画名。"""
    match = re.search(r'(?i)\bvol(?:ume)?[.\s_-]*\d+\b', file_stem or '')
    if not match:
        return ""

    title = file_stem[:match.start()]
    title = re.sub(r'[\s._-]+$', '', title)
    return sanitize_output_component(title)


def extract_folder_segments(folder_name: str) -> List[str]:
    """提取文件夹名中 `[]` 内的片段。"""
    segments = re.findall(r'\[([^\[\]]+)\]', folder_name or '')
    if segments:
        return [segment.strip() for segment in segments if segment.strip()]
    return [folder_name.strip()] if folder_name.strip() else []


def is_folder_metadata_segment(segment: str) -> bool:
    """判断文件夹片段是否更像元数据而非漫画名。"""
    cleaned = sanitize_output_component(segment)
    if not cleaned:
        return True
    if extract_volume_number(cleaned):
        return True

    lowered = cleaned.lower()
    if lowered in {item.lower() for item in FOLDER_METADATA_BLACKLIST}:
        return True

    return False


def infer_title_from_folder(folder_name: str) -> str:
    """
    从 `[漫画名][][]` 风格文件夹中尽量推断漫画名。
    由于元数据顺序并不稳定，只做最佳努力推断，并允许前端覆盖。
    """
    segments = extract_folder_segments(folder_name)
    candidates = [segment for segment in segments if not is_folder_metadata_segment(segment)]

    if not candidates:
        return ""
    if len(candidates) == 1:
        return sanitize_output_component(candidates[0])

    return sanitize_output_component(max(candidates, key=lambda value: (len(value), -candidates.index(value))))


def build_output_preview(comic_name: str, sample_volume: Optional[str]) -> str:
    """生成输出命名预览。"""
    safe_title = sanitize_output_component(comic_name)
    volume_number = sample_volume or '01'

    if safe_title:
        return f"{safe_title} Vol.{volume_number}"

    return f"漫画名 Vol.{volume_number}"


def build_suggested_output_dir(comic_name: str) -> str:
    """输出目录现在是根目录语义，默认建议保持在 ./output。"""
    return "./output"


def analyze_comic_folder(folder_path: str) -> dict:
    """读取漫画文件夹并返回命名分析结果。"""
    all_comic_files = list_comic_files(folder_path, COMIC_FILE_EXTENSIONS)
    convertible_files = [
        file_name for file_name in all_comic_files
        if Path(file_name).suffix.lower() in CONVERTIBLE_COMIC_EXTENSIONS
    ]

    sample_files = convertible_files or all_comic_files
    first_file_name = sample_files[0] if sample_files else None
    first_file_stem = Path(first_file_name).stem if first_file_name else ""
    sample_volume = extract_volume_number(first_file_stem)
    file_title = extract_title_from_filename(first_file_stem)
    folder_title = infer_title_from_folder(Path(folder_path).name)
    inferred_title = file_title or folder_title

    if file_title:
        naming_source = 'filename'
        naming_pattern = 'title_volume'
        confidence = 'high'
    elif sample_volume and folder_title:
        naming_source = 'folder'
        naming_pattern = 'volume_only'
        confidence = 'medium'
    else:
        naming_source = 'unknown'
        naming_pattern = 'unknown'
        confidence = 'low'

    return {
        'first_file_name': first_file_name,
        'first_file_stem': first_file_stem or None,
        'comic_name': inferred_title or '',
        'folder_title_candidate': folder_title or None,
        'sample_volume': sample_volume or '01',
        'output_preview': build_output_preview(inferred_title, sample_volume),
        'suggested_output_dir': build_suggested_output_dir(inferred_title),
        'naming_source': naming_source,
        'naming_pattern': naming_pattern,
        'naming_confidence': confidence,
        'total_comic_files': len(all_comic_files),
        'convertible_file_count': len(convertible_files)
    }


class ConsoleCapture(io.StringIO):
    """捕获stdout输出的自定义类"""
    
    def write(self, text):
        """重写write方法以捕获输出"""
        # 调用父类的write方法
        super().write(text)
        
        # 如果不是空行或只有换行符，添加到控制台输出
        if text and text.strip():
            # 移除多余的换行符
            clean_text = text.rstrip('\n')
            if clean_text:
                add_console_output(clean_text)
        
        return len(text)


def add_console_output(line: str):
    """添加一行控制台输出"""
    with console_output_lock:
        console_output.append(line)
        # 只保留最新的5行
        if len(console_output) > MAX_CONSOLE_LINES:
            console_output.pop(0)


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
            job_id = job_queue.get()
            
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
                print(f"[WORKER] Job {job_id} started ({job['parameters'].get('mode', 'batch')})")
            
            # 创建进度跟踪器
            tracker = ProgressTracker(job_id)
            
            # 保存原始stdout
            original_stdout = sys.stdout
            
            try:
                # 重定向stdout到我们的捕获器
                console_capture = ConsoleCapture()
                sys.stdout = console_capture
                
                # 执行转换任务
                params = job['parameters']
                mode = params.get('mode', 'batch')
                comic_name = params.get('comic_name', '').strip()
                
                print(f"[WORKER] Starting conversion in {mode} mode")
                tracker.update('init', 0, 100, f'开始 {mode} 模式转换...')
                
                if mode == 'batch':
                    pack_comics_to_pdf_with_progress(
                        folder_path=params['folder'],
                        batch_size=params.get('batch_size', 10),
                        pdf_prefix=params.get('prefix', ''),
                        output_folder=params.get('output', './output'),
                        convert_to_mobi=params.get('convert_to_mobi', False),
                        kindle_profile=params.get('kindle_profile', 'KPW5'),
                        progress_callback=tracker.update,
                        comic_name=comic_name
                    )
                elif mode == 'book':
                    pack_comics_by_book_with_progress(
                        folder_path=params['folder'],
                        pdf_prefix=params.get('prefix', ''),
                        output_folder=params.get('output', './output'),
                        convert_to_mobi=params.get('convert_to_mobi', False),
                        kindle_profile=params.get('kindle_profile', 'KPW5'),
                        progress_callback=tracker.update,
                        comic_name=comic_name
                    )
                elif mode == 'cbz':
                    convert_cbz_to_pdf_with_progress(
                        folder_path=params['folder'],
                        cbz_prefix=params.get('prefix', ''),
                        output_folder=params.get('output', './output'),
                        convert_to_mobi=params.get('convert_to_mobi', False),
                        kindle_profile=params.get('kindle_profile', 'KPW5'),
                        progress_callback=tracker.update,
                        comic_name=comic_name
                    )
                elif mode == 'pdf':
                    convert_pdf_folder_to_mobi_with_progress(
                        folder_path=params['folder'],
                        output_folder=params.get('output', './output'),
                        kindle_profile=params.get('kindle_profile', 'KPW5'),
                        progress_callback=tracker.update,
                        comic_name=comic_name
                    )
                
                # 任务完成
                print(f"[WORKER] Job {job_id} completed successfully with verified outputs")
                with jobs_lock:
                    progress = jobs[job_id].get('progress', {})
                    if progress.get('stage') != 'completed':
                        current = progress.get('current', 0)
                        total = progress.get('total', current)
                        jobs[job_id]['progress'] = {
                            'stage': 'completed',
                            'current': current,
                            'total': total,
                            'message': '任务已完成，输出文件已写入目标目录',
                            'percentage': 100
                        }
                    else:
                        jobs[job_id]['progress']['percentage'] = 100
                        jobs[job_id]['progress']['message'] = (
                            jobs[job_id]['progress'].get('message')
                            or '任务已完成，输出文件已写入目标目录'
                        )

                    if jobs[job_id]['status'] != 'completed':
                        jobs[job_id]['status'] = 'completed'
                    jobs[job_id]['end_time'] = datetime.now().isoformat()
                    jobs[job_id]['last_update'] = datetime.now().isoformat()
                    
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
                    failure_message = f'转换失败: {str(e)}'
                    with jobs_lock:
                        jobs[job_id]['status'] = 'failed'
                        jobs[job_id]['end_time'] = datetime.now().isoformat()
                        jobs[job_id]['error'] = str(e)
                    tracker.update('error', 0, 100, failure_message)
            
            finally:
                # 恢复原始stdout
                sys.stdout = original_stdout
                job_queue.task_done()
                
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
                                     progress_callback: Optional[Callable] = None,
                                     comic_name: str = ""):
    """批次模式转换（带进度回调）"""
    pack_comics_to_pdf(folder_path, batch_size, pdf_prefix, output_folder,
                      convert_to_mobi, kindle_profile, progress_callback,
                      comic_name=comic_name)


def pack_comics_by_book_with_progress(folder_path: str, pdf_prefix: str = "",
                                      output_folder: str = './output',
                                      convert_to_mobi: bool = False, 
                                      kindle_profile: str = 'KPW5',
                                      progress_callback: Optional[Callable] = None,
                                      comic_name: str = ""):
    """按书打包模式（带进度回调）"""
    # 直接调用main.py中的函数，它会通过progress_callback报告所有进度
    pack_comics_by_book(folder_path, pdf_prefix, output_folder, 
                       convert_to_mobi, kindle_profile, progress_callback,
                       comic_name=comic_name)


def convert_cbz_to_pdf_with_progress(folder_path: str, cbz_prefix: str = "",
                                     output_folder: str = './output',
                                     convert_to_mobi: bool = False,
                                     kindle_profile: str = 'KPW5',
                                     progress_callback: Optional[Callable] = None,
                                     comic_name: str = ""):
    """CBZ转PDF模式（带进度回调）"""
    convert_cbz_to_pdf(folder_path, cbz_prefix, output_folder, 
                        convert_to_mobi, kindle_profile, progress_callback,
                        comic_name=comic_name)


def convert_pdf_folder_to_mobi_with_progress(folder_path: str,
                                             output_folder: str = './output',
                                             kindle_profile: str = 'KPW5',
                                             progress_callback: Optional[Callable] = None,
                                             comic_name: str = ""):
    """PDF转MOBI模式（带进度回调）"""
    convert_pdf_folder_to_mobi(
        folder_path,
        output_folder,
        kindle_profile,
        progress_callback,
        comic_name=comic_name
    )


# ============= API路由 =============

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/config', methods=['GET'])
def get_config():
    """获取 Web 配置。"""
    try:
        config = load_app_config()
        return jsonify({
            **config,
            'browse_root': str(BROWSE_ROOT)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/default-path', methods=['POST'])
def update_default_path():
    """更新默认漫画目录，并同步输出目录。"""
    try:
        data = request.json or {}
        config = update_default_paths(data.get('path'))
        return jsonify({
            **config,
            'browse_root': str(BROWSE_ROOT)
        })
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except (FileNotFoundError, NotADirectoryError, ValueError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/browse', methods=['POST'])
def browse_files():
    """浏览服务器文件系统"""
    try:
        data = request.json or {}
        config = load_app_config()
        abs_path = resolve_allowed_path(
            data.get('path') or config['comic_folder'],
            require_exists=True,
            require_dir=True
        )
        
        # 列出目录内容
        items = []
        try:
            for item in sorted(os.listdir(abs_path), key=natural_sort_key):
                item_path = abs_path / item
                is_dir = item_path.is_dir()
                
                # 统计文件信息
                file_count = 0
                if is_dir:
                    try:
                        # 统计漫画文件数量
                        file_count = len([
                            f for f in os.listdir(item_path)
                            if Path(f).suffix.lower() in COMIC_FILE_EXTENSIONS
                        ])
                    except:
                        file_count = 0
                
                items.append({
                    'name': item,
                    'path': str(item_path),
                    'is_dir': is_dir,
                    'file_count': file_count if is_dir else None,
                    'is_downloadable': (not is_dir and item_path.suffix.lower() in DOWNLOADABLE_FILE_EXTENSIONS)
                })
        except PermissionError:
            return jsonify({'error': '没有权限访问此目录'}), 403
        
        return jsonify({
            'path': str(abs_path),
            'parent': str(abs_path.parent) if abs_path != BROWSE_ROOT else None,
            'items': items
        })
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except FileNotFoundError:
        return jsonify({'error': '路径不存在'}), 404
    except NotADirectoryError:
        return jsonify({'error': '不是目录'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download', methods=['GET'])
def download_file():
    """下载 /mnt/ 下的漫画相关文件。"""
    try:
        file_path = resolve_allowed_path(
            request.args.get('path', ''),
            require_exists=True,
            require_file=True
        )

        if file_path.suffix.lower() not in DOWNLOADABLE_FILE_EXTENSIONS:
            return jsonify({'error': '该文件类型不支持下载'}), 400

        return send_file(file_path, as_attachment=True, download_name=file_path.name)
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except FileNotFoundError:
        return jsonify({'error': '文件不存在'}), 404
    except IsADirectoryError:
        return jsonify({'error': '不是文件'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/detect-mode', methods=['POST'])
def detect_mode():
    """检测文件夹内容并返回推荐的转换模式"""
    try:
        data = request.json or {}
        folder_path = resolve_allowed_path(
            data.get('path'),
            require_exists=True,
            require_dir=True
        )
        
        # 统计文件类型并读取命名分析
        cbz_count = 0
        zip_count = 0
        pdf_count = 0
        vol_files_count = 0  # 统计以Vol开头的文件
        folder_analysis = analyze_comic_folder(str(folder_path))
        
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
                elif item_lower.endswith('.pdf'):
                    pdf_count += 1
        except PermissionError:
            return jsonify({'error': '没有权限访问此目录'}), 403
        
        # 根据文件类型推荐模式
        if cbz_count > 0:
            recommended_mode = 'cbz'
        elif zip_count > 0:
            recommended_mode = 'book'
        elif pdf_count > 0:
            recommended_mode = 'pdf'
        else:
            recommended_mode = 'book'  # 默认
        
        return jsonify({
            'recommended_mode': recommended_mode,
            'cbz_count': cbz_count,
            'zip_count': zip_count,
            'pdf_count': pdf_count,
            'total_files': cbz_count + zip_count + pdf_count,
            'has_vol_files': vol_files_count > 0,
            'vol_files_count': vol_files_count,
            **folder_analysis
        })
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except FileNotFoundError:
        return jsonify({'error': '路径不存在'}), 404
    except NotADirectoryError:
        return jsonify({'error': '不是目录'}), 400
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


@app.route('/api/console-output', methods=['GET'])
def get_console_output():
    """获取最新的控制台输出"""
    with console_output_lock:
        return jsonify({
            'output': list(console_output)
        })


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
        params = request.json or {}
        
        # 验证参数
        if 'folder' not in params:
            print("[API] 创建任务失败: 缺少 folder 参数")
            return jsonify({'error': '缺少folder参数'}), 400

        folder_path = resolve_allowed_path(params['folder'], require_exists=True, require_dir=True)
        params['folder'] = str(folder_path)

        folder_analysis = analyze_comic_folder(params['folder'])
        comic_name = sanitize_output_component(params.get('comic_name', '').strip()) or folder_analysis.get('comic_name', '')
        params['comic_name'] = comic_name

        if params.get('mode') == 'batch' and comic_name and not params.get('prefix'):
            params['prefix'] = comic_name
        if params.get('mode') == 'pdf':
            params['convert_to_mobi'] = True

        if not params.get('output'):
            params['output'] = load_app_config().get('output_folder', str(derive_output_folder_from_comic_folder(params['folder'])))

        output_path = resolve_allowed_path(params['output'], require_exists=False)
        if output_path.exists() and not output_path.is_dir():
            return jsonify({'error': '输出路径不是目录'}), 400
        output_path.mkdir(parents=True, exist_ok=True)
        params['output'] = str(output_path)
        
        # 创建任务
        job_id = str(uuid.uuid4())
        
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
        print(f"[JOB] Created job {job_id} ({params.get('mode', 'batch')})")
        
        return jsonify({
            'job_id': job_id,
            'status': 'pending'
        })
    except PermissionError as e:
        print(f"[API] 创建任务失败: {e}")
        return jsonify({'error': str(e)}), 403
    except ValueError as e:
        print(f"[API] 创建任务失败: {e}")
        return jsonify({'error': str(e)}), 400
    except FileNotFoundError:
        print(f"[API] 创建任务失败: 文件夹不存在 - {params.get('folder')}")
        return jsonify({'error': '文件夹不存在'}), 400
    except NotADirectoryError:
        print(f"[API] 创建任务失败: 目录无效 - {params.get('folder')}")
        return jsonify({'error': '不是目录'}), 400
    except Exception as e:
        print(f"[API] 创建任务时出错: {e}")
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
    configure_server_logging()
    config = load_app_config()
    print("=" * 60)
    print("ComicPacker Web Server")
    print("=" * 60)
    print("服务器地址: http://localhost:5000")
    print(f"漫画目录: {config['comic_folder']}")
    print(f"输出目录: {config['output_folder']}")
    print(f"浏览限制: {BROWSE_ROOT}/")
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
