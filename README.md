# 本地知识库 RAG 系统

基于本地部署的知识库检索系统，支持多项目管理，完全离线运行。

## 特性

- 🔒 **完全本地部署** - 数据不出境，隐私安全
- 📁 **多项目管理** - 项目间数据严格隔离
- 📄 **多格式支持** - PDF、Word、Markdown、代码文件
- 🔍 **混合检索** - 语义搜索 + 关键词搜索
- 🌐 **Web UI** - 现代化网页界面，支持拖拽上传
- 🤖 **Claude Code 集成** - MCP Server 支持
- 🚀 **Apple Silicon 优化** - MPS 加速支持

## 快速开始

### 一键启动

```bash
cd ~/Projects/rag-knowledge-base
./scripts/start-all.sh
```

访问 http://localhost:8000/docs 查看 API 文档。

### 手动启动

```bash
# 1. 进入项目
cd ~/Projects/rag-knowledge-base
source .venv/bin/activate

# 2. 启动 Qdrant (如未运行)
./scripts/start-qdrant.sh

# 3. 确保 Ollama 运行
ollama serve

# 4. 启动 API 服务
uvicorn src.rag_api.main:app --reload
```

### CLI 使用

```bash
# 创建项目
rag project-create "项目名称"

# 列出项目
rag project-list

# 上传文档
rag ingest "项目ID" ./docs/

# 搜索
rag search "项目ID" "查询内容"
```

## 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Embedding | Ollama + bge-m3 | 中文语义理解优秀 |
| 向量数据库 | Qdrant | 高性能，支持过滤 |
| 文档解析 | pypdf / MinerU | PDF 解析 |
| API 框架 | FastAPI | 异步高性能 |
| Web UI | Next.js + shadcn/ui | 现代化 React 界面 |
| 元数据 | SQLite | 零配置 |

## 项目结构

```
rag-knowledge-base/
├── src/
│   ├── rag_api/          # FastAPI 服务
│   ├── core/             # 核心逻辑
│   ├── services/         # 业务服务
│   ├── mcp/              # MCP Server
│   └── cli/              # CLI 工具
├── web/                  # Web UI (Next.js)
│   └── my-app/
│       ├── app/          # 页面路由
│       ├── components/   # UI 组件
│       └── lib/          # API 客户端
├── scripts/              # 运维脚本
│   ├── setup.sh          # 初始化
│   ├── start-all.sh      # 一键启动
│   ├── start-web.sh      # 启动 Web UI
│   ├── start-qdrant.sh   # 启动 Qdrant
│   └── service.sh        # 服务管理
├── docs/                 # 文档
├── data/                 # 数据目录
└── db/                   # SQLite 数据库
```

## 测试

```bash
# 运行功能测试
python scripts/test_system.py
```

## 常见问题

### 什么是"片段"?

**片段（Chunk）** 是文档被拆分后的小块文本。RAG系统会将上传的文档：

1. **解析** - 提取文档中的文本内容
2. **切分** - 将长文本切分成适当大小的片段（通常几百个字符）
3. **向量化** - 将每个片段转换为向量（Embedding）
4. **存储** - 存入向量数据库用于语义搜索

例如，一个100页的PDF会被切分成数百个片段，搜索时系统会找到最相关的片段返回。

### 为什么项目显示0片段？

如果项目显示0片段，可能是：
- 文档还在处理中（状态为"处理中"）
- 文档解析失败（状态为"失败"）
- 文档内容为空或无法提取文本

### 如何查看文档处理状态？

进入项目 → 文档列表，查看每个文档的"状态"列：
- **已完成** - 文档已解析并创建片段
- **处理中** - 正在解析文档
- **失败** - 解析失败，可能是格式不支持或文件损坏

## 文档

- [API 文档](docs/API.md) - RESTful API 参考
- [MCP 配置](docs/MCP_SETUP.md) - Claude Code 集成
- [自动启动配置](AUTOSTART.md) - 开机自启动设置

## 系统要求

- macOS 14.0+ (Apple Silicon 优化)
- Python 3.10+ (当前环境 3.14.3)
- 16GB 内存
- Docker (可选，用于 Qdrant)

## 部署状态

详见 [DEPLOY_STATUS.md](DEPLOY_STATUS.md)

## License

MIT
