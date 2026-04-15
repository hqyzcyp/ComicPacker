#!/usr/bin/env python3
"""
Comic Packer - 将ZIP文件中的漫画图片打包成PDF
按章节顺序分批次打包，每批默认10个章节，每章节第一页带标题索引
"""

import os
import zipfile
import re
import argparse
import subprocess
import shutil
from pathlib import Path
from typing import List, Tuple, Optional, Callable
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
from multiprocessing import Process

page_width, page_height = 1236, 1648

# 全局进程池,用于跟踪所有MOBI转换进程
conversion_processes = []
INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'

def natural_sort_key(filename: str) -> List:
    """
    自然排序键函数，用于正确排序包含数字的文件名
    例如: CH-001, CH-002, ..., CH-010, CH-011
    """
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split('([0-9]+)', filename)]


def fix_zip_filename(filename: str) -> str:
    """
    修复ZIP文件中的中文文件名编码问题
    ZIP文件可能使用GBK、CP437等编码，需要尝试转换
    """
    # 尝试不同的编码方式
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'cp437']
    
    for encoding in encodings:
        try:
            # 先尝试用cp437解码（ZIP默认），再用目标编码重新编码
            if encoding != 'utf-8':
                fixed = filename.encode('cp437').decode(encoding)
                # 验证解码结果是否包含合理的字符
                if fixed.isprintable() or any('\u4e00' <= c <= '\u9fff' for c in fixed):
                    return fixed
        except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
            continue
    
    # 如果所有编码都失败，返回原始文件名
    return filename


def sanitize_output_component(value: str) -> str:
    """
    清理输出文件/目录名中的非法字符并压缩空白。
    """
    cleaned = re.sub(INVALID_FILENAME_CHARS, ' ', value or '')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ._-')
    return cleaned


def extract_volume_number(name: str) -> Optional[str]:
    """
    从名称中提取卷号数字，统一补齐为至少 2 位。
    例如: "Vol.1" -> "01", "尖帽子的魔法工坊 Vol.12" -> "12"
    """
    match = re.search(r'(?i)\bvol(?:ume)?[.\s_-]*(\d+)\b', name or '')
    if not match:
        return None

    digits = match.group(1)
    return digits.zfill(max(2, len(digits)))


def build_normalized_volume_name(source_name: str, comic_name: str = "") -> str:
    """
    根据漫画名与源文件卷号生成规范输出名，格式为: 漫画名 Vol.xx
    若无法识别卷号，则回退为源文件名（去扩展名）。
    """
    stem = Path(source_name).stem
    safe_stem = sanitize_output_component(stem) or stem
    safe_title = sanitize_output_component(comic_name)
    volume_number = extract_volume_number(stem)

    if safe_title and volume_number:
        return f"{safe_title} Vol.{volume_number}"

    return safe_stem



def get_sorted_zip_files(folder_path: str) -> List[str]:
    """
    获取文件夹中所有ZIP文件并按自然顺序排序
    """
    zip_files = [f for f in os.listdir(folder_path) if f.endswith('.zip')]
    zip_files.sort(key=natural_sort_key)
    return zip_files


def get_images_from_zip(zip_path: str) -> List[Tuple[str, bytes]]:
    """
    从ZIP文件中提取所有图片文件
    返回: [(文件名, 图片数据), ...]
    """
    images = []
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # 获取所有图片文件
        image_items = []
        for file_info in zip_ref.filelist:
            # 修复文件名编码
            fixed_filename = fix_zip_filename(file_info.filename)
            
            # 检查是否是图片文件
            if Path(fixed_filename).suffix.lower() in image_extensions:
                image_items.append((fixed_filename, file_info.filename))
        
        # 按修复后的文件名排序
        image_items.sort(key=lambda x: natural_sort_key(x[0]))
        
        # 读取图片数据
        for fixed_filename, original_filename in image_items:
            image_data = zip_ref.read(original_filename)
            images.append((fixed_filename, image_data))
    
    return images


def get_chapters_from_zip(zip_path: str) -> dict:
    """
    从ZIP文件中按文件夹（章节）提取图片
    返回: {章节名: [(文件名, 图片数据), ...], ...}
    """
    chapters = {}
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # 获取所有图片文件
        for file_info in zip_ref.filelist:
            # 修复文件名编码
            try:
                # 尝试使用UTF-8解码
                filename = file_info.filename
            except:
                filename = file_info.filename
            
            # 尝试修复编码问题
            fixed_filename = fix_zip_filename(filename)
            
            # 检查是否是图片文件
            if Path(fixed_filename).suffix.lower() not in image_extensions:
                continue
            
            # 获取文件夹名作为章节名
            path_parts = Path(fixed_filename).parts
            if len(path_parts) > 1:
                # 有文件夹结构
                chapter_name = path_parts[0]
            else:
                # 没有文件夹，使用默认章节名
                chapter_name = "默认章节"
            
            if chapter_name not in chapters:
                chapters[chapter_name] = []
            
            # 读取图片数据（使用原始文件名）
            image_data = zip_ref.read(file_info.filename)
            chapters[chapter_name].append((fixed_filename, image_data))
    
    # 对每个章节的图片进行排序
    for chapter_name in chapters:
        chapters[chapter_name].sort(key=lambda x: natural_sort_key(x[0]))
    
    return chapters


