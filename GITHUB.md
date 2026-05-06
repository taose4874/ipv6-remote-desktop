# GitHub Actions 自动打包指南

本项目已配置 GitHub Actions，可以自动为你打包 Windows exe 文件！

## 🚀 快速开始

### 1. 创建 GitHub 仓库

1. 在 GitHub 上创建一个新仓库
2. 将本项目的所有文件上传到仓库

### 2. 触发自动打包

有三种方式可以触发自动打包：

#### 方式一：手动触发（最简单）

1. 进入你的 GitHub 仓库
2. 点击顶部的 **Actions** 标签
3. 在左侧选择 **Build EXE** 工作流
4. 点击右侧的 **Run workflow** 按钮
5. 选择分支（通常是 main 或 master）
6. 点击绿色的 **Run workflow** 按钮

#### 方式二：推送代码

```bash
git add .
git commit -m "feat: 添加新功能"
git push
```

每次推送到 main/master 分支都会自动触发打包。

#### 方式三：发布版本

创建并推送一个带版本号的 tag：

```bash
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

这会自动创建一个 Release 并附加打包好的文件。

## 📥 下载打包好的文件

### 从 Actions 下载

1. 进入仓库的 **Actions** 页面
2. 点击一个成功的工作流（绿色勾）
3. 在页面底部找到 **Artifacts** 部分
4. 你会看到三个下载选项：
   - `IPv6RemoteDesktop-Server` - 单独的服务端
   - `IPv6RemoteDesktop-Client` - 单独的客户端
   - `IPv6RemoteDesktop-All` - 两个都包含

### 从 Releases 下载（如果使用了版本发布）

1. 进入仓库的主页
2. 点击右侧的 **Releases**
3. 在最新的 Release 中找到下载链接

## ⚙️ 工作流说明

### build.yml - 普通打包工作流

**触发条件：**
- 推送到 main/master 分支
- 创建 Pull Request
- 创建 Release
- 手动触发

**功能：**
- 在 Windows 环境中打包
- 生成三个 Artifacts 供下载

### release.yml - 版本发布工作流

**触发条件：**
- 推送 `v*` 格式的 tag（如 v1.0.0, v2.1.3）

**功能：**
- 自动打包
- 创建 ZIP 压缩包
- 自动创建 GitHub Release
- 自动生成 Release Notes

## 📊 工作流执行过程

当触发工作流后，GitHub Actions 会：

1. 🧹 准备 Windows 环境
2. 📥 检出你的代码
3. 🐍 设置 Python 3.11
4. 📦 安装所有依赖
5. 🔨 打包服务端
6. 🔨 打包客户端
7. 📤 上传 Artifacts
8. ✅ 完成！

整个过程大约需要 5-15 分钟。

## 🔧 自定义配置

### 修改 Python 版本

编辑 `.github/workflows/build.yml`：

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.10'  # 修改这里
```

### 修改打包配置

编辑 `server.spec` 或 `client.spec` 文件来自定义打包行为。

## 🐛 故障排除

### 工作流失败了怎么办？

1. 进入 Actions 页面
2. 点击失败的工作流
3. 查看详细的错误日志
4. 根据错误信息修复问题

### 常见问题

**问题：依赖安装失败**
- 检查 requirements.txt 文件是否正确
- 尝试升级 pip 版本

**问题：打包时间过长**
- 这是正常的，PyInstaller 打包需要时间
- 通常 5-15 分钟都是正常的

**问题：下载的文件无法运行**
- 确保下载的是 Windows exe
- 检查是否被杀毒软件拦截
- 尝试以管理员身份运行

## 💡 最佳实践

1. **使用手动触发测试**：先手动触发一次，确认配置正确
2. **使用版本标签发布**：准备发布时使用 v1.0.0 这样的标签
3. **查看构建日志**：每次构建都可以查看详细日志
4. **定期更新依赖**：保持 requirements.txt 的依赖是最新的

## 📝 注意事项

- GitHub Actions 免费额度有限制（对个人用户足够用）
- Artifacts 只能保留 90 天（Releases 中的文件永久保留）
- 建议使用正式发布时用 tag 方式，这样文件会永久保存在 Releases 中

## 🎉 开始使用

现在你可以：
1. 把代码推送到 GitHub
2. 手动触发一次工作流（Actions → Build EXE → Run workflow）
3. 几分钟后下载打包好的 exe 文件！

有问题？查看 Actions 的日志输出或提交 Issue。
