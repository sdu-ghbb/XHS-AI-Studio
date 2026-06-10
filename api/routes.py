"""
TuLun AI Studio — FastAPI 路由
"""

import json
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from config import Config
from knowledge_base import ShadowKnowledgeBase
from orchestrator import TaskManager
from api.schemas import (
    GenerateRequest, GenerateResponse, TaskStatusResponse,
    ConfigResponse,
    StyleSearchRequest, StyleSearchResponse, StyleSearchResult,
    HeadlineRequest, HeadlineResponse,
    HealthResponse, LogEntry,
)
from api.deps import get_task_manager, get_kb_instance, get_config

router = APIRouter(prefix="/api/v1")


# =========================================================
#  健康检查
# =========================================================

@router.get("/health", response_model=HealthResponse)
async def health(
    kb: ShadowKnowledgeBase = Depends(get_kb_instance),
    cfg: Config = Depends(get_config),
):
    return HealthResponse(
        status="ok",
        kb_ready=kb.is_ready(),
        kb_mode=kb.mode,
        kb_count=len(kb.notes),
        config_valid=len(cfg.validate()) == 0,
    )


# =========================================================
#  标题候选生成
# =========================================================

@router.post("/headlines", response_model=HeadlineResponse)
async def generate_headlines_route(
    req: HeadlineRequest,
):
    """生成 3 个标题候选"""
    import asyncio
    from agents import generate_headlines

    try:
        headlines = await asyncio.to_thread(generate_headlines, topic=req.topic)
        return HeadlineResponse(headlines=headlines)
    except Exception as e:
        return HeadlineResponse(headlines=[], error=str(e))


# =========================================================
#  生成任务
# =========================================================

@router.post("/generate", response_model=GenerateResponse)
async def create_generation(
    req: GenerateRequest,
    tm: TaskManager = Depends(get_task_manager),
):
    if not req.brief.strip():
        raise HTTPException(status_code=400, detail="选题简报不能为空")

    task_id = tm.start(
        brief=req.brief,
        enable_carousel=req.enable_carousel,
        enable_retry=req.enable_retry,
    )
    return GenerateResponse(task_id=task_id)


@router.get("/generate/stream/{task_id}")
async def stream_generation(
    task_id: str,
    tm: TaskManager = Depends(get_task_manager),
):
    """SSE 流式输出"""
    info = tm.get_info(task_id)
    if not info:
        raise HTTPException(status_code=404, detail="任务不存在")

    return EventSourceResponse(tm.subscribe(task_id))


@router.get("/generate/result/{task_id}", response_model=TaskStatusResponse)
async def get_generation_result(
    task_id: str,
    tm: TaskManager = Depends(get_task_manager),
):
    info = tm.get_info(task_id)
    if not info:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskStatusResponse(
        task_id=task_id,
        status=info.status,
        progress=info.progress,
        logs=[LogEntry(type=l.get("type",""), content=l.get("content",""), ts=l.get("ts",""))
              for l in info.logs[-50:]],
        result=info.result,
        final_score=info.final_score,
        error=info.error,
        poster_paths=(info.result or {}).get("poster_paths", []),
    )


# =========================================================
#  配置查询
# =========================================================

@router.get("/config", response_model=ConfigResponse)
async def get_config_info(
    cfg: Config = Depends(get_config),
    kb: ShadowKnowledgeBase = Depends(get_kb_instance),
):
    return ConfigResponse(
        styles=[], templates=[],
        routing=cfg.routing_summary(),
        health={
            "kb_ready": kb.is_ready(),
            "kb_count": len(kb.notes),
            "config_valid": len(cfg.validate()) == 0,
        },
    )


# =========================================================
#  风格 RAG 搜索
# =========================================================

@router.post("/style/search", response_model=StyleSearchResponse)
async def style_search(
    req: StyleSearchRequest,
    kb: ShadowKnowledgeBase = Depends(get_kb_instance),
):
    """搜索与选题相关的爆款范文（给前端直接使用）"""
    if not kb.is_ready():
        return StyleSearchResponse(results=[], mode=kb.mode)

    results = kb.search_style(query=req.query, top_k=5)
    return StyleSearchResponse(
        results=[
            StyleSearchResult(
                title=r.get("title", ""),
                content=r.get("content", "")[:500],
                likes=r.get("likes", 0),
                tags=r.get("tags", []),
            )
            for r in results
        ],
        mode=kb.mode,
    )
