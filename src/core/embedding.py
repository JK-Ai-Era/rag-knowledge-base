"""Embedding 服务"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.rag_api.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# 全局线程池，用于异步执行同步操作
_executor: Optional[ThreadPoolExecutor] = None


def _get_executor() -> ThreadPoolExecutor:
    """获取全局线程池"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="embedding-")
    return _executor


class EmbeddingService:
    """Embedding 服务 - 使用 Ollama
    
    提供同步和异步两种调用方式：
    - embed_text() / embed_batch(): 异步方法，不阻塞事件循环
    - embed_text_sync(): 同步方法，用于同步上下文
    """
    
    def __init__(self):
        self.host = settings.OLLAMA_HOST
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.embed_dim = settings.OLLAMA_EMBED_DIM
        self._async_client: Optional[httpx.AsyncClient] = None
        self._sync_client: Optional[httpx.Client] = None
    
    @property
    def async_client(self) -> httpx.AsyncClient:
        """懒加载异步客户端"""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client
    
    @property
    def sync_client(self) -> httpx.Client:
        """懒加载同步客户端"""
        if self._sync_client is None:
            self._sync_client = httpx.Client(timeout=self.timeout)
        return self._sync_client
    
    async def embed_text(self, text: str) -> List[float]:
        """对单个文本进行向量化（异步）
        
        使用异步HTTP请求，不阻塞事件循环。
        """
        if not text or not text.strip():
            return [0.0] * self.embed_dim
        
        # 截断过长文本
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars]
        
        try:
            response = await self.async_client.post(
                f"{self.host}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text,
                },
            )
            response.raise_for_status()
            
            data = response.json()
            embedding = data.get("embedding", [])
            
            if not embedding:
                logger.warning("Ollama 返回空向量")
                return [0.0] * self.embed_dim
            
            return embedding
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Embedding HTTP 错误: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Embedding 请求错误: {e}")
            raise
        except Exception as e:
            logger.error(f"Embedding 失败: {e}")
            raise
    
    def embed_text_sync(self, text: str) -> List[float]:
        """对单个文本进行向量化（同步）
        
        用于同步上下文，如 Watcher 事件处理。
        """
        if not text or not text.strip():
            return [0.0] * self.embed_dim
        
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars]
        
        try:
            response = self.sync_client.post(
                f"{self.host}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text,
                },
            )
            response.raise_for_status()
            
            data = response.json()
            embedding = data.get("embedding", [])
            
            if not embedding:
                logger.warning("Ollama 返回空向量")
                return [0.0] * self.embed_dim
            
            return embedding
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Embedding HTTP 错误: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Embedding 请求错误: {e}")
            raise
        except Exception as e:
            logger.error(f"Embedding 失败: {e}")
            raise
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def embed_batch(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """批量向量化（异步）
        
        使用并发HTTP请求提高效率，每个批次内并行处理。
        添加重试机制，最多重试3次。
        
        Args:
            texts: 待向量化的文本列表
            batch_size: 每批次处理的数量，默认10
            
        Returns:
            向量列表，失败的文本返回零向量
        """
        if not texts:
            return []
        
        results = [None] * len(texts)  # 预分配结果列表
        failed_indices = []  # 记录失败的索引
        
        for i in range(0, len(texts), batch_size):
            batch_indices = list(range(i, min(i + batch_size, len(texts))))
            batch_texts = [texts[j] for j in batch_indices]
            
            # 并发处理批次内的文本
            tasks = [self.embed_text(text) for text in batch_texts]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for idx, result in zip(batch_indices, batch_results):
                if isinstance(result, Exception):
                    logger.warning(f"Embedding 失败 (索引 {idx}): {result}")
                    failed_indices.append(idx)
                    results[idx] = [0.0] * self.embed_dim
                else:
                    results[idx] = result
        
        if failed_indices:
            logger.warning(f"批量向量化完成，{len(failed_indices)}/{len(texts)} 个失败")
        
        return results
    
    async def embed_batch_sync_fallback(self, texts: List[str]) -> List[List[float]]:
        """批量向量化（使用线程池执行同步方法）
        
        当异步方法有问题时的备选方案。
        """
        loop = asyncio.get_event_loop()
        executor = _get_executor()
        
        results = []
        for text in texts:
            try:
                result = await loop.run_in_executor(executor, self.embed_text_sync, text)
                results.append(result)
            except Exception as e:
                logger.error(f"Embedding 失败: {e}")
                results.append([0.0] * self.embed_dim)
        
        return results
    
    async def health_check(self) -> bool:
        """检查 Ollama 服务健康状态"""
        try:
            response = await self.async_client.get(f"{self.host}/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama 健康检查失败: {e}")
            return False
    
    async def list_models(self) -> List[str]:
        """列出可用的模型"""
        try:
            response = await self.async_client.get(f"{self.host}/api/tags")
            data = response.json()
            models = data.get("models", [])
            return [m.get("name", "") for m in models]
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return []
    
    async def close(self):
        """关闭连接"""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
    
    def __del__(self):
        """析构时关闭连接"""
        # 注意：在异步环境中，__del__ 可能不会被正确调用
        # 建议显式调用 close()
        if self._sync_client:
            try:
                self._sync_client.close()
            except:
                pass