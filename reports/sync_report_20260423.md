# RAG 向量同步报告

**时间**: 2026-04-23T03:05:42.155510

## 项目统计

| 项目名称 | SQLite向量 | Qdrant向量 | 缺失 | 孤儿 | 状态 |
|----------|------------|------------|------|------|------|
| GPT-SoVITS | 393 | 393 | 0 | 0 | ✅ |
| agents-platform | 76 | 76 | 0 | 0 | ✅ |
| claude-code-leaked-mirror | 0 | 0 | 0 | 0 | ✅ |
| claude-leaked-files | 0 | 0 | 0 | 0 | ✅ |
| claw-code | 0 | 0 | 0 | 0 | ✅ |
| content-pipeline | 149 | 149 | 0 | 0 | ✅ |
| destiny-quant | 672 | 672 | 0 | 0 | ✅ |
| ecommerce-platform | 86 | 86 | 0 | 0 | ✅ |
| guitar-circle-of-fifths | 0 | 0 | 0 | 0 | ✅ |
| investor-deck | 1 | 1 | 0 | 0 | ✅ |
| investor-deck-pptxgenjs | 6 | 6 | 0 | 0 | ✅ |
| openclaw | 501 | 501 | 0 | 0 | ✅ |
| openviking | 1442 | 1442 | 0 | 0 | ✅ |
| rag-knowledge-base | 3 | 3 | 0 | 0 | ✅ |
| yunxi | 13909 | 13909 | 0 | 0 | ✅ |
| yunxi-demo | 17 | 17 | 0 | 0 | ✅ |
| 易学资料 | 4921 | 4411 | 510 | 0 | ⚠️ |

## 执行结果

- 检查项目数: 17
- 缺失向量: 510
- 已同步: 510
- 孤儿向量: 0
- 已清理: 0
- 失败重试: 0

## 下一步操作

- [ ] 检查失败向量详情: `python scripts/retry_failed_vectors.py --list`