def extract_chapter_name(zip_filename: str) -> str:
    """
    从ZIP文件名中提取章节名称
    例如: "寓言杀手-CH-001.zip" -> "CH-001"
    """
    # 移除.zip扩展名
    name = Path(zip_filename).stem
    
    # 尝试提取章节编号
    match = re.search(r'CH-?\d+', name, re.IGNORECASE)
    if match:
        return match.group()
    
    # 如果没有找到标准格式，返回整个文件名
    return name


def is_first_image(filename: str) -> bool:
    """
    检测图片文件名是否表示第一张图片（从1或01开始）
    例如: "1.jpg", "01.png", "001.jpg" 等
    """
    basename = Path(filename).stem
    # 提取文件名中的数字
    numbers = re.findall(r'\d+', basename)
    if numbers:
        # 检查第一个数字是否为1
        return int(numbers[0]) == 1
    return False


def create_title_page(c: canvas.Canvas, title: str, page_width: float, page_height: float):
    """
    创建章节标题页，并添加PDF书签
    """
    # 在创建新页面之前添加书签（书签指向当前页）
    c.bookmarkPage(title)
    c.addOutlineEntry(title, title, level=0)
    
    c.setFont("Helvetica-Bold", 36)
    
    # 在页面中央绘制标题
    text_width = c.stringWidth(title, "Helvetica-Bold", 36)
    x = (page_width - text_width) / 2
    y = page_height / 2
    
    c.drawString(x, y, title)
    c.showPage()


def create_image_cover_page(c: canvas.Canvas, title: str, image_data: bytes, page_width: float, page_height: float):
    """
    创建带图片封面的标题页，并添加PDF书签
    
    注意：此函数会根据图片的宽高比动态调整页面大小，以确保图片完全填充页面且无空白
    """
    # 在创建新页面之前添加书签（书签指向当前页）
    c.bookmarkPage(title)
    c.addOutlineEntry(title, title, level=0)
    
    try:
        # 从字节数据创建PIL图片
        img = Image.open(io.BytesIO(image_data))
        
        # 获取图片尺寸
        img_width, img_height = img.size
        
        # 计算图片的宽高比
        img_aspect_ratio = img_width / img_height
        page_aspect_ratio = page_width / page_height
        
        # 根据宽高比调整页面大小，使图片能够完全填充页面
        if img_aspect_ratio > page_aspect_ratio:
            # 图片更宽，以宽度为准
            actual_width = page_width
            actual_height = page_width / img_aspect_ratio
        else:
            # 图片更高，以高度为准
            actual_height = page_height
            actual_width = page_height * img_aspect_ratio
        
        # 设置当前页面大小
        c.setPageSize((actual_width, actual_height))
        
        # 将图片绘制到PDF（完全填充页面，无边距）
        img_reader = ImageReader(io.BytesIO(image_data))
        c.drawImage(img_reader, 0, 0, width=actual_width, height=actual_height)
        c.showPage()
        
    except Exception as e:
        print(f"警告: 无法创建图片封面 - {e}，使用文字标题页")
        # 如果图片处理失败，回退到文字标题页
        create_title_page(c, title, page_width, page_height)


def preprocess_image(args):
    """
    预处理单张图片（在独立进程中执行）
    
    参数:
        args: (img_data, page_width, page_height, img_name)
    
    返回:
        dict: {
            'data': 优化后的图片字节数据,
            'width': 实际宽度,
            'height': 实际高度,
            'name': 图片名称,
            'error': 错误信息（如果有）
        }
    """
    img_data, page_width, page_height, img_name = args
    
    try:
        # 解码图片
        img = Image.open(io.BytesIO(img_data))
        img_width, img_height = img.size
        
        # 计算目标尺寸
        img_aspect_ratio = img_width / img_height
        page_aspect_ratio = page_width / page_height
        
        if img_aspect_ratio > page_aspect_ratio:
            actual_width = page_width
            actual_height = page_width / img_aspect_ratio
        else:
            actual_height = page_height
            actual_width = page_height * img_aspect_ratio
        
        # 如果图片过大，调整大小以节省内存
        max_dimension = max(actual_width, actual_height)
        if img_width > max_dimension * 1.5 or img_height > max_dimension * 1.5:
            img = img.resize((int(actual_width), int(actual_height)), Image.LANCZOS)
        
        # 保存为优化的 JPEG
        output = io.BytesIO()
        if img.mode in ('RGBA', 'LA', 'P'):
            # 处理透明图片
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        img.save(output, format='JPEG', quality=95, optimize=True)
        
        return {
            'data': output.getvalue(),
            'width': actual_width,
            'height': actual_height,
            'name': img_name,
            'error': None
        }
    except Exception as e:
        return {
            'data': None,
            'width': 0,
            'height': 0,
            'name': img_name,
            'error': str(e)
        }


