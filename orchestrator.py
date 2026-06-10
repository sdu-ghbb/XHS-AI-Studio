"""
TuLun AI Studio — 异步任务编排器
===========================================
桥接 LangGraph 调用和异步 SSE 推送。
TaskManager 用 threading.Thread 执行业务逻辑，
通过 asyncio.Queue 向 SSE 端点推送实时日志。
LangGraph 替代 CrewAI，实现真正的 streaming 和阶段追踪。
===========================================
"""

import os
import re
import glob
import json
import time
import uuid
import asyncio
import threading
import traceback
from typing import Optional, Dict, Any, AsyncGenerator

from config import config
from agents import run_graph


# =========================================================
#  TaskInfo — 单个任务的状态和事件队列
# =========================================================

class TaskInfo:
    """单个生成任务的全部状态"""
    def __init__(self, task_id: str):
        self.task_id: str = task_id
        self.queue: asyncio.Queue = asyncio.Queue()
        self.status: str = "queued"       # queued | running | done | error
        self.progress: int = 0
        self.logs: list = []
        self.result: Optional[Dict] = None
        self.final_score: Optional[int] = None
        self.error: Optional[str] = None
        self.created_at: float = time.time()


# =========================================================
#  TaskManager — 全局任务管理器（单例）
# =========================================================

class TaskManager:
    """
    任务管理器
    ----------
    职责：
        1. 接收生成请求，分配 task_id
        2. 用后台线程执行 CrewAI 流水线
        3. 通过 asyncio.Queue 向 SSE 端点推送事件
        4. 提供任务结果查询接口

    用法：
        mgr = TaskManager()
        task_id = mgr.start(brief="...")
        async for event in mgr.subscribe(task_id):
            # SSE stream
        result = mgr.get_result(task_id)
    """
    def __init__(self):
        self._tasks: Dict[str, TaskInfo] = {}
        self._lock = threading.Lock()
        # 保存事件循环引用（在 FastAPI lifespan 中设置）
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """在 lifespan 中设置事件循环引用"""
        self._loop = loop

    # ---------- 公共 API ----------

    def start(
        self,
        brief: str,
        enable_carousel: bool = False,
        enable_retry: bool = True,
    ) -> str:
        """
        启动一个新的生成任务
        返回 task_id
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        info = TaskInfo(task_id)
        with self._lock:
            self._tasks[task_id] = info

        thread = threading.Thread(
            target=self._run,
            args=(task_id, brief, enable_carousel, enable_retry),
            daemon=True,
        )
        thread.start()
        return task_id

    def get_info(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        with self._lock:
            return self._tasks.get(task_id)

    def get_result(self, task_id: str) -> Optional[Dict]:
        """获取任务结果（如果已完成）"""
        info = self.get_info(task_id)
        if info and info.status in ("done", "error"):
            return self._serialize_result(info)
        return None

    async def subscribe(self, task_id: str) -> AsyncGenerator[dict, None]:
        """SSE 事件流 —— yield dict，由 sse-starlette 格式化为 event:/data: 行"""
        info = self.get_info(task_id)
        if not info:
            yield {"event": "error", "data": json.dumps({"message": "task not found"}, ensure_ascii=False)}
            return

        info.status = "running"

        while True:
            try:
                event = await asyncio.wait_for(info.queue.get(), timeout=30.0)
                etype = event.get("event", "message")
                # data 字段必须传 JSON 字符串，sse-starlette 直接拼在 data: 后面
                yield {"event": etype, "data": json.dumps(event, ensure_ascii=False)}
                if etype in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                yield {"comment": "heartbeat"}

    # ---------- 内部 ----------

    def _run(
        self,
        task_id: str,
        brief: str,
        enable_carousel: bool,
        enable_retry: bool,
    ):
        """后台线程：执行 CrewAI 流水线"""
        info = self.get_info(task_id)
        if not info:
            return

        max_attempts = 2 if enable_retry else 1

        def _emit(event: str, data: dict):
            """向 SSE 队列推送事件"""
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    info.queue.put({"event": event, "data": data}),
                    self._loop,
                )

        # ---- LangGraph 统一事件回调 ----
        def on_event(etype: str, data: dict):
            data["ts"] = time.strftime("%H:%M:%S")
            if etype == "phase":
                info.progress = {"search": 15, "copy": 40, "critic": 65, "visual": 90}.get(
                    data.get("phase", ""), info.progress)
                # 同时发 log 让前端显示
                _emit("log", {"type": "info",
                              "content": data.get("label", ""),
                              "ts": data["ts"]})
            _emit(etype, data)
            if etype == "log":
                info.logs.append({"type": data.get("type", "info"),
                                  "content": data.get("content", ""),
                                  "ts": data["ts"]})

        # 清理上次生成的旧图片
        import glob as _glob
        for _f in _glob.glob(os.path.join(config.output_dir, "poster_*.jpg")):
            try: os.remove(_f)
            except Exception: pass

        try:
            _emit("log", {"type": "info", "content": f"🧠 选题: {brief[:80]}...",
                          "ts": time.strftime("%H:%M:%S")})

            state = run_graph(
                topic=brief,
                enable_carousel=enable_carousel,
                max_attempts=max_attempts,
                on_event=on_event,
            )

            # 组装结果（兼容旧前端字段）
            task_outputs = {
                "research": state.get("research_context", "")[:2000],
                "copy": state.get("copy_output", ""),
                "critic": state.get("critic_output", ""),
                "visual": "\n".join(state.get("poster_paths", [])),
                "task_0": state.get("research_context", "")[:2000],
                "task_1": state.get("copy_output", ""),
                "task_2": state.get("critic_output", ""),
                "task_3": "",
            }

            poster_paths = state.get("poster_paths", [])
            final_score = state.get("score", 0)

            info.result = {
                "result": state.get("copy_output", ""),
                "task_outputs": task_outputs,
                "poster_paths": poster_paths,
            }
            info.final_score = final_score
            info.progress = 100
            info.status = "done"

            _emit("done", {
                "task_outputs": task_outputs,
                "poster_paths": poster_paths,
                "final_score": final_score,
            })

        except Exception as e:
            tb = traceback.format_exc()
            info.error = f"{e}\n{tb}"
            info.status = "error"
            _emit("error", {"message": str(e), "detail": tb})

    @staticmethod
    def _serialize_result(info: TaskInfo) -> Dict:
        return {
            "task_id": info.task_id,
            "status": info.status,
            "progress": info.progress,
            "logs": info.logs[-50:],  # 只返回最近 50 条
            "result": info.result,
            "final_score": info.final_score,
            "error": info.error,
        }
