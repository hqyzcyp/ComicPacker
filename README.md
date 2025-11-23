# Comic Packer - 漫画打包工具

将ZIP格式的漫画章节自动打包成PDF文件的Python工具。

## 功能特点

- ✅ 自动识别并按章节顺序排序ZIP文件
- ✅ 分批次打包（默认每10个章节一个PDF）
- ✅ 每个章节自动添加标题页
- ✅ 图片零边距显示，每页一张图片
- ✅ 自动处理剩余不足批次大小的章节
- ✅ 支持多种图片格式（JPG, PNG, GIF, BMP, WEBP）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 基本使用

1. 将所有漫画ZIP文件放在 `comic` 文件夹中
2. 运行脚本：

```bash
python main.py
```

### 自定义批次大小

编辑 `main.py` 文件中的 `BATCH_SIZE` 变量：

```python
BATCH_SIZE = 10  # 修改为你想要的数量
```

或者在代码中直接调用：

```python
from main import pack_comics_to_pdf

pack_comics_to_pdf("./comic", batch_size=15)  # 每15个章节一个PDF
```

## 文件结构

```
ComicPacker/
├── main.py              # 主程序
├── requirements.txt     # Python依赖
├── README.md           # 说明文档
└── comic/              # 存放ZIP文件的文件夹
    ├── 寓言杀手-CH-001.zip
    ├── 寓言杀手-CH-002.zip
    └── ...
```

## 输出示例

运行后会在 `comic` 文件夹中生成PDF文件：

```
漫画合集_CH-001_to_CH-010.pdf
```

## 技术细节

- **自然排序**: 正确处理章节编号（CH-001, CH-002, ..., CH-010）
- **图片缩放**: 自动调整图片大小以适应A4页面
- **章节标题**: 每个章节开始前自动添加标题页
- **零边距**: 图片在页面中居中显示，最大化利用空间

## 注意事项

- ZIP文件应包含图片文件（支持 JPG, PNG, GIF, BMP, WEBP）
- 建议ZIP文件名包含章节编号以便正确排序
- 生成的PDF使用A4页面大小