def preprocess_images(images, page_width, page_height, show_progress=True):
    """
    顺序预处理多张图片
    
    参数:
        images: [(img_name, img_data), ...] 图片列表
        page_width: 页面宽度
        page_height: 页面高度
        show_progress: 是否显示进度条
    
    返回:
        list: 预处理后的图片数据列表
    """
    if not images:
        return []
    
    # 准备参数
    args_list = [(img_data, page_width, page_height, img_name) 
                 for img_name, img_data in images]
    
    print(f"  预处理 {len(images)} 张图片...")
    
    # 顺序处理
    try:
        # 尝试导入 tqdm 用于进度显示
        if show_progress:
            try:
                from tqdm import tqdm
                use_tqdm = True
            except ImportError:
                use_tqdm = False
        else:
            use_tqdm = False
        
        results = []
        iterator = tqdm(args_list, desc="  预处理进度") if use_tqdm else args_list
        
        for args in iterator:
            result = preprocess_image(args)
            results.append(result)
        
        # 检查错误
        errors = [r for r in results if r['error']]
        if errors:
            print(f"  警告: {len(errors)} 张图片预处理失败")
            for err in errors[:3]:  # 只显示前3个错误
                print(f"    - {err['name']}: {err['error']}")
        
        # 过滤掉失败的图片
        successful_results = [r for r in results if r['data'] is not None]
        print(f"  ✓ 成功预处理 {len(successful_results)}/{len(images)} 张图片")
        
        return successful_results
        
    except Exception as e:
        print(f"  ✗ 预处理失败: {e}")
        return []


def add_image_to_pdf(c: canvas.Canvas, image_data: bytes, page_width: float, page_height: float, chapter_title: str = None):
    """
    将图片添加到PDF页面，边距为0，图片填充整个页面
    如果提供了chapter_title，会在图片顶部添加章节标题索引
    
    注意：此函数会根据图片的宽高比动态调整页面大小，以确保图片完全填充页面且无空白
    """
    try:
        # 从字节数据创建PIL图片
        img = Image.open(io.BytesIO(image_data))
        
        # 获取图片尺寸
        img_width, img_height = img.size
        
        # 计算图片的宽高比
        img_aspect_ratio = img_width / img_height
        page_aspect_ratio = page_width / page_height
        
        # 根据宽高比调整页面大小，使图片能够完全填充页面
        if img_aspect_ratio > page_aspect_ratio:
            # 图片更宽，以宽度为准
            actual_width = page_width
            actual_height = page_width / img_aspect_ratio
        else:
            # 图片更高，以高度为准
            actual_height = page_height
            actual_width = page_height * img_aspect_ratio
        
        # 设置当前页面大小
        c.setPageSize((actual_width, actual_height))
        
        # 将图片绘制到PDF（完全填充页面，无边距）
        img_reader = ImageReader(io.BytesIO(image_data))
        c.drawImage(img_reader, 0, 0, width=actual_width, height=actual_height)
        
        # 如果提供了章节标题，在图片上叠加索引信息
        if chapter_title:
            # 添加PDF书签
            c.bookmarkPage(chapter_title)
            c.addOutlineEntry(chapter_title, chapter_title, level=0)
            
            # # 设置半透明黑色背景
            # c.setFillColorRGB(0, 0, 0, alpha=0.7)
            
            # # 计算标题栏的位置和大小
            # title_height = 60
            # title_y = actual_height - title_height
            # c.rect(0, title_y, actual_width, title_height, fill=True, stroke=False)
            
            # # 设置白色文字
            # c.setFillColorRGB(1, 1, 1)
            # c.setFont("Helvetica-Bold", 28)
            
            # # 在标题栏中央绘制章节标题
            # text_width = c.stringWidth(chapter_title, "Helvetica-Bold", 28)
            # text_x = (actual_width - text_width) / 2
            # text_y = title_y + (title_height - 28) / 2 + 5
            
            # c.drawString(text_x, text_y, chapter_title)
        
        c.showPage()
        
    except Exception as e:
        print(f"警告: 无法处理图片 - {e}")


def create_pdf_from_chapters(zip_files: List[str], folder_path: str, 
                            output_filename: str, batch_number: int, output_folder: str = './output'):
    """
    从多个ZIP文件创建一个PDF文件，并为每个章节添加书签
    """
    output_path = os.path.join(output_folder, output_filename)
    
    print(f"\n创建PDF: {output_filename}")
    print(f"包含章节: {', '.join([extract_chapter_name(z) for z in zip_files])}")
    
    # 第一步：收集所有图片和章节信息
    all_images = []
    chapter_markers = []  # 记录每个章节的起始位置
    
    for zip_file in zip_files:
        zip_path = os.path.join(folder_path, zip_file)
        chapter_name = extract_chapter_name(zip_file)
        
        print(f"  读取章节: {chapter_name}")
        
        # 获取章节中的所有图片
        images = get_images_from_zip(zip_path)
        print(f"    找到 {len(images)} 张图片")
        
        # 记录章节标记（在所有图片列表中的位置）
        chapter_markers.append({
            'name': chapter_name,
            'start_index': len(all_images)
        })
        
        all_images.extend(images)
    
    # 第二步：预处理所有图片
    if all_images:
        preprocessed_images = preprocess_images(all_images, page_width, page_height)
    else:
        preprocessed_images = []
    
    # 第三步：顺序组装PDF
    print(f"  组装PDF...")
    c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
    
    current_img_index = 0
    for chapter_info in chapter_markers:
        chapter_name = chapter_info['name']
        
        # 计算这个章节有多少张图片
        next_chapter_start = chapter_markers[chapter_markers.index(chapter_info) + 1]['start_index'] \
                            if chapter_markers.index(chapter_info) + 1 < len(chapter_markers) \
                            else len(preprocessed_images)
        
        # 添加这个章节的所有图片
        while current_img_index < next_chapter_start and current_img_index < len(preprocessed_images):
            img_info = preprocessed_images[current_img_index]
            
            # 设置页面大小
            c.setPageSize((img_info['width'], img_info['height']))
            
            # 绘制图片
            img_reader = ImageReader(io.BytesIO(img_info['data']))
            c.drawImage(img_reader, 0, 0, width=img_info['width'], height=img_info['height'])
            c.showPage()
            
            current_img_index += 1
    
    c.save()
    print(f"✓ PDF创建完成: {output_filename}")
    print(f"  已添加 {len(zip_files)} 个章节书签")


