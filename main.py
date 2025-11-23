#!/usr/bin/env python3
"""
Comic Packer - 将ZIP文件中的漫画图片打包成PDF
按章节顺序分批次打包，每批默认10个章节，每章节包含标题页
"""

import os
import zipfile
import re
from pathlib import Path
from typing import List, Tuple
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io


def natural_sort_key(filename: str) -> List:
    """
    自然排序键函数，用于正确排序包含数字的文件名
    例如: CH-001, CH-002, ..., CH-010, CH-011
    """
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split('([0-9]+)', filename)]


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
        # 获取所有图片文件并排序
        image_files = [f for f in zip_ref.namelist() 
                      if Path(f).suffix.lower() in image_extensions]
        image_files.sort(key=natural_sort_key)
        
        for image_file in image_files:
            image_data = zip_ref.read(image_file)
            images.append((image_file, image_data))
    
    return images


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


def create_title_page(c: canvas.Canvas, title: str, page_width: float, page_height: float):
    """
    创建章节标题页
    """
    c.setFont("Helvetica-Bold", 36)
    
    # 在页面中央绘制标题
    text_width = c.stringWidth(title, "Helvetica-Bold", 36)
    x = (page_width - text_width) / 2
    y = page_height / 2
    
    c.drawString(x, y, title)
    c.showPage()


def add_image_to_pdf(c: canvas.Canvas, image_data: bytes, page_width: float, page_height: float):
    """
    将图片添加到PDF页面，边距为0，图片填充整个页面
    """
    try:
        # 从字节数据创建PIL图片
        img = Image.open(io.BytesIO(image_data))
        
        # 获取图片尺寸
        img_width, img_height = img.size
        
        # 计算缩放比例以填充页面
        width_ratio = page_width / img_width
        height_ratio = page_height / img_height
        
        # 使用较小的比例以确保图片完全适应页面
        scale = min(width_ratio, height_ratio)
        
        # 计算缩放后的尺寸
        scaled_width = img_width * scale
        scaled_height = img_height * scale
        
        # 居中图片
        x = (page_width - scaled_width) / 2
        y = (page_height - scaled_height) / 2
        
        # 将图片绘制到PDF
        img_reader = ImageReader(io.BytesIO(image_data))
        c.drawImage(img_reader, x, y, width=scaled_width, height=scaled_height)
        c.showPage()
        
    except Exception as e:
        print(f"警告: 无法处理图片 - {e}")


def create_pdf_from_chapters(zip_files: List[str], folder_path: str, 
                            output_filename: str, batch_number: int):
    """
    从多个ZIP文件创建一个PDF文件
    """
    output_path = os.path.join(folder_path, output_filename)
    
    # 使用A4页面大小，也可以根据需要调整
    page_width, page_height = A4
    
    c = canvas.Canvas(output_path, pagesize=A4)
    
    print(f"\n创建PDF: {output_filename}")
    print(f"包含章节: {', '.join([extract_chapter_name(z) for z in zip_files])}")
    
    for zip_file in zip_files:
        zip_path = os.path.join(folder_path, zip_file)
        chapter_name = extract_chapter_name(zip_file)
        
        print(f"  处理章节: {chapter_name}")
        
        # 添加章节标题页
        create_title_page(c, chapter_name, page_width, page_height)
        
        # 获取章节中的所有图片
        images = get_images_from_zip(zip_path)
        print(f"    找到 {len(images)} 张图片")
        
        # 将每张图片添加到PDF
        for idx, (img_name, img_data) in enumerate(images, 1):
            add_image_to_pdf(c, img_data, page_width, page_height)
    
    c.save()
    print(f"✓ PDF创建完成: {output_filename}")


def pack_comics_to_pdf(folder_path: str, batch_size: int = 10):
    """
    主函数：将文件夹中的ZIP文件按批次打包成PDF
    
    参数:
        folder_path: 包含ZIP文件的文件夹路径
        batch_size: 每个PDF包含的章节数量（默认10）
    """
    # 获取所有ZIP文件并排序
    zip_files = get_sorted_zip_files(folder_path)
    
    if not zip_files:
        print(f"错误: 在 {folder_path} 中没有找到ZIP文件")
        return
    
    print(f"找到 {len(zip_files)} 个ZIP文件")
    print(f"批次大小: {batch_size} 个章节/PDF")
    
    # 分批处理
    total_batches = (len(zip_files) + batch_size - 1) // batch_size
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(zip_files))
        
        batch_files = zip_files[start_idx:end_idx]
        
        # 生成输出文件名
        first_chapter = extract_chapter_name(batch_files[0])
        last_chapter = extract_chapter_name(batch_files[-1])
        output_filename = f"漫画合集_{first_chapter}_to_{last_chapter}.pdf"
        
        # 创建PDF
        create_pdf_from_chapters(batch_files, folder_path, output_filename, batch_num + 1)
    
    print(f"\n✓ 全部完成! 共创建 {total_batches} 个PDF文件")


if __name__ == "__main__":
    # 配置参数
    COMIC_FOLDER = "./comic"  # ZIP文件所在文件夹
    BATCH_SIZE = 10  # 每个PDF包含的章节数量
    
    # 执行打包
    pack_comics_to_pdf(COMIC_FOLDER, BATCH_SIZE)
