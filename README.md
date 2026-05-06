# IPv6 内网穿透工具

一个简单的 IPv6 内网穿透工具，让公网 IPv6 可以访问内网服务（如 Minecraft）。

## 功能特点

- ✅ IPv6 原生支持
- ✅ TCP 端口转发
- ✅ 支持 Minecraft 等游戏
- ✅ 自动重连
- ✅ 轻量级高性能

## 使用场景

**你（公网 IPv6）**：运行服务器端  
**朋友（内网 IPv6）**：运行客户端  
**结果**：你访问 `你的IPv6:25565` → 朋友的 Minecraft 局域网游戏

## 快速开始

### 1. 你（公网 IPv6）：服务器端

创建配置文件 `config_server.json`：
```json
{
  "control_port": 7000,
  "listen_port": 25565
}
```

运行服务器：
```bash
python server.py
```

### 2. 朋友（内网 IPv6）：客户端

创建配置文件 `config_client.json`：
```json
{
  "server_addr": "你的公网IPv6地址",
  "server_port": 7000,
  "local_port": 25565
}
```

运行客户端：
```bash
python client.py
```

### 3. 连接游戏

启动 Minecraft，在多人游戏中输入：
```
你的公网IPv6:25565
```

## 配置说明

### 服务器端 (config_server.json)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| control_port | 控制端口（客户端连接） | 7000 |
| listen_port | 游戏监听端口（外部访问） | 25565 |

### 客户端 (config_client.json)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| server_addr | 服务器 IPv6 地址 | - |
| server_port | 服务器控制端口 | 7000 |
| local_port | 本地服务端口（如 Minecraft） | 25565 |

## 打包为 EXE

### 使用 GitHub Actions 自动打包

创建 tag 触发自动构建：
```bash
git tag -a v1.0.0 -m "First Release"
git push origin v1.0.0
```

从 GitHub Releases 下载打包好的 EXE 文件。

### 手动打包

安装依赖：
```bash
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

## 工作原理

```
[你的电脑/公网IPv6]          [朋友电脑/内网IPv6]
    ↓                              ↓
[服务端监听7000/25565]   [客户端连接7000]
    ↓                              ↓
游戏连接25565 → 通过隧道 → 朋友的MC
```

## 许可证

MIT License
