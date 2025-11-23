#!/usr/bin/env python3
"""
Comic Packer - 将ZIP文件中的漫画图片打包成PDF
按章节顺序分批次打包，每批默认10个章节，每章节包含标题页
"""

import os
import zipfile
import re
import argparse
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
    """
    # 在创建新页面之前添加书签（书签指向当前页）
    c.bookmarkPage(title)
    c.addOutlineEntry(title, title, level=0)
    
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
        print(f"警告: 无法创建图片封面 - {e}，使用文字标题页")
        # 如果图片处理失败，回退到文字标题页
        create_title_page(c, title, page_width, page_height)


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
                            output_filename: str, batch_number: int, output_folder: str = './output'):
    """
    从多个ZIP文件创建一个PDF文件，并为每个章节添加书签
    """
    output_path = os.path.join(output_folder, output_filename)
    
    # 使用A4页面大小，也可以根据需要调整
    page_width, page_height = A4
    
    c = canvas.Canvas(output_path, pagesize=A4)
    
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


def pack_comics_by_book(folder_path: str, pdf_prefix: str = "漫画合集", output_folder: str = './output'):
    """
    按书打包：当检测到图片名从1开始时，将之前的图片打包成一个PDF
    使用每本书的第一张图片作为封面
    
    参数:
        folder_path: 包含ZIP文件的文件夹路径
        pdf_prefix: PDF文件名前缀（默认"漫画合集"）
        output_folder: 输出PDF文件的文件夹路径（默认'./output'）
    """
    # 创建输出文件夹（如果不存在）
    os.makedirs(output_folder, exist_ok=True)
    
    # 获取所有ZIP文件并排序
    zip_files = get_sorted_zip_files(folder_path)
    
    if not zip_files:
        print(f"错误: 在 {folder_path} 中没有找到ZIP文件")
        return
    
    print(f"找到 {len(zip_files)} 个ZIP文件")
    print(f"打包模式: 按书打包（检测图片序号重置）")
    print(f"PDF文件名前缀: {pdf_prefix}")
    print(f"输出文件夹: {output_folder}")
    
    page_width, page_height = A4
    
    current_book_chapters = []  # 当前书的章节列表
    current_book_images = []    # 当前书的所有图片
    first_image_data = None     # 当前书的第一张图片（用作封面）
    book_count = 0
    
    for idx, zip_file in enumerate(zip_files):
        zip_path = os.path.join(folder_path, zip_file)
        chapter_name = extract_chapter_name(zip_file)
        images = get_images_from_zip(zip_path)
        
        if not images:
            print(f"警告: {zip_file} 中没有找到图片，跳过")
            continue
        
        # 检查第一张图片是否表示新书的开始
        first_img_name = images[0][0]
        is_new_book = is_first_image(first_img_name)
        
        # 如果检测到新书开始，且已有积累的图片，则打包之前的书
        if is_new_book and current_book_images:
            book_count += 1
            first_chapter = extract_chapter_name(current_book_chapters[0])
            last_chapter = extract_chapter_name(current_book_chapters[-1])
            output_filename = f"{pdf_prefix}_Book{book_count}_{first_chapter}_to_{last_chapter}.pdf"
            output_path = os.path.join(output_folder, output_filename)
            
            print(f"\n创建PDF: {output_filename}")
            print(f"包含章节: {', '.join([extract_chapter_name(z) for z in current_book_chapters])}")
            
            c = canvas.Canvas(output_path, pagesize=A4)
            
            # 使用第一张图片创建封面
            book_title = f"Book {book_count}: {first_chapter} - {last_chapter}"
            if first_image_data:
                create_image_cover_page(c, book_title, first_image_data, page_width, page_height)
            else:
                create_title_page(c, book_title, page_width, page_height)
            
            # 添加所有图片
            for img_data in current_book_images:
                add_image_to_pdf(c, img_data, page_width, page_height)
            
            c.save()
            print(f"✓ PDF创建完成: {output_filename}")
            print(f"  共 {len(current_book_images)} 张图片")
            
            # 重置当前书的数据
            current_book_chapters = []
            current_book_images = []
            first_image_data = None
        
        # 添加当前章节到当前书
        current_book_chapters.append(zip_file)
        
        # 如果是新书的第一个章节，保存第一张图片作为封面
        if not first_image_data:
            first_image_data = images[0][1]
        
        # 添加所有图片到当前书
        print(f"  添加章节: {chapter_name} ({len(images)} 张图片)")
        for img_name, img_data in images:
            current_book_images.append(img_data)
    
    # 处理最后一本书
    if current_book_images:
        book_count += 1
        first_chapter = extract_chapter_name(current_book_chapters[0])
        last_chapter = extract_chapter_name(current_book_chapters[-1])
        output_filename = f"{pdf_prefix}_Book{book_count}_{first_chapter}_to_{last_chapter}.pdf"
        output_path = os.path.join(output_folder, output_filename)
        
        print(f"\n创建PDF: {output_filename}")
        print(f"包含章节: {', '.join([extract_chapter_name(z) for z in current_book_chapters])}")
        
        c = canvas.Canvas(output_path, pagesize=A4)
        
        # 使用第一张图片创建封面
        book_title = f"Book {book_count}: {first_chapter} - {last_chapter}"
        if first_image_data:
            create_image_cover_page(c, book_title, first_image_data, page_width, page_height)
        else:
            create_title_page(c, book_title, page_width, page_height)
        
        # 添加所有图片
        for img_data in current_book_images:
            add_image_to_pdf(c, img_data, page_width, page_height)
        
        c.save()
        print(f"✓ PDF创建完成: {output_filename}")
        print(f"  共 {len(current_book_images)} 张图片")
    
    print(f"\n✓ 全部完成! 共创建 {book_count} 本书的PDF文件")


def pack_comics_to_pdf(folder_path: str, batch_size: int = 10, pdf_prefix: str = "漫画合集", output_folder: str = './output'):
    """
    主函数：将文件夹中的ZIP文件按批次打包成PDF
    
    参数:
        folder_path: 包含ZIP文件的文件夹路径
        batch_size: 每个PDF包含的章节数量（默认10）
        pdf_prefix: PDF文件名前缀（默认"漫画合集"）
        output_folder: 输出PDF文件的文件夹路径（默认'./output'）
    """
    # 创建输出文件夹（如果不存在）
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
    
    print(f"\n✓ 全部完成! 共创建 {total_batches} 个PDF文件")


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
        choices=['batch', 'book'],
        default='batch',
        help='打包模式: batch=固定批次打包, book=按书打包（检测图片序号重置） (默认: batch)'
    )
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 根据模式执行不同的打包逻辑
    if args.mode == 'book':
        pack_comics_by_book(args.folder, args.prefix, args.output)
    else:
        pack_comics_to_pdf(args.folder, args.batch_size, args.prefix, args.output)