def pack_comics_by_book(folder_path: str, pdf_prefix: str = "", output_folder: str = './output',
                        convert_to_mobi: bool = False, kindle_profile: str = 'KPW5',
                        progress_callback: Optional[Callable] = None,
                        comic_name: str = ""):
    """
    按书打包：每个ZIP压缩包下有若干文件夹（章节），将这些章节打包成一个PDF
    - 使用最小章节的第一张图片作为整本书的封面
    - 每个章节的第一页图片上叠加章节名称索引
    
    参数:
        folder_path: 包含ZIP文件的文件夹路径
        pdf_prefix: PDF文件名前缀（默认""）
        output_folder: 输出PDF文件的文件夹路径（默认'./output')
        convert_to_mobi: 是否转换为MOBI格式(默认False)
        kindle_profile: Kindle设备配置文件(默认'KPW5')
        progress_callback: 进度回调函数(可选)
    """
    # 创建输出文件夹（如果不存在）
    os.makedirs(output_folder, exist_ok=True)
    
    # 获取所有ZIP文件并排序
    zip_files = get_sorted_zip_files(folder_path)
    
    if not zip_files:
        print(f"错误: 在 {folder_path} 中没有找到ZIP文件")
        return
    
    print(f"找到 {len(zip_files)} 个ZIP文件")
    print(f"打包模式: 按书打包（每个ZIP为一本书，包含多个章节）")
    print(f"PDF文件名前缀: {pdf_prefix}")
    if comic_name:
        print(f"规范漫画名: {comic_name}")
    print(f"输出文件夹: {output_folder}")
    if convert_to_mobi:
        print(f"MOBI转换: 启用 (设备配置: {kindle_profile})")
    
    # 报告初始进度
    if progress_callback:
        progress_callback('scanning', 0, len(zip_files), f'找到 {len(zip_files)} 本书')
    
    # 处理每个ZIP文件（每个ZIP是一本书）
    for book_idx, zip_file in enumerate(zip_files, 1):
        zip_path = os.path.join(folder_path, zip_file)
        book_name = Path(zip_file).stem  # 去掉.zip后缀
        
        print(f"\n处理书籍 {book_idx}/{len(zip_files)}: {book_name}")
        
        # 报告当前书籍进度
        if progress_callback:
            progress_callback('processing', book_idx - 1, len(zip_files), 
                            f'处理书籍 {book_idx}/{len(zip_files)}: {book_name}')
        
        # 从ZIP中提取章节
        chapters = get_chapters_from_zip(zip_path)
        
        if not chapters:
            print(f"  警告: {zip_file} 中没有找到图片，跳过")
            continue
        
        # 对章节名进行排序
        sorted_chapter_names = sorted(chapters.keys(), key=natural_sort_key)
        
        print(f"  找到 {len(sorted_chapter_names)} 个章节: {', '.join(sorted_chapter_names)}")
        
        # 创建PDF文件
        normalized_book_name = build_normalized_volume_name(zip_file, comic_name) if comic_name else book_name
        output_filename = f"{normalized_book_name}.pdf" if comic_name else f"{pdf_prefix}{book_name}.pdf"
        output_path = os.path.join(output_folder, output_filename)
        
        print(f"  创建PDF: {output_filename}")
        
        c = canvas.Canvas(output_path, pagesize=(page_width, page_height))

        # 设置PDF元数据，帮助Kindle识别
        title = normalized_book_name if comic_name else Path(zip_file).stem
        c.setTitle(title)
        c.setAuthor("Comic Packer")
        c.setSubject("Comic Book")
        book_title = normalized_book_name if comic_name else book_name
        
        # 2. 收集所有章节的图片
        all_images = []
        chapter_info_list = []  # 记录每个章节的信息
        
        for chapter_name in sorted_chapter_names:
            chapter_images = chapters[chapter_name]
            
            if not chapter_images:
                print(f"    警告: 章节 {chapter_name} 没有图片，跳过")
                continue
            
            print(f"    读取章节: {chapter_name} ({len(chapter_images)} 张图片)")
            
            # 记录章节信息
            chapter_info_list.append({
                'name': chapter_name,
                'start_index': len(all_images),
                'image_count': len(chapter_images)
            })
            
            all_images.extend(chapter_images)
        
        # 3. 预处理所有图片
        if all_images:
            preprocessed_images = preprocess_images(all_images, page_width, page_height)
        else:
            preprocessed_images = []
        
        # 4. 顺序组装PDF
        print(f"  组装PDF...")
        current_img_index = 0
        total_images = 0
        
        for chapter_info in chapter_info_list:
            chapter_name = chapter_info['name']
            
            # 计算这个章节的图片范围
            next_chapter_start = chapter_info_list[chapter_info_list.index(chapter_info) + 1]['start_index'] \
                                if chapter_info_list.index(chapter_info) + 1 < len(chapter_info_list) \
                                else len(preprocessed_images)
            
            # 添加第一张图片（带章节标题书签）
            if current_img_index < len(preprocessed_images):
                img_info = preprocessed_images[current_img_index]
                
                # 设置页面大小
                c.setPageSize((img_info['width'], img_info['height']))
                
                # 添加书签
                c.bookmarkPage(chapter_name)
                c.addOutlineEntry(chapter_name, chapter_name, level=0)
                
                # 绘制图片
                img_reader = ImageReader(io.BytesIO(img_info['data']))
                c.drawImage(img_reader, 0, 0, width=img_info['width'], height=img_info['height'])
                c.showPage()
                
                current_img_index += 1
                total_images += 1
            
            # 添加后续图片（不带标题）
            while current_img_index < next_chapter_start and current_img_index < len(preprocessed_images):
                img_info = preprocessed_images[current_img_index]
                
                # 设置页面大小
                c.setPageSize((img_info['width'], img_info['height']))
                
                # 绘制图片
                img_reader = ImageReader(io.BytesIO(img_info['data']))
                c.drawImage(img_reader, 0, 0, width=img_info['width'], height=img_info['height'])
                c.showPage()
                
                current_img_index += 1
                total_images += 1
        
        # 保存PDF
        c.save()
        print(f"  ✓ PDF创建完成: {output_filename}")
        print(f"    共 {len(sorted_chapter_names)} 个章节，{total_images} 张图片")
        
        # 如果需要,转换为MOBI
        if convert_to_mobi:
            mobi_path = convert_pdf_to_mobi(output_path, output_folder, kindle_profile)
            if mobi_path:
                print(f"  ✓ MOBI已创建: {Path(mobi_path).name}")
    
    print(f"\n所有书籍打包完成！共处理 {len(zip_files)} 本书")
    if convert_to_mobi:
        print(f"  MOBI转换已完成")
    
    # 报告完成
    if progress_callback:
        progress_callback('completed', len(zip_files), len(zip_files), 
                         f'所有书籍打包完成！共处理 {len(zip_files)} 本书')




