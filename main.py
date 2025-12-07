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
from typing import List, Tuple, Optional
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io

page_width, page_height = 1236, 1648

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
    
    c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
    
    print(f"\n创建PDF: {output_filename}")
    print(f"包含章节: {', '.join([extract_chapter_name(z) for z in zip_files])}")
    
    for zip_file in zip_files:
        zip_path = os.path.join(folder_path, zip_file)
        chapter_name = extract_chapter_name(zip_file)
        
        print(f"  处理章节: {chapter_name}")
        
        # 添加章节标题页（会自动添加书签）
        create_title_page(c, chapter_name, page_width, page_height)
        
        # 获取章节中的所有图片
        images = get_images_from_zip(zip_path)
        print(f"    找到 {len(images)} 张图片")
        
        # 将每张图片添加到PDF
        for idx, (img_name, img_data) in enumerate(images, 1):
            add_image_to_pdf(c, img_data, page_width, page_height)
    
    c.save()
    print(f"✓ PDF创建完成: {output_filename}")
    print(f"  已添加 {len(zip_files)} 个章节书签")


def pack_comics_by_book(folder_path: str, pdf_prefix: str = "漫画合集", output_folder: str = './output',
                        convert_to_mobi: bool = False, kindle_profile: str = 'KPW5'):
    """
    按书打包：每个ZIP压缩包下有若干文件夹（章节），将这些章节打包成一个PDF
    - 使用最小章节的第一张图片作为整本书的封面
    - 每个章节的第一页图片上叠加章节名称索引
    
    参数:
        folder_path: 包含ZIP文件的文件夹路径
        pdf_prefix: PDF文件名前缀（默认"漫画合集"）
        output_folder: 输出PDF文件的文件夹路径（默认'./output')
        convert_to_mobi: 是否转换为MOBI格式(默认False)
        kindle_profile: Kindle设备配置文件(默认'KPW5')
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
    print(f"输出文件夹: {output_folder}")
    if convert_to_mobi:
        print(f"MOBI转换: 启用 (设备配置: {kindle_profile})")
    
    # 处理每个ZIP文件（每个ZIP是一本书）
    for book_idx, zip_file in enumerate(zip_files, 1):
        zip_path = os.path.join(folder_path, zip_file)
        book_name = Path(zip_file).stem  # 去掉.zip后缀
        
        print(f"\n处理书籍 {book_idx}/{len(zip_files)}: {book_name}")
        
        # 从ZIP中提取章节
        chapters = get_chapters_from_zip(zip_path)
        
        if not chapters:
            print(f"  警告: {zip_file} 中没有找到图片，跳过")
            continue
        
        # 对章节名进行排序
        sorted_chapter_names = sorted(chapters.keys(), key=natural_sort_key)
        
        print(f"  找到 {len(sorted_chapter_names)} 个章节: {', '.join(sorted_chapter_names)}")
        
        # 获取封面图片（最小章节的第一张图片）
        # first_chapter_name = sorted_chapter_names[0]
        # first_chapter_images = chapters[first_chapter_name]
        
        # if not first_chapter_images:
        #     print(f"  警告: 第一章节 {first_chapter_name} 没有图片，跳过此书")
        #     continue
        
        # cover_image_data = first_chapter_images[0][1]  # 第一张图片的数据
        
        # 创建PDF文件
        output_filename = f"{pdf_prefix}{book_name}.pdf"
        output_path = os.path.join(output_folder, output_filename)
        
        print(f"  创建PDF: {output_filename}")
        
        c = canvas.Canvas(output_path, pagesize=(page_width, page_height))

        # 设置PDF元数据，帮助Kindle识别
        title = Path(zip_file).stem
        c.setTitle(title)
        c.setAuthor("Comic Packer")
        c.setSubject("Comic Book")
        
        # 1. 添加封面（使用第一章节的第一张图片）
        book_title = book_name
        # create_image_cover_page(c, book_title, cover_image_data, page_width, page_height)
        # print(f"    ✓ 已添加封面")
        
        # 2. 处理每个章节
        total_images = 0
        for chapter_name in sorted_chapter_names:
            chapter_images = chapters[chapter_name]
            
            if not chapter_images:
                print(f"    警告: 章节 {chapter_name} 没有图片，跳过")
                continue
            
            print(f"    ✓ 章节: {chapter_name}")
            
            # 添加章节的所有图片
            # 第一张图片添加章节标题索引
            first_img_name, first_img_data = chapter_images[0]
            add_image_to_pdf(c, first_img_data, page_width, page_height, chapter_title=chapter_name)
            total_images += 1
            
            # 后续图片不添加标题
            for img_name, img_data in chapter_images[1:]:
                add_image_to_pdf(c, img_data, page_width, page_height)
                total_images += 1
            
            print(f"      添加了 {len(chapter_images)} 张图片（第一张带索引）")
        
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




def pack_comics_to_pdf(folder_path: str, batch_size: int = 10, pdf_prefix: str = "漫画合集", 
                        output_folder: str = './output', convert_to_mobi: bool = False, 
                        kindle_profile: str = 'KPW5'):
    """
    主函数:将文件夹中的ZIP文件按批次打包成PDF
    
    参数:
        folder_path: 包含ZIP文件的文件夹路径
        batch_size: 每个PDF包含的章节数量(默认10)
        pdf_prefix: PDF文件名前缀(默认"漫画合集")
        output_folder: 输出PDF文件的文件夹路径(默认'./output')
        convert_to_mobi: 是否转换为MOBI格式(默认False)
        kindle_profile: Kindle设备配置文件(默认'KPW5')
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
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(zip_files))
        
        batch_files = zip_files[start_idx:end_idx]
        
        # 生成输出文件名
        first_chapter = extract_chapter_name(batch_files[0])
        last_chapter = extract_chapter_name(batch_files[-1])
        output_filename = f"{pdf_prefix}_{first_chapter}_to_{last_chapter}.pdf"
        
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



