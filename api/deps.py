"""
TuLun AI Studio — FastAPI 依赖注入
"""

from config import config
from knowledge_base import get_kb, ShadowKnowledgeBase
from orchestrator import TaskManager

# 模块级单例
_task_manager: TaskManager = None


def get_task_manager() -> TaskManager:
    """返回 TaskManager 单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


def set_task_manager_loop(loop):
    """在 lifespan 中注入事件循环"""
    mgr = get_task_manager()
    mgr.set_loop(loop)


def get_kb_instance() -> ShadowKnowledgeBase:
    """返回影子题库单例"""
    return get_kb()


def get_config():
    """返回配置单例"""
    return config