def pack_comics_to_pdf(folder_path: str, batch_size: int = 10, pdf_prefix: str = "", 
                        output_folder: str = './output', convert_to_mobi: bool = False, 
                        kindle_profile: str = 'KPW5', progress_callback: Optional[Callable] = None):
    """
    主函数:将文件夹中的ZIP文件按批次打包成PDF
    
    参数:
        folder_path: 包含ZIP文件的文件夹路径
        batch_size: 每个PDF包含的章节数量(默认10)
        pdf_prefix: PDF文件名前缀(默认"")
        output_folder: 输出PDF文件的文件夹路径(默认'./output')
        convert_to_mobi: 是否转换为MOBI格式(默认False)
        kindle_profile: Kindle设备配置文件(默认'KPW5')
        progress_callback: 进度回调函数(可选)
    """
    # 创建输出文件夹(如果不存在)
    os.makedirs(output_folder, exist_ok=True)
    
    # 获取所有ZIP文件并排序
    zip_files = get_sorted_zip_files(folder_path)
    
    if not zip_files:
        print(f"错误: 在 {folder_path} 中没有找到ZIP文件")
        return
    
    print(f"找到 {len(zip_files)} 个ZIP文件")
    print(f"批次大小: {batch_size} 个章节/PDF")
    print(f"PDF文件名前缀: {pdf_prefix}")
    print(f"输出文件夹: {output_folder}")
    if convert_to_mobi:
        print(f"MOBI转换: 启用 (设备配置: {kindle_profile})")
    
    # 分批处理
    total_batches = (len(zip_files) + batch_size - 1) // batch_size
    
    # 报告初始进度
    if progress_callback:
        progress_callback('scanning', 0, total_batches, f'找到 {len(zip_files)} 个ZIP文件，共 {total_batches} 个批次')
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(zip_files))
        
        batch_files = zip_files[start_idx:end_idx]
        
        # 报告当前批次进度
        if progress_callback:
            progress_callback('processing', batch_num, total_batches, 
                            f'处理批次 {batch_num + 1}/{total_batches}')
        
        # 生成输出文件名
        first_chapter = extract_chapter_name(batch_files[0])
        last_chapter = extract_chapter_name(batch_files[-1])
        prefix_part = f"{pdf_prefix}_" if pdf_prefix else ""
        output_filename = f"{prefix_part}{first_chapter}_to_{last_chapter}.pdf"
        
        # 创建PDF
        create_pdf_from_chapters(batch_files, folder_path, output_filename, batch_num + 1, output_folder)
        
        # 如果需要,转换为MOBI
        if convert_to_mobi:
            pdf_path = os.path.join(output_folder, output_filename)
            mobi_path = convert_pdf_to_mobi(pdf_path, output_folder, kindle_profile)
            if mobi_path:
                print(f"  ✓ MOBI已创建: {Path(mobi_path).name}")
    
    print(f"\n✓ 全部完成! 共创建 {total_batches} 个PDF文件")
    if convert_to_mobi:
        print(f"  MOBI转换已完成")
    
    # 报告完成
    if progress_callback:
        progress_callback('completed', total_batches, total_batches, 
                         f'全部完成! 共创建 {total_batches} 个PDF文件')



