# MCP Music Server

为 LLM 大模型提供音乐播放能力的 MCP (Model Context Protocol) Server。支持网易云音乐、QQ 音乐、酷狗音乐在线搜索与播放，以及本地音乐文件离线播放。

## 功能

- 跨平台音乐搜索（网易云 / QQ / 酷狗 / 本地文件）
- 歌词获取、歌单浏览、热门推荐
- 多音质播放链接获取（low / standard / high / lossless）
- 本地音频文件播放（MP3、FLAC、M4A、WAV、OGG 等）
- 播放控制（播放 / 暂停 / 恢复 / 停止）
- 两种传输模式：`stdio`（本地）和 `sse`（远程 HTTP）
- QQ 音乐扫码登录，凭证自动续期

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/<your-username>/mcp-music-server.git
cd mcp-music-server
```

### 2. 配置 GitHub Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加以下 Secrets：

| Secret | 示例值 | 说明 |
|--------|--------|------|
| `HARBOR_REGISTRY` | `harbor.example.com` | Harbor 仓库地址 |
| `HARBOR_PROJECT` | `mcp-server` | Harbor 项目名称 |
| `HARBOR_USERNAME` | `admin` 或 `robot$mcp-builder` | Harbor 用户名 |
| `HARBOR_PASSWORD` | `your-password-or-token` | Harbor 密码或访问令牌 |

### 3. 发布版本

```bash
# 打 tag 并推送，自动触发构建和发布
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions 将自动：
- 构建 linux/amd64 和 linux/arm64 多架构镜像
- 推送镜像到你的 Harbor 仓库
- 创建 GitHub Release，附带运行包和离线镜像

## 部署

### 离线部署（无网络环境）

```bash
# 1. 下载 Release 中的文件：
#    - mcp-music-server_vX.X.X/           (运行包)
#    - mcp-music-server_vX.X.X_linux-amd64.tar.gz  (镜像，按架构选择)
#    - mcp-music-server_vX.X.X_linux-arm64.tar.gz

# 2. 加载镜像
docker load -i mcp-music-server_v0.1.0_linux-amd64.tar.gz

# 3. 进入运行包目录
cd mcp-music-server_v0.1.0

# 4. QQ 音乐扫码登录（只需一次，在你装有 Python 的电脑上执行）
pip install qqmusic-api-python
python qqmusic_login.py
# 生成凭证文件 → ~/.config/mcp-music-server/qqmusic_credential.json

# 5. 如果服务器不是同一台机器，拷贝凭证到服务器：
scp ~/.config/mcp-music-server/qqmusic_credential.json user@server:~/.config/mcp-music-server/

# 6. 取消 docker-compose.yaml 中凭证挂载行的注释：
#    - ~/.config/mcp-music-server/qqmusic_credential.json:/app/config/qqmusic_credential.json:ro
#    并在 .env 中取消注释：
#    MCP_QQMUSIC_CREDENTIAL_PATH=/app/config/qqmusic_credential.json

# 7. 启动
docker compose up -d
```

### 在线部署（从 Harbor 拉取）

```bash
# 下载运行包
wget https://github.com/<your-username>/mcp-music-server/releases/download/v0.1.0/mcp-music-server_v0.1.0.tar.gz
tar xzf mcp-music-server_v0.1.0.tar.gz
cd mcp-music-server_v0.1.0

# 编辑 .env，设置 Harbor 镜像地址
# MCP_IMAGE=harbor.example.com/mcp-server/mcp-music-server:v0.1.0

docker login harbor.example.com
docker compose up -d
```

### 本地开发运行

```bash
# 安装依赖
pip install -e ".[sse]"

# 配置环境变量
cp .env.example .env
vim .env

# QQ 音乐扫码登录（可选，不使用则通过 Cookie 认证）
python scripts/qqmusic_login.py

# stdio 模式（本地 MCP 客户端）
MCP_TRANSPORT=stdio python -m mcp_music_server.server

# SSE 模式（远程 MCP 客户端）
MCP_TRANSPORT=sse python -m mcp_music_server.server
```

## QQ 音乐认证

项目支持两种 QQ 音乐认证方式：

