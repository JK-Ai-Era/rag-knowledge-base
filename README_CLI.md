# RAG CLI 管理工具 - ragctl

本地 RAG 知识库系统的命令行管理工具，提供服务、项目、文档、搜索等管理功能。

## 安装

```bash
cd ~/Projects/rag-knowledge-base
pip install -e .
```

安装后即可使用 `ragctl` 命令。

## 快速开始

```bash
# 查看帮助
ragctl --help

# 查看服务状态
ragctl service status

# 列出所有项目
ragctl project list

# 搜索知识库
ragctl search <project_id> <query>
```

## 命令详解

### 服务管理

```bash
# 查看所有服务状态
ragctl service status

# 启动所有服务
ragctl service start

# 停止所有服务
ragctl service stop

# 重启所有服务
ragctl service restart

# 查看服务日志
ragctl service logs api
ragctl service logs qdrant
ragctl service logs web
```

### 项目管理

```bash
# 列出所有项目
ragctl project list

# 创建项目
ragctl project create my-project --desc "项目描述"

# 查看项目详情
ragctl project info <project_id>

# 重新索引项目
ragctl project reindex <project_id>

# 删除项目
ragctl project delete <project_id> --force
```

### 文档管理

```bash
# 列出项目文档
ragctl doc list <project_id>

# 上传文档
ragctl doc upload <project_id> /path/to/file.pdf

# 上传整个目录
ragctl doc upload <project_id> /path/to/directory --recursive

# 导出文档内容
ragctl doc export <project_id> <doc_id> --output output.txt

# 删除文档
ragctl doc delete <project_id> <doc_id> --force
```

### 搜索

```bash
# 语义搜索 (默认)
ragctl search <project_id> "搜索内容"

# 关键词搜索
ragctl search <project_id> "关键词" --mode keyword

# 混合搜索
ragctl search <project_id> "搜索内容" --mode hybrid

# 指定返回数量
ragctl search <project_id> "搜索内容" --top-k 20

# 设置分数阈值
ragctl search <project_id> "搜索内容" --threshold 0.7
```

### 文件监控

```bash
# 查看监控状态
ragctl watcher status

# 启动监控
ragctl watcher start

# 停止监控
ragctl watcher stop

# 查看同步统计
ragctl watcher stats

# 强制扫描项目
ragctl watcher scan <project_name>

# 重置统计
ragctl watcher reset-stats
```

### 系统信息

```bash
# 健康检查
ragctl health

# 系统统计
ragctl stats

# 系统信息
ragctl system info
```

## 配置文件

配置文件位于 `~/.config/ragctl/config.yaml`:

```yaml
api:
  url: http://localhost:8000
  timeout: 30

services:
  qdrant:
    host: localhost
    port: 6333
  ollama:
    host: localhost
    port: 11434
  web:
    host: localhost
    port: 3000

auth:
  enabled: true
  token_file: ~/.config/ragctl/token

logging:
  level: INFO
```

## 认证

如果 API 启用了认证，需要先登录：

```bash
# 交互式登录
ragctl login

# 或通过环境变量
export RAG_API_USERNAME=admin
export RAG_API_PASSWORD=your-password
```

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| API | 8000 | RAG API 服务 |
| Qdrant | 6333 | 向量数据库 |
| Web UI | 3000 | Web 界面 |
| Ollama | 11434 | LLM 服务 |

## 故障排查

### 无法连接 API

```bash
# 检查服务是否运行
ragctl service status

# 查看 API 日志
ragctl service logs api
```

### 认证失败

```bash
# 删除 Token 文件重新登录
rm ~/.config/ragctl/token
ragctl login
```

### 查看详细日志

```bash
# API 日志
tail -f ~/Projects/rag-knowledge-base/logs/api_latest.log

# Qdrant 日志
tail -f ~/.qdrant/logs/stderr.log
```

## 命令别名

如果习惯使用旧命令，可以创建别名：

```bash
alias rag='ragctl'
```
