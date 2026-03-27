"""项目路由"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.rag_api.models.database import get_db
from src.rag_api.models.schemas import (
    APIResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from src.services.project_service import ProjectService

router = APIRouter()


@router.post("", response_model=APIResponse)
async def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
):
    """创建项目"""
    service = ProjectService(db)
    try:
        result = service.create_project(project)
        return APIResponse(success=True, data=result, message="项目创建成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建项目失败: {str(e)}")


@router.get("", response_model=APIResponse)
async def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """列出所有项目"""
    service = ProjectService(db)
    projects = service.list_projects(skip=skip, limit=limit)
    return APIResponse(success=True, data=projects)


@router.get("/{project_id}", response_model=APIResponse)
async def get_project(
    project_id: str,
    db: Session = Depends(get_db),
):
    """获取项目详情"""
    service = ProjectService(db)
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return APIResponse(success=True, data=project)


@router.put("/{project_id}", response_model=APIResponse)
async def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    db: Session = Depends(get_db),
):
    """更新项目"""
    service = ProjectService(db)
    try:
        result = service.update_project(project_id, project_update)
        return APIResponse(success=True, data=result, message="项目更新成功")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新项目失败: {str(e)}")


@router.delete("/{project_id}", response_model=APIResponse)
async def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
):
    """删除项目（连同所有数据）"""
    service = ProjectService(db)
    try:
        service.delete_project(project_id)
        return APIResponse(success=True, message="项目删除成功")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除项目失败: {str(e)}")