def convert_cbz_to_pdf(folder_path: str, cbz_prefix: str = "", output_folder: str = './output',
                        convert_to_mobi: bool = False, kindle_profile: str = 'KPW5',
                        progress_callback: Optional[Callable] = None,
                        comic_name: str = ""):
    """
    CBZ转PDF模式：将文件夹中的每个CBZ文件转换为单独的PDF
    使用第一张图片作为封面，确保在Kindle上正确显示
    支持检测CBZ内部的章节结构（文件夹），并为每个章节的第一张图片添加书签索引
    
    参数:
        folder_path: 包含CBZ文件的文件夹路径
        cbz_prefix:  cbz文件名前缀（默认""）
        output_folder: 输出PDF文件的文件夹路径（默认'./output'）
        convert_to_mobi: 是否转换为MOBI格式(默认False)
        kindle_profile: Kindle设备配置文件(默认'KPW5')
        progress_callback: 进度回调函数(可选)
    """
    # 创建输出文件夹（如果不存在）
    os.makedirs(output_folder, exist_ok=True)
    
    # 获取所有CBZ文件（CBZ本质上是ZIP文件）
    cbz_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.cbz')]
    cbz_files.sort(key=natural_sort_key)
    
    if not cbz_files:
        print(f"错误: 在 {folder_path} 中没有找到CBZ文件")
        return
    
    print(f"找到 {len(cbz_files)} 个CBZ文件")
    print(f"转换模式: CBZ -> PDF (每个CBZ生成一个PDF，自动检测章节)")
    if comic_name:
        print(f"规范漫画名: {comic_name}")
    print(f"输出文件夹: {output_folder}")
    if convert_to_mobi:
        print(f"MOBI转换: 启用 (设备配置: {kindle_profile})")
    
    # 报告初始进度
    if progress_callback:
        progress_callback('scanning', 0, len(cbz_files), f'找到 {len(cbz_files)} 个CBZ文件')
    
    success_count = 0
    
    for idx, cbz_file in enumerate(cbz_files, 1):
        cbz_path = os.path.join(folder_path, cbz_file)
        
        # 生成PDF文件名（优先使用规范化的 漫画名 Vol.xx 命名）
        normalized_cbz_name = build_normalized_volume_name(cbz_file, comic_name) if comic_name else Path(cbz_file).stem
        prefix_part = f"{cbz_prefix}_" if cbz_prefix else ""
        pdf_filename = f"{normalized_cbz_name}.pdf" if comic_name else f"{prefix_part}{Path(cbz_file).stem}.pdf"
        output_path = os.path.join(output_folder, pdf_filename)
        
        print(f"\n[{idx}/{len(cbz_files)}] 处理: {cbz_file}")
        
        # 报告当前文件进度
        if progress_callback:
            progress_callback('processing', idx - 1, len(cbz_files), 
                            f'处理 {idx}/{len(cbz_files)}: {cbz_file}')
        
        try:
            # 尝试按章节提取图片（检测文件夹结构）
            chapters = get_chapters_from_zip(cbz_path)
            
            if not chapters:
                print(f"  ⚠ 警告: {cbz_file} 中没有找到图片，跳过")
                continue
            
            # 检查是否有真正的章节结构（多个文件夹或非"默认章节"）
            has_chapters = len(chapters) > 1 or (len(chapters) == 1 and "默认章节" not in chapters)
            
            if has_chapters:
                # 对章节名进行排序
                sorted_chapter_names = sorted(chapters.keys(), key=natural_sort_key)
                print(f"  检测到 {len(sorted_chapter_names)} 个章节: {', '.join(sorted_chapter_names[:3])}{'...' if len(sorted_chapter_names) > 3 else ''}")
            else:
                print(f"  未检测到章节结构，作为单一文档处理")
            
            # 统计总图片数
            total_images = sum(len(imgs) for imgs in chapters.values())
            print(f"  找到 {total_images} 张图片")
            
            # 获取第一张图片作为封面
            if has_chapters:
                first_chapter_name = sorted(chapters.keys(), key=natural_sort_key)[0]
                first_image_data = chapters[first_chapter_name][0][1]
            else:
                first_image_data = list(chapters.values())[0][0][1]
            
            # 使用第一张图片的尺寸作为PDF页面大小（用于封面）
            first_img = Image.open(io.BytesIO(first_image_data))
            cover_width, cover_height = first_img.size
            
            # 创建PDF
            c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
            
            # 设置PDF元数据
            title = normalized_cbz_name if comic_name else Path(cbz_file).stem
            c.setTitle(title)
            c.setAuthor("Comic Packer")
            c.setSubject("Comic Book")
            
            # 第一页：封面（添加书签）
            c.bookmarkPage("封面")
            c.addOutlineEntry("封面", "封面", level=0)
            
            print(f"  添加封面 ({cover_width}x{cover_height})")
            img_reader = ImageReader(io.BytesIO(first_image_data))
            c.drawImage(img_reader, 0, 0, width=cover_width, height=cover_height)
            c.showPage()
            
            
            if has_chapters:
                # 有章节结构：收集所有图片（跳过第一章的第一张，已作为封面）
                sorted_chapter_names = sorted(chapters.keys(), key=natural_sort_key)
                
                all_images = []
                chapter_bookmarks = []  # 记录需要添加书签的位置
                
                for chapter_idx, chapter_name in enumerate(sorted_chapter_names, 1):
                    chapter_images = chapters[chapter_name]
                    
                    for img_idx, (img_name, img_data) in enumerate(chapter_images):
                        # 跳过第一章的第一张图片（已作为封面）
                        if chapter_idx == 1 and img_idx == 0:
                            continue
                        
                        # 如果是章节的第一张图片，记录书签位置
                        if img_idx == 0:
                            chapter_bookmarks.append({
                                'index': len(all_images),
                                'name': chapter_name
                            })
                        
                        all_images.append((img_name, img_data))
                
                # 预处理所有图片
                if all_images:
                    print(f"  预处理 {len(all_images)} 张图片...")
                    preprocessed_images = preprocess_images(all_images, page_width, page_height)
                else:
                    preprocessed_images = []
                
                # 顺序组装PDF
                print(f"  组装PDF...")
                for idx, img_info in enumerate(preprocessed_images):
                    # 检查是否需要添加书签
                    for bookmark in chapter_bookmarks:
                        if bookmark['index'] == idx:
                            c.bookmarkPage(bookmark['name'])
                            c.addOutlineEntry(bookmark['name'], bookmark['name'], level=0)
                            break
                    
                    # 设置页面大小
                    c.setPageSize((img_info['width'], img_info['height']))
                    
                    # 绘制图片
                    img_reader = ImageReader(io.BytesIO(img_info['data']))
                    c.drawImage(img_reader, 0, 0, width=img_info['width'], height=img_info['height'])
                    c.showPage()
                
                print(f"  ✓ 已添加 {len(sorted_chapter_names)} 个章节书签")
            else:
                # 无章节结构：直接处理所有图片（跳过第一张，已作为封面）
                all_images = list(chapters.values())[0]
                
                # 收集除封面外的所有图片
                images_to_process = all_images[1:]
                
                # 预处理所有图片
                if images_to_process:
                    print(f"  预处理 {len(images_to_process)} 张图片...")
                    preprocessed_images = preprocess_images(images_to_process, page_width, page_height)
                else:
                    preprocessed_images = []
                
                # 顺序组装PDF
                print(f"  组装PDF...")
                for img_info in preprocessed_images:
                    # 设置页面大小
                    c.setPageSize((img_info['width'], img_info['height']))
                    
                    # 绘制图片
                    img_reader = ImageReader(io.BytesIO(img_info['data']))
                    c.drawImage(img_reader, 0, 0, width=img_info['width'], height=img_info['height'])
                    c.showPage()
            
            c.save()
            success_count += 1
            print(f"  ✓ 完成: {pdf_filename}")
            
            # 如果需要,转换为MOBI
            if convert_to_mobi:
                mobi_path = convert_pdf_to_mobi(output_path, output_folder, kindle_profile)
                if mobi_path:
                    print(f"  ✓ MOBI已创建: {Path(mobi_path).name}")
            
        except Exception as e:
            print(f"  ✗ 错误: 处理 {cbz_file} 时出错 - {e}")
    
    print(f"\n{'='*50}")
    print(f"✓ 转换完成! 成功: {success_count}/{len(cbz_files)}")
    print(f"输出目录: {output_folder}")
    if convert_to_mobi:
        print(f"  MOBI转换已完成")
    
    # 报告完成
    if progress_callback:
        progress_callback('completed', len(cbz_files), len(cbz_files), 
                         f'转换完成! 成功: {success_count}/{len(cbz_files)}')



