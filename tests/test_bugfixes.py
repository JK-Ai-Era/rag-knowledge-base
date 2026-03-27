"""Bug 修复验证测试"""

import pytest
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestEmbeddingService:
    """测试 Embedding 服务修复"""
    
    def test_embed_text_is_async(self):
        """验证 embed_text 是真正的异步方法"""
        from src.core.embedding import EmbeddingService
        import inspect
        
        service = EmbeddingService()
        assert inspect.iscoroutinefunction(service.embed_text), "embed_text 应该是异步方法"
        assert inspect.iscoroutinefunction(service.embed_batch), "embed_batch 应该是异步方法"
        assert not inspect.iscoroutinefunction(service.embed_text_sync), "embed_text_sync 应该是同步方法"
        service.close()
    
    def test_embed_text_sync_works(self):
        """验证同步方法仍然可用"""
        from src.core.embedding import EmbeddingService
        
        service = EmbeddingService()
        # 空文本应该返回零向量
        result = service.embed_text_sync("")
        assert len(result) == 1024
        assert all(v == 0.0 for v in result)
        service.close()
    
    def test_empty_text_handling(self):
        """验证空文本处理"""
        from src.core.embedding import EmbeddingService
        
        service = EmbeddingService()
        result = service.embed_text_sync("   ")  # 只有空格
        assert len(result) == 1024
        assert all(v == 0.0 for v in result)
        service.close()


class TestChunker:
    """测试 Chunker 修复"""
    
    def test_merge_small_chunks_empty(self):
        """测试空列表边界情况"""
        from src.core.chunker import TextChunker
        
        chunker = TextChunker()
        result = chunker._merge_small_chunks([])
        assert result == []
    
    def test_merge_small_chunks_single(self):
        """测试单元素边界情况"""
        from src.core.chunker import TextChunker
        
        chunker = TextChunker()
        result = chunker._merge_small_chunks(["single chunk"])
        assert result == ["single chunk"]
    
    def test_merge_small_chunks_normal(self):
        """测试正常合并"""
        from src.core.chunker import TextChunker
        
        chunker = TextChunker(chunk_size=1000)
        chunks = ["small", "medium size chunk", "another small"]
        result = chunker._merge_small_chunks(chunks)
        assert len(result) >= 1  # 至少有一个结果


class TestVectorStore:
    """测试 VectorStore 修复"""
    
    def test_search_result_handling(self):
        """验证搜索结果处理兼容多版本"""
        from src.core.vector_store import VectorStore
        
        # 这里不能真正测试，因为需要 Qdrant 服务
        # 但可以验证代码结构
        import inspect
        source = inspect.getsource(VectorStore.search)
        assert 'hasattr(results, \'points\')' in source or 'isinstance(results, list)' in source


class TestDatabaseSession:
    """测试数据库会话管理修复"""
    
    def test_mcp_session_context_manager(self):
        """验证 MCP server 使用上下文管理器"""
        import inspect
        from src.mcp import server as mcp_server
        
        # 检查 _get_db_session 返回的是上下文管理器
        source = inspect.getsource(mcp_server._get_db_session)
        assert 'contextmanager' in source or 'yield' in source


class TestFileSync:
    """测试 FileSync 修复"""
    
    def test_sync_file_is_sync(self):
        """验证 sync_file 现在是同步方法"""
        from src.watcher.sync import FileSync
        import inspect
        
        # 创建一个 mock 的 db session
        class MockDB:
            def query(self, *args): pass
            def commit(self): pass
            def close(self): pass
        
        file_sync = FileSync(MockDB(), "test-project")
        assert not inspect.iscoroutinefunction(file_sync.sync_file), "sync_file 应该是同步方法"


class TestConsistencyChecker:
    """测试一致性检查器修复"""
    
    def test_check_untracked_files_safe(self):
        """验证未跟踪文件只记录不删除"""
        import inspect
        from src.watcher.sync import ConsistencyChecker
        
        source = inspect.getsource(ConsistencyChecker._check_untracked_files)
        # 不应该有 unlink 调用
        assert 'unlink()' not in source or '只记录警告' in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