def convert_cbz_to_pdf(folder_path: str, cbz_prefix: str = "comic", output_folder: str = './output',
                        convert_to_mobi: bool = False, kindle_profile: str = 'KPW5'):
    """
    CBZ转PDF模式：将文件夹中的每个CBZ文件转换为单独的PDF
    使用第一张图片作为封面，确保在Kindle上正确显示
    支持检测CBZ内部的章节结构（文件夹），并为每个章节的第一张图片添加书签索引
    
    参数:
        folder_path: 包含CBZ文件的文件夹路径
        cbz_prefix:  cbz文件名前缀（默认"comic"）
        output_folder: 输出PDF文件的文件夹路径（默认'./output'）
        convert_to_mobi: 是否转换为MOBI格式(默认False)
        kindle_profile: Kindle设备配置文件(默认'KPW5')
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
    print(f"输出文件夹: {output_folder}")
    if convert_to_mobi:
        print(f"MOBI转换: 启用 (设备配置: {kindle_profile})")
    
    success_count = 0
    
    for idx, cbz_file in enumerate(cbz_files, 1):
        cbz_path = os.path.join(folder_path, cbz_file)
        
        # 生成PDF文件名（去掉.cbz扩展名，添加.pdf）
        pdf_filename = f"{cbz_prefix}_{Path(cbz_file).stem}.pdf"
        output_path = os.path.join(output_folder, pdf_filename)
        
        print(f"\n[{idx}/{len(cbz_files)}] 处理: {cbz_file}")
        
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
            title = Path(cbz_file).stem
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
                # 有章节结构：为每个章节的第一张图片添加书签
                sorted_chapter_names = sorted(chapters.keys(), key=natural_sort_key)
                
                for chapter_idx, chapter_name in enumerate(sorted_chapter_names, 1):
                    chapter_images = chapters[chapter_name]
                    
                    for img_idx, (img_name, img_data) in enumerate(chapter_images):
                        # 跳过第一章的第一张图片（已作为封面）
                        if chapter_idx == 1 and img_idx == 0:
                            continue
                        
                        try:
                            # 打开图片获取尺寸
                            img = Image.open(io.BytesIO(img_data))
                            img_width, img_height = img.size
                            
                            # 计算图片的宽高比
                            img_aspect_ratio = img_width / img_height
                            page_aspect_ratio = page_width / page_height
                            
                            # 根据宽高比调整页面大小
                            if img_aspect_ratio > page_aspect_ratio:
                                actual_width = page_width
                                actual_height = page_width / img_aspect_ratio
                            else:
                                actual_height = page_height
                                actual_width = page_height * img_aspect_ratio
                            
                            # 设置当前页面大小
                            c.setPageSize((actual_width, actual_height))
                            
                            # 如果是章节的第一张图片，添加书签（但不在页面上显示文字）
                            if img_idx == 0:
                                c.bookmarkPage(chapter_name)
                                c.addOutlineEntry(chapter_name, chapter_name, level=0)
                            
                            # 绘制图片
                            img_reader = ImageReader(io.BytesIO(img_data))
                            c.drawImage(img_reader, 0, 0, width=actual_width, height=actual_height)
                            c.showPage()
                            
                        except Exception as e:
                            print(f"  ⚠ 警告: 无法处理图片 {img_name} - {e}")
                
                print(f"  ✓ 已添加 {len(sorted_chapter_names)} 个章节书签")
            else:
                # 无章节结构：直接处理所有图片（跳过第一张，已作为封面）
                all_images = list(chapters.values())[0]
                
                for img_name, img_data in all_images[1:]:
                    try:
                        # 打开图片获取尺寸
                        img = Image.open(io.BytesIO(img_data))
                        img_width, img_height = img.size
                        
                        # 计算图片的宽高比
                        img_aspect_ratio = img_width / img_height
                        page_aspect_ratio = page_width / page_height
                        
                        # 根据宽高比调整页面大小
                        if img_aspect_ratio > page_aspect_ratio:
                            actual_width = page_width
                            actual_height = page_width / img_aspect_ratio
                        else:
                            actual_height = page_height
                            actual_width = page_height * img_aspect_ratio
                        
                        # 设置当前页面大小
                        c.setPageSize((actual_width, actual_height))
                        
                        # 绘制图片
                        img_reader = ImageReader(io.BytesIO(img_data))
                        c.drawImage(img_reader, 0, 0, width=actual_width, height=actual_height)
                        c.showPage()
                        
                    except Exception as e:
                        print(f"  ⚠ 警告: 无法处理图片 {img_name} - {e}")
            
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



def convert_pdf_to_mobi(pdf_path: str, output_folder: Optional[str] = None, 
                        device_profile: str = 'KPW5') -> Optional[str]:
    """
    使用KCC (Kindle Comic Converter)将PDF转换为MOBI格式
    
    参数:
        pdf_path: PDF文件的路径
        output_folder: 可选的输出目录(默认:与PDF相同目录)
        device_profile: KCC设备配置文件(默认:KPW5表示Kindle Paperwhite 5)
    
    返回:
        生成的MOBI文件路径,如果转换失败则返回None
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

    try:
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
        
        # 执行转换
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        # 检查是否成功
        if result.returncode == 0:
            # KCC可能会在文件名后添加设备配置文件名,尝试查找生成的文件
            possible_paths = [
                expected_mobi_path,
                os.path.join(output_folder, f"{pdf_name}_{device_profile}.mobi"),
                os.path.join(output_folder, f"{pdf_name}-{device_profile}.mobi"),
            ]
            
            for mobi_path in possible_paths:
                if os.path.exists(mobi_path):
                    return mobi_path
            
            # 如果找不到预期的文件,在输出目录中搜索最新的.mobi文件
            mobi_files = list(Path(output_folder).glob(f"{pdf_name}*.mobi"))
            if mobi_files:
                # 按修改时间排序,返回最新的
                latest_mobi = max(mobi_files, key=lambda p: p.stat().st_mtime)
                return str(latest_mobi)
            
            print(f"  ⚠ 警告: KCC执行成功但未找到生成的MOBI文件")
            return None
        else:
            print(f"  ✗ KCC转换失败 (退出码: {result.returncode})")
            if result.stderr:
                print(f"  错误信息: {result.stderr[:200]}")
            return None
            
    except subprocess.TimeoutExpired:
        print(f"  ✗ 错误: KCC转换超时(超过5分钟)")
        return None
    except Exception as e:
        print(f"  ✗ 错误: KCC转换时出错 - {e}")
        return None




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
        default='漫画合集',
        help='PDF文件名前缀 (默认: 漫画合集)'
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

