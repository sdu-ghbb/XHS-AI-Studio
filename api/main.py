"""
TuLun AI Studio — FastAPI 应用入口
========================================
与 Streamlit 版本 (app.py) 并行运行。
两者共享同一套 agents/tools/knowledge_base 模块。

启动:
    uvicorn api.main:app --reload --port 8000

与 Streamlit 关系:
    - Streamlit (app.py) 可继续独立使用
    - FastAPI (api/main.py) 提供 REST + SSE 端点供 HTML 前端调用
    - 两者互不干扰，共享代码
========================================
"""

import asyncio
import os as _os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import config
from api.deps import set_task_manager_loop
from api.routes import router

# 静态文件路径
_STATIC_DIR = _os.path.join(_os.path.dirname(__file__), "static")
_OUTPUTS_DIR = _os.path.join(_os.path.dirname(__file__), "..", "outputs")
_os.makedirs(_STATIC_DIR, exist_ok=True)
_os.makedirs(_OUTPUTS_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理"""
    # 启动
    print("=" * 50)
    print("🌸 TuLun AI Studio API 启动中...")
    print("=" * 50)

    # 清理旧海报图片
    import glob as _glob
    for _f in _glob.glob(_os.path.join(_OUTPUTS_DIR, "poster_*.jpg")):
        try: _os.remove(_f)
        except Exception: pass

    # 注入事件循环到 TaskManager
    loop = asyncio.get_event_loop()
    set_task_manager_loop(loop)

    # 验证配置
    missing = config.validate()
    if missing:
        print(f"[API] ⚠️ 缺少 API Key: {', '.join(missing)}")
        print("[API] 部分功能可能不可用，请配置 .env 文件")
    else:
        print("[API] ✅ 所有 API Key 已加载")

    # 预加载影子题库
    from knowledge_base import get_kb
    kb = get_kb()
    if kb.is_ready():
        print(f"[API] ✅ 影子题库已加载: {len(kb.notes)} 篇, 模式: {kb.mode}")
    else:
        print("[API] ⚠️ 影子题库未构建，风格 RAG 将不可用")

    print(f"[API] ✅ 服务就绪: http://{config.api_host}:{config.api_port}")
    print(f"[API] 📚 API 文档: http://{config.api_host}:{config.api_port}/docs")
    print()

    yield

    # 关闭
    print("[API] 服务关闭")


app = FastAPI(
    title="小红书 AI Studio API",
    description="多 Agent 协作 · RAG 风格学习 · 小红书图文生成",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS — 允许 HTML 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(router)

# 挂载静态文件（HTML 前端 + 海报图片）
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=_OUTPUTS_DIR), name="outputs")


# =========================================================
#  根路径 → HTML 前端
# =========================================================

@app.get("/")
async def root():
    return FileResponse(_os.path.join(_STATIC_DIR, "index.html"))
