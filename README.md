# Comic Packer - 漫画打包工具

将ZIP格式的漫画章节自动打包成PDF文件的Python工具。

## 功能特点

- ✅ 自动识别并按章节顺序排序ZIP文件
- ✅ 分批次打包（默认每10个章节一个PDF）
- ✅ 每个章节自动添加标题页
- ✅ 图片零边距显示，每页一张图片
- ✅ 自动处理剩余不足批次大小的章节
- ✅ 支持多种图片格式（JPG, PNG, GIF, BMP, WEBP）
- ✅ **CBZ转PDF模式**：将CBZ文件转换为PDF，封面可在Kindle上正确显示
- ✅ **可选MOBI转换**：使用KCC将PDF转换为MOBI格式，完美适配Kindle设备

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### Web界面（推荐）

使用Web界面可以更方便地管理转换任务：

```bash
# 启动Web服务器
python web_server.py

# 或使用虚拟环境
.venv/bin/python web_server.py
```

然后在浏览器中打开 `http://localhost:5000`

**Web界面功能：**
- 📁 可视化文件浏览器，选择服务器上的文件夹
- ⚙️ 图形化配置界面，支持所有命令行参数
- 📊 实时进度显示，查看转换状态
- 📜 任务历史记录，追踪所有转换任务
- 🎨 现代化深色主题界面

### 命令行使用

### 基本使用（批次模式）

1. 将所有漫画ZIP文件放在 `comic` 文件夹中
2. 运行脚本：

```bash
python main.py
```

### CBZ转PDF模式

将CBZ文件转换为PDF，每个CBZ生成一个独立的PDF文件：

```bash
# 基本用法
python main.py --mode cbz --folder ./cbz_files

# 指定输出目录
python main.py --mode cbz --folder ./cbz_files --output ./my_pdfs

# CBZ转PDF并同时转换为MOBI
python main.py --mode cbz --folder ./cbz_files --convert-to-mobi
```


**CBZ模式特点：**
- 每个CBZ文件生成一个独立的PDF
- 使用第一张图片作为封面
- 封面使用原始图片尺寸，确保在Kindle上正确显示
- 自动设置PDF元数据（标题、作者、主题）

### 按书打包模式

当检测到图片序号重置时自动分书：

```bash
python main.py --mode book --folder ./comics
```

### PDF转MOBI模式

将生成的PDF文件转换为MOBI格式（需要先安装KCC）：

```bash
# 基本用法（转换为MOBI）
python main.py --convert-to-mobi

# 指定Kindle设备型号
python main.py --convert-to-mobi --kindle-profile KPW5

# CBZ模式 + MOBI转换
python main.py --mode cbz --folder ./cbz_files --convert-to-mobi

# 按书打包 + MOBI转换
python main.py --mode book --convert-to-mobi
```

**安装KCC (Kindle Comic Converter):**

```bash
# 方法1: 使用本地KCC脚本(推荐)
# 将KCC源码克隆到项目目录下
cd /path/to/ComicPacker
git clone https://github.com/ciromattia/kcc.git
cd kcc
pip install -r requirements.txt

# 方法2: Ubuntu/Debian(使用Flatpak)
sudo apt install flatpak
flatpak install flathub io.github.ciromattia.kcc

# 方法3: 从源码安装到系统
git clone https://github.com/ciromattia/kcc.git
cd kcc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> **注意**: 程序会优先使用项目目录下的 `kcc/kcc-c2e.py` 脚本,如果不存在则尝试使用系统安装的 `kcc-c2e` 命令。

**支持的Kindle设备配置:**
- `KPW6`: Kindle Paperwhite 6(默认,推荐)
- `KPW5`: Kindle Paperwhite 5
- `KPW`: Kindle Paperwhite (旧版)
- `KV`: Kindle Voyage
- `KO`: Kindle Oasis
- `K11`: Kindle 11th Gen
- `KS`: Kindle Scribe

### 自定义批次大小

```bash
python main.py --batch-size 15  # 每15个章节一个PDF
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
├── comic/              # 存放ZIP/CBZ文件的文件夹
│   ├── 寓言杀手-CH-001.zip
│   ├── 寓言杀手-CH-002.zip
│   └── ...
└── output/             # 输出PDF文件的文件夹（自动创建）
```

## 输出示例

运行后会在 `output` 文件夹中生成PDF文件：

```
漫画合集_CH-001_to_CH-010.pdf
```

## 技术细节

- **自然排序**: 正确处理章节编号（CH-001, CH-002, ..., CH-010）
- **图片缩放**: 自动调整图片大小以适应A4页面
- **章节标题**: 每个章节开始前自动添加标题页
- **零边距**: 图片在页面中居中显示，最大化利用空间
- **Kindle封面**: CBZ模式下，第一页使用原始图片尺寸作为封面，确保Kindle正确识别

## 注意事项

- ZIP/CBZ文件应包含图片文件（支持 JPG, PNG, GIF, BMP, WEBP）
- 建议ZIP文件名包含章节编号以便正确排序
- 批次模式生成的PDF使用A4页面大小
- **CBZ模式**: 封面页使用原始图片尺寸，内容页使用A4尺寸
- **Kindle使用**: CBZ模式生成的PDF可直接传输到Kindle，封面会在图书馆中正确显示



```
/etc/systemd/system/c2m.service

[Unit]
Description=c2m service
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/vol1/1000/code/ComicPacker
ExecStart=/vol1/1000/code/ComicPacker/start_web.sh
StandardOutput=append:/var/log/c2m/c2m.log
StandardError=append:/var/log/c2m/c2m.err
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target

```

sudo systemctl daemon-reload
sudo systemctl enable c2m.service
sudo systemctl restart c2m.service
sudo mkdir -p /var/log/c2m
sudo touch /var/log/c2m/c2m.log /var/log/c2m/c2m.err
sudo chmod 644 /var/log/c2m/c2m.log /var/log/c2m/c2m.err

