#!/bin/bash
# ComicPacker Web Server 启动脚本

echo "======================================"
echo "ComicPacker Web 服务器启动脚本"
echo "======================================"
echo ""

# 检查虚拟环境
if [ -d ".venv" ]; then
    echo "✓ 找到虚拟环境"
    PYTHON=".venv/bin/python"
else
    echo "⚠ 未找到虚拟环境，使用系统Python"
    PYTHON="python3"
fi

# 检查依赖
echo "检查依赖..."
$PYTHON -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ Flask未安装，正在安装依赖..."
    $PYTHON -m pip install -r requirements.txt
else
    echo "✓ 依赖已安装"
fi

echo ""
echo "启动Web服务器..."
echo "访问地址: http://localhost:5000"
echo "按 Ctrl+C 停止服务器"
echo ""

# 启动服务器
$PYTHON web_server.py
