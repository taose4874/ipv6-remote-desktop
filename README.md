# IPv6 游戏联机中继服务器

一个简单高效的 IPv6 游戏联机中继服务器，帮助玩家建立游戏连接。

## 功能特点

- ✅ IPv6 原生支持
- ✅ 房间/房间管理
- ✅ 玩家加入/离开通知
- ✅ 数据中继转发
- ✅ 支持多种游戏协议
- ✅ 轻量级高性能

## 快速开始

### 1. 运行服务器

```bash
python server.py
```

服务器默认监听端口：`3003`

### 2. 配置

修改 `server.py` 中的配置：

```python
PORT = 3003          # 服务器端口
MAX_ROOMS = 100       # 最大房间数
MAX_PLAYERS_PER_ROOM = 10  # 每个房间最大玩家数
```

## 协议说明

### 创建房间
```
CREATE_ROOM|room_id|room_name
```

### 加入房间
```
JOIN_ROOM|room_id|player_id|player_name
```

### 离开房间
```
LEAVE_ROOM|room_id|player_id
```

### 发送数据
```
SEND_DATA|room_id|player_id|data
```

### 广播消息
```
BROADCAST|room_id|player_id|message
```

## 部署

### 使用 GitHub Actions 自动构建

1. 创建 tag 触发构建：
```bash
git tag -a v1.0.0 -m "First Release"
git push origin v1.0.0
```

2. 从 Releases 下载 exe 文件

### 手动构建

```bash
pip install -r requirements.txt
pyinstaller --clean server.spec
```

## 许可证

MIT License