def _run_kcc_conversion(cmd: List[str], pdf_name: str, project_dir: str = None):
    """
    在独立进程中运行KCC转换命令
    
    参数:
        cmd: KCC命令列表
        pdf_name: PDF文件名(用于日志)
        project_dir: 项目根目录路径(用于设置PYTHONPATH)
    """
    try:
        # 设置环境变量，确保 KCC 脚本能找到模块
        env = os.environ.copy()
        if project_dir:
            # 添加项目根目录到 PYTHONPATH
            pythonpath = env.get('PYTHONPATH', '')
            if pythonpath:
                env['PYTHONPATH'] = f"{project_dir}:{pythonpath}" # Prepend project_dir
            else:
                env['PYTHONPATH'] = project_dir
        
        # 执行转换命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,  # 使用修改后的环境变量
            timeout=300  # 5分钟超时
        )
        
        if result.returncode == 0:
            print(f"  ✓ MOBI转换完成: {pdf_name}")
        else:
            print(f"  ✗ MOBI转换失败: {pdf_name} (退出码: {result.returncode})")
            if result.stderr:
                print(f"  错误信息: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print(f"  ✗ MOBI转换超时: {pdf_name} (超过5分钟)")
    except Exception as e:
        print(f"  ✗ MOBI转换出错: {pdf_name} - {e}")


def convert_pdf_to_mobi(pdf_path: str, output_folder: Optional[str] = None, 
                        device_profile: str = 'KPW5') -> Optional[str]:
    """
    使用KCC (Kindle Comic Converter)将PDF转换为MOBI格式
    使用多进程方式启动转换,不等待完成
    
    参数:
        pdf_path: PDF文件的路径
        output_folder: 可选的输出目录(默认:与PDF相同目录)
        device_profile: KCC设备配置文件(默认:KPW5表示Kindle Paperwhite 5)
    
    返回:
        预期的MOBI文件路径,如果无法启动转换则返回None
    """
    # 获取当前脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    kcc_script_path = os.path.join(script_dir, 'kcc', 'kcc-c2e.py')
    
    # 检查KCC是否可用(优先使用本地脚本,其次使用系统命令)
    use_local_script = os.path.exists(kcc_script_path)
    use_system_command = shutil.which('kcc-c2e') is not None
    
    if not use_local_script and not use_system_command:
        print(f"  ⚠ 警告: 未找到KCC。请先安装或将KCC源码放在项目的kcc目录下")
        print(f"  本地脚本路径: {kcc_script_path}")
        print(f"  或安装系统命令: https://github.com/ciromattia/kcc")
        return None
    
    # 检查PDF文件是否存在
    if not os.path.exists(pdf_path):
        print(f"  ✗ 错误: PDF文件不存在: {pdf_path}")
        return None
    
    # 确定输出目录
    if output_folder is None:
        output_folder = os.path.dirname(pdf_path)
    
    # 生成MOBI文件名
    pdf_name = Path(pdf_path).stem
    mobi_filename = f"{pdf_name}.mobi"
    expected_mobi_path = os.path.join(output_folder, mobi_filename)
    
    print(f"  正在转换为MOBI: {Path(pdf_path).name}")
    if use_local_script:
        print(f"    使用本地KCC脚本")
    
    pdf_path = os.path.abspath(pdf_path)
    output_folder = os.path.abspath(output_folder)

    # 构建KCC命令
    # -p: 设备配置文件
    # -f MOBI: 输出格式
    # -o: 输出目录
    if use_local_script:
        # 使用本地Python脚本
        cmd = [
            'python3',
            kcc_script_path,
            '-p', device_profile,
            '-f', 'MOBI',
            '-o', output_folder,
            pdf_path
        ]
    else:
        # 使用系统命令
        cmd = [
            'kcc-c2e',
            '-p', device_profile,
            '-f', 'MOBI',
            '-o', output_folder,
            pdf_path
        ]
    
    # 启动独立进程执行转换
    # 传递项目根目录作为 PYTHONPATH
    process = Process(target=_run_kcc_conversion, args=(cmd, Path(pdf_path).name, script_dir))
    process.start()
    
    # 将进程添加到全局进程池
    conversion_processes.append(process)
    
    print(f"  已启动MOBI转换进程: {Path(pdf_path).name}")
    
    # 返回预期的MOBI文件路径
    return expected_mobi_path




if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(
        description="Comic Packer - 将ZIP文件中的漫画图片打包成PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                                    # 使用默认设置（批次模式）
  python main.py --prefix "我的漫画"                 # 自定义文件名前缀
  python main.py --batch-size 15                    # 每15个章节一个PDF
  python main.py --folder ./comics --prefix "寓言杀手"  # 指定文件夹和前缀
  python main.py --output ./my_pdfs                 # 指定自定义输出文件夹
  python main.py --mode book                        # 按书打包（检测图片序号重置）
  python main.py --mode book --prefix "我的漫画"     # 按书打包并自定义前缀
  python main.py --mode cbz --folder ./cbz_files    # CBZ转PDF模式
  python main.py --mode cbz --folder ./cbz --output ./pdfs  # CBZ转PDF并指定输出目录
        """
    )
    
    parser.add_argument(
        '--folder',
        type=str,
        default='./comic',
        help='包含ZIP文件的文件夹路径 (默认: ./comic)'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='每个PDF包含的章节数量 (默认: 10)'
    )
    
    parser.add_argument(
        '--prefix',
        type=str,
        default='',
        help='PDF文件名前缀 (默认: )'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='./output',
        help='输出PDF文件的文件夹路径 (默认: ./output)'
    )
    
    parser.add_argument(
        '--mode',
        type=str,
        choices=['batch', 'book', 'cbz'],
        default='batch',
        help='打包模式: batch=固定批次打包, book=按书打包（检测图片序号重置）, cbz=CBZ转PDF (默认: batch)'
    )
    
    parser.add_argument(
        '--convert-to-mobi',
        action='store_true',
        help='将生成的PDF文件转换为MOBI格式(需要先安装KCC - Kindle Comic Converter)'
    )
    
    parser.add_argument(
        '--kindle-profile',
        type=str,
        default='KPW5',
        choices=['K1', 'K2', 'K34', 'K578', 'KDX', 'KPW', 'KPW5', 'KV', 'KO', 'K11', 'KS'],
        help='Kindle设备配置文件,用于MOBI转换 (默认: KPW5表示Kindle Paperwhite 5)'
    )

    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 根据模式执行不同的打包逻辑
    if args.mode == 'book':
        pack_comics_by_book(args.folder, args.prefix, args.output, 
                           args.convert_to_mobi, args.kindle_profile)
    elif args.mode == 'cbz':
        convert_cbz_to_pdf(args.folder, args.prefix, args.output,
                          args.convert_to_mobi, args.kindle_profile)
    else:
        pack_comics_to_pdf(args.folder, args.batch_size, args.prefix, args.output,
                          args.convert_to_mobi, args.kindle_profile)
    
    # 等待所有MOBI转换进程完成
    if conversion_processes:
        print(f"\n等待 {len(conversion_processes)} 个MOBI转换进程完成...")
        for process in conversion_processes:
            process.join()
        print("所有MOBI转换进程已完成")
        
        # 如果启用了MOBI转换，删除output文件夹下所有PDF文件
        if args.convert_to_mobi:
            print(f"\n清理PDF文件...")
            pdf_count = 0
            for filename in os.listdir(args.output):
                if filename.lower().endswith('.pdf'):
                    pdf_path = os.path.join(args.output, filename)
                    try:
                        os.remove(pdf_path)
                        pdf_count += 1
                        print(f"  已删除: {filename}")
                    except Exception as e:
                        print(f"  删除失败: {filename} - {e}")
            print(f"✓ 已清理 {pdf_count} 个PDF文件")
