"""文档处理服务 - 统一的文档处理入口

提供文档处理的完整流程：
1. 提取文本
2. 分块
3. 向量化
4. 保存到数据库和向量库

被 sync.py (watcher 自动同步) 和 ingest_service.py (API 上传) 共用
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from src.rag_api.config import get_settings
from src.rag_api.models.database import Chunk as ChunkModel
from src.rag_api.models.database import Document as DocumentModel
from src.rag_api.models.database import Project as ProjectModel
from src.core.chunker import TextChunker, ChunkWithMetadata
from src.core.document_processor import DocumentProcessor
from src.core.embedding import EmbeddingService
from src.core.vector_store import VectorStore
from src.core.bm25_index import bm25_manager
from src.core.hierarchical_index import hierarchical_index

settings = get_settings()
logger = logging.getLogger(__name__)


class DocumentProcessingResult:
    """文档处理结果"""
    
    def __init__(
        self,
        success: bool,
        document_id: Optional[str] = None,
        chunk_count: int = 0,
        vector_count: int = 0,
        error_message: Optional[str] = None
    ):
        self.success = success
        self.document_id = document_id
        self.chunk_count = chunk_count
        self.vector_count = vector_count
        self.error_message = error_message
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "document_id": self.document_id,
            "chunk_count": self.chunk_count,
            "vector_count": self.vector_count,
            "error_message": self.error_message,
        }


class DocumentService:
    """文档处理服务
    
    统一的文档处理入口，被多个模块共用：
    - FileSync (sync.py): 文件系统自动同步
    - IngestService (ingest_service.py): API 手动上传
    - Reindex scripts: 重新索引脚本
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.processor = DocumentProcessor()
        self.chunker = TextChunker()
        self.embedding = EmbeddingService()
        self.vector_store = VectorStore()
    
    def process_document(
        self,
        file_path: Path,
        doc_type: str,
        project_id: str,
        document_id: Optional[str] = None,
        filename: Optional[str] = None,
        source_path: Optional[str] = None,  # 原始文件完整路径（用于 Agent read 源文件）
        metadata: Optional[Dict[str, Any]] = None,
        on_progress: Optional[Callable[[str, int, int], None]] = None
    ) -> DocumentProcessingResult:
        """
        处理文档的完整流程
        
        Args:
            file_path: 文件路径（必须是已复制到项目目录的路径）
            doc_type: 文档类型 (pdf/docx/xlsx/pptx/image/md/txt/code)
            project_id: 项目ID
            document_id: 现有文档ID（重新索引时使用），None则创建新文档
            filename: 文件名，None则使用 file_path.name
            metadata: 文档元数据
            on_progress: 进度回调函数，参数: (stage, current, total)
            
        Returns:
            DocumentProcessingResult: 处理结果
        """
        try:
            # 验证文件
            if not file_path.exists():
                return DocumentProcessingResult(
                    success=False,
                    error_message=f"文件不存在: {file_path}"
                )
            
            # 使用文件名
            actual_filename = filename or file_path.name
            
            # 获取或创建文档记录
            if document_id:
                doc = self.db.query(DocumentModel).filter(
                    DocumentModel.id == document_id
                ).first()
                if not doc:
                    return DocumentProcessingResult(
                        success=False,
                        error_message=f"文档不存在: {document_id}"
                    )
                # 更新 source_path（重新索引时）
                if source_path:
                    doc.source_path = source_path
                old_chunk_count = doc.chunk_count
            else:
                doc = self._create_document_record(
                    project_id=project_id,
                    filename=actual_filename,
                    doc_type=doc_type,
                    file_path=str(file_path),
                    source_path=source_path,
                    metadata=metadata
                )
                old_chunk_count = 0
            
            doc_id = doc.id
            
            if on_progress:
                on_progress("extract", 0, 100)
            
            # 1. 提取文本
            logger.info(f"[{doc_id}] 提取文本: {actual_filename}")
            text = self.processor.extract_text(file_path, doc_type)
            
            if on_progress:
                on_progress("chunk", 50, 100)
            
            # 2. 分块
            logger.info(f"[{doc_id}] 分块处理...")
            chunk_objects = self._chunk_text(text, doc_type, str(file_path))
            logger.info(f"[{doc_id}] 生成 {len(chunk_objects)} 个片段")
            
            if on_progress:
                on_progress("vectorize", 75, 100)
            
            # 3. 向量化并保存
            logger.info(f"[{doc_id}] 向量化...")
            vector_result = self._vectorize_and_save_chunks(
                chunks=chunk_objects,
                document_id=doc_id,
                project_id=project_id,
                filename=actual_filename,
                source_path=source_path  # 传递原始文件路径
            )
            
            # 4. 更新文档状态
            doc.status = "completed" if vector_result["success_count"] > 0 else "failed"
            doc.chunk_count = vector_result["success_count"]
            # 使用详细的错误信息
            if vector_result.get("error_details"):
                doc.error_message = vector_result["error_details"]
            elif vector_result["failed_count"] > 0:
                doc.error_message = (
                    f"{vector_result['failed_count']}/{len(chunk_objects)} chunks 向量化失败"
                )
            
            self.db.commit()
            
            # 5. 更新项目统计
            self._update_project_stats(
                project_id=project_id,
                old_chunk_count=old_chunk_count,
                new_chunk_count=vector_result["success_count"],
                is_new_document=(document_id is None)
            )
            
            # 6. 更新 BM25 索引
            self._update_bm25_index(
                project_id=project_id,
                chunks=[(c.id, c.content) for c in self.db.query(ChunkModel).filter(
                    ChunkModel.document_id == doc_id
                ).all()],
                action="add"
            )
            
            # 7. 生成文档摘要（层次化索引）
            if vector_result["success_count"] > 0:
                try:
                    chunk_contents = [c.content for c in chunk_objects]
                    hierarchical_index.index_document_sync(
                        project_id=project_id,
                        document_id=doc_id,
                        chunks=chunk_contents,
                        filename=actual_filename,
                    )
                except Exception as e:
                    logger.warning(f"生成文档摘要失败: {e}")
            
            if on_progress:
                on_progress("complete", 100, 100)
            
            logger.info(
                f"[{doc_id}] 处理完成: {vector_result['success_count']}/"
                f"{len(chunk_objects)} 个向量成功"
            )
            
            return DocumentProcessingResult(
                success=vector_result["success_count"] > 0,
                document_id=doc_id,
                chunk_count=len(chunk_objects),
                vector_count=vector_result["success_count"],
                error_message=doc.error_message if vector_result["failed_count"] > 0 else None
            )
            
        except Exception as e:
            logger.exception(f"处理文档失败: {e}")
            
            # 如果已创建文档记录，标记为失败
            if 'doc' in locals() and doc:
                doc.status = "failed"
                doc.error_message = str(e)
                self.db.commit()
            
            return DocumentProcessingResult(
                success=False,
                document_id=doc.id if 'doc' in locals() and doc else None,
                error_message=str(e)
            )
    
    def _create_document_record(
        self,
        project_id: str,
        filename: str,
        doc_type: str,
        file_path: str,
        source_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentModel:
        """创建文档记录"""
        from uuid import uuid4
        
        file_size = Path(file_path).stat().st_size
        
        doc = DocumentModel(
            id=str(uuid4()),
            project_id=project_id,
            filename=filename,
            doc_type=doc_type,
            file_size=file_size,
            file_path=file_path,
            source_path=source_path,  # 保存原始文件路径
            status="processing",
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        
        logger.info(f"创建文档记录: {doc.id} - {filename}")
        return doc
    
    def _chunk_text(
        self,
        text: str,
        doc_type: str,
        file_path: str
    ) -> List[ChunkWithMetadata]:
        """对文本进行分块"""
        if doc_type == "code":
            language = Path(file_path).suffix.lstrip('.')
            return self.chunker.chunk_code_with_symbols(
                text,
                file_path=file_path,
                language=language
            )
        else:
            return self.chunker.chunk_text_with_location(
                text,
                file_path=file_path
            )
    
    def _vectorize_and_save_chunks(
        self,
        chunks: List[ChunkWithMetadata],
        document_id: str,
        project_id: str,
        filename: str,
        source_path: Optional[str] = None  # 原始文件完整路径
    ) -> Dict[str, int]:
        """
        向量化 chunks 并保存到数据库和向量库
        
        优化：批量获取 embedding，批量添加向量
        
        Args:
            chunks: 分块列表
            document_id: 文档ID
            project_id: 项目ID
            filename: 文件名
            source_path: 原始文件完整路径（用于 Agent read 源文件）
            
        Returns:
            {"success_count": int, "failed_count": int, "error_details": str}
        """
        if not chunks:
            return {"success_count": 0, "failed_count": 0, "error_details": "无分块"}
        
        success_count = 0
        failed_count = 0
        error_details = []
        
        # 1. 首先保存所有 chunks 到数据库（无 vector_id）
        chunk_records = []
        for idx, chunk_obj in enumerate(chunks):
            metadata = {
                "start_line": chunk_obj.start_line,
                "end_line": chunk_obj.end_line,
                "file_path": chunk_obj.metadata.get("file_path"),
            }
            
            # 代码文件额外保存符号信息
            if chunk_obj.metadata.get("symbols"):
                metadata["symbols"] = chunk_obj.metadata["symbols"]
            
            chunk = ChunkModel(
                document_id=document_id,
                project_id=project_id,
                content=chunk_obj.content,
                chunk_index=idx,
                metadata_json=json.dumps(metadata),
            )
            self.db.add(chunk)
            chunk_records.append(chunk)
        
        try:
            self.db.commit()  # 先保存 chunks 获取 ID
        except Exception as e:
            logger.error(f"[{document_id}] 保存分块失败: {e}")
            self.db.rollback()
            return {"success_count": 0, "failed_count": len(chunks), "error_details": f"保存分块失败: {e}"}
        
        # 2. 批量向量化（逐个处理，记录详细错误）
        logger.info(f"[{document_id}] 批量向量化 {len(chunk_records)} 个 chunks...")
        embeddings = []
        vectorization_errors = []
        
        for idx, c in enumerate(chunk_records):
            try:
                emb = self.embedding.embed_text_sync(c.content)
                if not emb or len(emb) == 0:
                    vectorization_errors.append(f"chunk {idx}: 返回空向量")
                    embeddings.append(None)
                elif all(v == 0.0 for v in emb):
                    vectorization_errors.append(f"chunk {idx}: 零向量（可能服务未就绪）")
                    embeddings.append(None)
                else:
                    embeddings.append(emb)
            except Exception as e:
                vectorization_errors.append(f"chunk {idx}: {str(e)[:50]}")
                embeddings.append(None)
        
        # 3. 筛选有效的向量化结果
        payloads = []
        valid_embeddings = []
        valid_chunks = []
        
        for idx, (chunk, embedding) in enumerate(zip(chunk_records, embeddings)):
            if embedding is None:
                failed_count += 1
                continue
            
            try:
                metadata = json.loads(chunk.metadata_json) if chunk.metadata_json else {}
            except:
                metadata = {}
            
            payload = {
                "chunk_id": chunk.id,
                "document_id": document_id,
                "content": chunk.content,
                "filename": filename,
                "source_path": source_path,  # 原始文件完整路径（Agent read 源文件用）
                "start_line": metadata.get("start_line"),
                "end_line": metadata.get("end_line"),
                "symbols": metadata.get("symbols", []),
            }
            payloads.append(payload)
            valid_embeddings.append(embedding)
            valid_chunks.append(chunk)
        
        # 4. 处理向量化结果
        if payloads:
            try:
                vector_ids = self.vector_store.add_vectors_batch(
                    project_id=project_id,
                    vectors=valid_embeddings,
                    payloads=payloads
                )
                
                # 更新 chunk 记录的 vector_id
                for chunk, vector_id in zip(valid_chunks, vector_ids):
                    if vector_id:
                        chunk.vector_id = vector_id
                        success_count += 1
                    else:
                        failed_count += 1
                        # 向量库添加失败，删除该分块
                        self.db.delete(chunk)
                
            except Exception as e:
                logger.error(f"[{document_id}] 添加向量失败: {e}")
                error_details.append(f"向量库添加失败: {str(e)[:50]}")
                # 所有有效分块都失败
                for chunk in valid_chunks:
                    self.db.delete(chunk)
                failed_count += len(valid_chunks)
        else:
            # 没有有效的向量，删除所有 chunks
            logger.warning(f"[{document_id}] 无有效向量，清理所有分块")
            for chunk in chunk_records:
                self.db.delete(chunk)
            failed_count = len(chunk_records)
        
        # 5. 最终 commit（确保删除操作生效）
        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"[{document_id}] 最终 commit 失败: {e}")
            self.db.rollback()
            # 尝试重新删除残留的 chunks
            try:
                remaining_chunks = self.db.query(ChunkModel).filter(
                    ChunkModel.document_id == document_id
                ).all()
                for chunk in remaining_chunks:
                    if chunk.vector_id is None:  # 只删除无向量的
                        self.db.delete(chunk)
                self.db.commit()
            except Exception as e2:
                logger.error(f"[{document_id}] 清理残留分块失败: {e2}")
        
        # 6. 构建详细错误信息
        if vectorization_errors:
            error_details.append(f"向量化失败: {len(vectorization_errors)}/{len(chunks)}")
            if len(vectorization_errors) <= 5:
                error_details.extend(vectorization_errors)
            else:
                error_details.extend(vectorization_errors[:3])
                error_details.append(f"... 共 {len(vectorization_errors)} 个错误")
        
        error_message = "; ".join(error_details) if error_details else None
        
        logger.info(f"[{document_id}] 向量化完成：{success_count} 成功，{failed_count} 失败")
        
        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "error_details": error_message,
        }
    
    def _update_project_stats(
        self,
        project_id: str,
        old_chunk_count: int,
        new_chunk_count: int,
        is_new_document: bool
    ):
        """更新项目统计"""
        project = self.db.query(ProjectModel).filter(
            ProjectModel.id == project_id
        ).first()
        
        if not project:
            logger.warning(f"项目不存在: {project_id}")
            return
        
        if is_new_document:
            # 新文档：增加文档计数
            project.document_count += 1
        else:
            # 重新索引：调整片段计数
            project.chunk_count = max(0, project.chunk_count - old_chunk_count)
        
        # 加上新的片段数
        project.chunk_count += new_chunk_count
        self.db.commit()
        
        logger.debug(
            f"更新项目统计: document_count={project.document_count}, "
            f"chunk_count={project.chunk_count}"
        )
    
    def _update_bm25_index(
        self,
        project_id: str,
        chunks: list,
        action: str = "add"
    ) -> None:
        """更新 BM25 索引
        
        Args:
            project_id: 项目 ID
            chunks: [(chunk_id, content), ...] 列表
            action: 操作类型 (add/remove)
        """
        try:
            bm25_index = bm25_manager.get_index(project_id)
            
            if action == "add":
                for chunk_id, content in chunks:
                    bm25_index.add_document(chunk_id, content)
            elif action == "remove":
                for chunk_id, _ in chunks:
                    bm25_index.remove_document(chunk_id)
            
            # 保存索引
            bm25_index.save()
            
            logger.debug(f"BM25 索引已更新: {action} {len(chunks)} 个文档")
            
        except Exception as e:
            logger.warning(f"更新 BM25 索引失败: {e}")
    
    def delete_document(
        self,
        document_id: str,
        delete_file: bool = True
    ) -> bool:
        """
        删除文档及其所有关联数据
        
        Args:
            document_id: 文档ID
            delete_file: 是否删除物理文件
            
        Returns:
            是否成功删除
        """
        try:
            doc = self.db.query(DocumentModel).filter(
                DocumentModel.id == document_id
            ).first()
            
            if not doc:
                logger.warning(f"文档不存在: {document_id}")
                return False
            
            project_id = doc.project_id
            chunk_count = doc.chunk_count
            
            # 1. 收集所有向量ID
            chunks = self.db.query(ChunkModel).filter(
                ChunkModel.document_id == document_id
            ).all()
            
            vector_ids_to_delete = []
            failed_vector_deletes = []
            
            for chunk in chunks:
                if chunk.vector_id:
                    vector_ids_to_delete.append(chunk.vector_id)
            
            # 2. 批量删除向量，记录失败的
            for vector_id in vector_ids_to_delete:
                try:
                    self.vector_store.delete_vector(project_id, vector_id)
                except Exception as e:
                    logger.error(f"删除向量失败 {vector_id}: {e}")
                    failed_vector_deletes.append(vector_id)
            
            # 3. 如果有向量删除失败，记录但不阻止文档删除
            # 孤立向量可通过一致性检查清理
            if failed_vector_deletes:
                logger.warning(
                    f"文档 {document_id} 有 {len(failed_vector_deletes)} 个向量删除失败，"
                    "可通过一致性检查清理"
                )
            
            # 4. 删除所有chunk记录
            # 先收集 chunk IDs 用于更新 BM25
            chunk_ids_for_bm25 = [chunk.id for chunk in chunks]
            
            for chunk in chunks:
                self.db.delete(chunk)
            
            # 5. 更新 BM25 索引
            if chunk_ids_for_bm25:
                self._update_bm25_index(
                    project_id=project_id,
                    chunks=[(cid, "") for cid in chunk_ids_for_bm25],
                    action="remove"
                )
            
            # 6. 删除物理文件
            if delete_file:
                file_path = Path(doc.file_path)
                if file_path.exists():
                    file_path.unlink()
                    # 清理空目录
                    self._cleanup_empty_dirs(file_path.parent, project_id)
            
            # 7. 删除文档记录
            self.db.delete(doc)
            self.db.commit()
            
            # 8. 更新项目统计
            project = self.db.query(ProjectModel).filter(
                ProjectModel.id == project_id
            ).first()
            if project:
                project.document_count = max(0, project.document_count - 1)
                project.chunk_count = max(0, project.chunk_count - chunk_count)
                self.db.commit()
            
            logger.info(f"已删除文档: {document_id}")
            return True
            
        except Exception as e:
            logger.exception(f"删除文档失败: {e}")
            self.db.rollback()
            return False
    
    def _cleanup_empty_dirs(self, dir_path: Path, project_id: str):
        """递归清理空目录"""
        try:
            project_dir = settings.PROJECTS_DIR / project_id
            if dir_path == project_dir:
                return
            
            if dir_path.exists() and not any(dir_path.iterdir()):
                dir_path.rmdir()
                logger.debug(f"删除空目录: {dir_path}")
                self._cleanup_empty_dirs(dir_path.parent, project_id)
        except OSError:
            pass
