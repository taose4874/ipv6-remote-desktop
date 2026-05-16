# IPv6 内网穿透工具

一个简单高效的 IPv6 内网穿透工具，帮助你将内网服务暴露到公网，支持 Minecraft 等游戏联机。

## 功能特点

- ✅ IPv6 原生支持
- ✅ 美观的图形化界面（PyQt6/PyQt5）
- ✅ 同时支持 Windows 10/11 和 Windows 7
- ✅ TCP 端口转发
- ✅ 支持 Minecraft 等游戏联机
- ✅ 自动重连机制
- ✅ 多客户端同时连接
- ✅ 随机端口分配
- ✅ 彩色日志显示

## 系统要求

- **Windows 10/11**: 使用 Win10 版本
- **Windows 7**: 使用 Win7 版本（需要 SP1）

## 使用场景

**你（公网 IPv6）**：运行服务器端
**朋友（内网 IPv6 或 IPv4）**：运行客户端
**结果**：朋友访问 `你的IPv6:分配端口` → 你的本地服务

## 快速开始

### 1. 你（公网 IPv6）：服务器端

下载 `IPv6穿透工具_Win10.zip` 或 `IPv6穿透工具_Win7.zip`，解压后运行 `IPv6穿透服务端_Win10.exe` 或 `IPv6穿透服务端_Win7.exe`：

- 设置控制端口（默认 7000）
- 设置端口范围（默认 25565-65535）
- 点击"保存配置"
- 点击"启动服务"
- 复制显示的 IPv6 地址

配置文件 `config_server.json` 会自动生成在程序目录。

### 2. 朋友（内网）：客户端

下载对应版本的客户端，运行 `IPv6穿透客户端_Win10.exe` 或 `IPv6穿透客户端_Win7.exe`：

- 设置服务器地址（你的公网 IPv6 地址，用方括号括起来，如 `[2001:db8::1]`）
- 设置服务器端口（默认 7000）
- 设置本地服务端口（例如 Minecraft 的 25565）
- 点击"保存配置"
- 点击"连接服务器"
- 连接成功后，复制显示的公网地址

配置文件 `config_client.json` 会自动生成在程序目录。

### 3. 连接游戏

启动 Minecraft，在多人游戏中输入复制的地址（格式如 `[2001:db8::1]:50000`）

## 配置说明

### 服务器端 (config_server.json)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| control_port | 控制端口（客户端连接） | 7000 |
| port_start | 分配端口起始值 | 25565 |
| port_end | 分配端口结束值 | 65535 |

### 客户端 (config_client.json)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| server_addr | 服务器 IPv6 地址 | - |
| server_port | 服务器控制端口 | 7000 |
| local_port | 本地服务端口 | 25565 |

## 工作原理

```
[公网服务器]                      [客户端电脑]
    |                                  |
    | ← 客户端连接控制端口 7000         |
    | → 分配公网端口 (如 50000)        |
    |                                  |
    | ← 外部用户连接 50000             |
    | → 通知客户端创建隧道              |
    | ← 客户端建立隧道连接              |
    | ←→ 数据转发                      |
    |         ↘                       |
    |           转发到本地服务          |
```

## 自动构建

每次推送 tag 到 GitHub 会自动构建 Windows 版本：

```bash
git tag v1.0.0
git push origin v1.0.0
```

从 GitHub Releases 下载预编译的 EXE 文件。

### 手动构建

安装依赖：

**Windows 10/11:**
```bash
pip install -r requirements.txt
pip install pyinstaller
```

**Windows 7:**
```bash
pip install PyQt5>=5.15.0
pip install pyinstaller
```

打包服务器：
```bash
pyinstaller --clean server.spec
```

打包客户端：
```bash
pyinstaller --clean client.spec
```

打包后的文件在 `dist/` 目录。

## 常见问题

**Q: 客户端一直显示"连接中"？**
A: 检查服务器是否正常运行，防火墙是否放行 7000 端口，确认 IPv6 地址格式正确（用方括号括起来）。

**Q: 外部用户无法连接？**
A: 确认服务器有公网 IPv6 地址，防火墙放行了分配的端口。

**Q: Minecraft 无法连接？**
A: 确认本地 Minecraft 服务已启动，本地可以正常连接。

## 许可证

MIT License
