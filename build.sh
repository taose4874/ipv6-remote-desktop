#!/bin/bash

echo "========================================"
echo "IPv6远程桌面 - 打包脚本 (Linux/Mac)"
echo "========================================"
echo ""

echo "[1/4] 检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3，请先安装Python 3.8+"
    exit 1
fi
python3 --version
echo "Python环境检查通过"
echo ""

echo "[2/4] 安装依赖..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "错误: 依赖安装失败"
    exit 1
fi
echo "依赖安装完成"
echo ""

echo "[3/4] 打包服务端..."
pyinstaller --clean server.spec
if [ $? -ne 0 ]; then
    echo "警告: 服务端打包可能出现问题，请检查"
fi
echo "服务端打包完成"
echo ""

echo "[4/4] 打包客户端..."
pyinstaller --clean client.spec
if [ $? -ne 0 ]; then
    echo "警告: 客户端打包可能出现问题，请检查"
fi
echo "客户端打包完成"
echo ""

echo "========================================"
echo "打包完成！"
echo "可执行文件位于 dist 目录中"
echo "========================================"
echo ""
echo "文件列表:"
ls -lh dist/
echo ""
