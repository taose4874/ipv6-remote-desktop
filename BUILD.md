# 打包说明

本项目支持使用 PyInstaller 将程序打包成独立的可执行文件（exe）。

## 🎯 推荐方式：GitHub Actions 自动打包

最简单的方式是使用 GitHub Actions 自动打包！详细说明请查看 [GITHUB.md](GITHUB.md)。

**优势：**
- ✅ 无需 Windows 电脑
- ✅ 一键触发，自动打包
- ✅ 自动上传可供下载
- ✅ 支持版本发布

## 📋 前提条件（本地打包）

- Python 3.8 或更高版本
- Windows 系统（主要用于打包exe）
- 稳定的网络连接（用于下载依赖）

## 🚀 快速开始（本地打包）

### Windows 系统（推荐）

1. 双击运行 `build.bat` 脚本
2. 等待打包完成
3. 在 `dist` 目录中找到生成的 exe 文件

### Linux/Mac 系统

```bash
chmod +x build.sh
./build.sh
```

## 📦 手动打包步骤

如果你想手动控制打包过程，可以按照以下步骤：

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 打包服务端

```bash
pyinstaller --clean server.spec
```

### 3. 打包客户端

```bash
pyinstaller --clean client.spec
```

## 📂 打包产物

打包完成后，会生成以下目录结构：

```
.
├── build/           # 临时构建文件（可删除）
├── dist/            # 最终可执行文件
│   ├── IPv6RemoteDesktop_Server.exe  # 服务端
│   └── IPv6RemoteDesktop_Client.exe  # 客户端
├── server.spec      # 服务端打包配置
└── client.spec      # 客户端打包配置
```

## ⚙️ 配置说明

### 服务端配置 (server.spec)

- **名称**: IPv6RemoteDesktop_Server
- **控制台**: 显示（用于查看日志）
- **单文件模式**: 是（所有文件打包在一个exe中）

### 客户端配置 (client.spec)

- **名称**: IPv6RemoteDesktop_Client
- **控制台**: 隐藏（GUI程序）
- **单文件模式**: 是（所有文件打包在一个exe中）

## 🎯 自定义配置

### 修改程序名称

编辑对应 spec 文件中的 `name` 参数：

```python
exe = EXE(
    ...
    name='你的程序名称',
    ...
)
```

### 添加图标

1. 准备 `.ico` 格式的图标文件
2. 在 spec 文件中添加 icon 参数：

```python
exe = EXE(
    ...
    icon='app.ico',
    ...
)
```

### 不使用单文件模式（减少启动时间）

修改 spec 文件，在 EXE 部分之前添加 COLLECT：

```python
exe = EXE(
    pyz,
    a.scripts,
    [],
    name='程序名',
    ...
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='程序名',
)
```

## 🔍 常见问题

### 1. 打包后无法运行

**问题**: 双击exe后无反应或报错

**解决方案**:
- 以管理员身份运行
- 检查是否有杀毒软件拦截
- 尝试在命令行中运行，查看错误信息

### 2. 文件体积过大

**问题**: 生成的exe文件太大（100MB+）

**解决方案**:
- 使用虚拟环境打包，只安装必要依赖
- 在 spec 文件中添加 `excludes` 排除不需要的模块
- 使用 UPX 压缩（已默认启用）

### 3. 杀毒软件误报

**问题**: exe文件被杀毒软件识别为病毒

**解决方案**:
- 将文件添加到杀毒软件白名单
- 使用数字签名（需要购买证书）
- 告知用户这是误报

### 4. 缺少模块

**问题**: 运行时提示找不到某个模块

**解决方案**:
- 在 spec 文件的 `hiddenimports` 中添加缺失的模块
- 重新打包

## 📝 注意事项

1. **跨平台打包**: 只能在对应平台上打包该平台的可执行文件
   - Windows → Windows exe
   - Linux → Linux 可执行文件
   - Mac → Mac app

2. **依赖问题**: 打包前确保所有依赖都正常安装

3. **测试**: 打包后务必在干净的环境中测试

4. **版本**: 建议使用 Python 3.8-3.11 版本，兼容性最好

5. **防火墙**: 运行时可能需要配置防火墙允许网络访问

## 🛠️ 高级技巧

### 只打包服务端

```bash
pyinstaller --onefile --console --name IPv6RemoteDesktop_Server server/server.py
```

### 只打包客户端

```bash
pyinstaller --onefile --windowed --name IPv6RemoteDesktop_Client client/main.py
```

### 添加版本信息

创建 `version_info.txt` 文件，然后在打包时使用：

```bash
pyinstaller --version-file=version_info.txt client.spec
```

## 📄 许可证

打包后的程序遵循原项目的许可协议。