| 方式 | 配置 | 有效期 | 说明 |
|------|------|--------|------|
| 扫码登录 | `MCP_QQMUSIC_CREDENTIAL_PATH` | 自动续期 | 推荐，首次扫码后无需再管 |
| Cookie 手动填写 | `MCP_QQMUSIC_COOKIE` | 数小时~数天 | 从浏览器 DevTools 复制 |

扫码登录步骤：

```bash
pip install qqmusic-api-python
python scripts/qqmusic_login.py
# 终端会保存二维码图片，用手机 QQ 扫码并确认登录
# 凭证自动保存到 ~/.config/mcp-music-server/qqmusic_credential.json
```

服务器启动时会自动检查凭证是否过期，过期自动刷新。Cookie 方式的优先级低于凭证文件。

## MCP 客户端配置

部署成功后，在任意支持 MCP 的客户端中添加配置：

```json
{
  "mcpServers": {
    "music": {
      "url": "http://<your-server-ip>:8090/sse"
    }
  }
}
```

对于本地 stdio 模式：

```json
{
  "mcpServers": {
    "music": {
      "command": "python",
      "args": ["-m", "mcp_music_server.server"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "MCP_MUSIC_DIR": "/path/to/your/music"
      }
    }
  }
}
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MCP_IMAGE` | `harbor.example.com/mcp-server/mcp-music-server:latest` | Docker 镜像地址 |
| `MCP_TRANSPORT` | `sse` | 传输模式：`stdio` 或 `sse` |
| `MCP_HOST` | `0.0.0.0` | SSE 模式监听地址 |
| `MCP_PORT` | `8090` | SSE 模式监听端口 |
| `MCP_MUSIC_DIR` | `~/Music` | 本地音乐文件目录 |
| `MCP_ENABLED_PLATFORMS` | `netease,qqmusic,kugou,local` | 启用的音乐平台 |
| `MCP_NETEASE_COOKIE` | (空) | 网易云音乐 Cookie |
| `MCP_QQMUSIC_COOKIE` | (空) | QQ 音乐 Cookie（备选方案） |
| `MCP_QQMUSIC_CREDENTIAL_PATH` | `~/.config/mcp-music-server/qqmusic_credential.json` | QQ 音乐扫码凭证路径 |
| `MCP_KUGOU_COOKIE` | (空) | 酷狗音乐 Cookie |
| `MCP_VERSION` | `latest` | 版本标签 |

## MCP 工具列表

| 工具 | 说明 |
|------|------|
| `music_search` | 跨平台搜索歌曲，支持按平台筛选 |
| `music_get_song` | 获取歌曲详情（封面、时长、歌手等） |
| `music_get_play_url` | 获取可播放音频 URL，支持四档音质 |
| `music_get_lyrics` | 获取歌词（含翻译） |
| `music_get_playlist` | 获取歌单详情及歌曲列表 |
| `music_get_hot_playlists` | 获取热门歌单 |
| `music_play` | 播放指定歌曲 |
| `music_stop` | 停止播放 |
| `music_pause` | 暂停播放 |
| `music_resume` | 恢复播放 |
| `music_get_playback_state` | 查询播放状态 |
| `music_get_platform_status` | 检查各平台可用性 |

### 工具调用示例

```
搜索歌曲：music_search(keyword="晴天", platform="all", limit=10)
获取歌词：music_get_lyrics(song_id="186016", platform="netease")
播放链接：music_get_play_url(song_id="97773", platform="qqmusic", quality="high")
```

## 项目结构

```
mcp-music-server/
├── src/mcp_music_server/
│   ├── server.py                # MCP 服务器入口
│   ├── platforms/
│   │   ├── base.py              # 平台抽象层
│   │   ├── netease.py           # 网易云音乐
│   │   ├── qqmusic.py           # QQ 音乐
│   │   ├── kugou.py             # 酷狗音乐
│   │   └── local.py             # 本地文件播放
│   └── utils/
│       ├── audio.py             # 音频播放控制
│       └── qqmusic_auth.py      # QQ 音乐凭证管理
├── scripts/
│   └── qqmusic_login.py         # QQ 音乐扫码登录
├── Dockerfile
├── docker-compose.yaml
├── .github/workflows/
│   └── build-release.yaml       # CI/CD 工作流
└── .env.example
```

## License

MIT
