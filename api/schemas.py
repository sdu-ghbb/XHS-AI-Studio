"""
TuLun AI Studio — API 请求/响应 Pydantic 模型
"""

from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field


# =========================================================
#  生成任务
# =========================================================

class GenerateRequest(BaseModel):
    """提交生成请求"""
    brief: str = Field(..., description="选题简报（Clarifier 输出或直接输入）")
    enable_carousel: bool = Field(False, description="是否生成组图（封面+正文图）")
    enable_retry: bool = Field(True, description="是否启用自检重试")


class GenerateResponse(BaseModel):
    """生成任务提交响应"""
    task_id: str = Field(..., description="任务 ID，用于轮询结果 / 订阅 SSE")


# =========================================================
#  任务状态与结果
# =========================================================

class LogEntry(BaseModel):
    """单条日志"""
    type: str = "info"   # info | step | error | done
    content: str = ""
    ts: str = ""


class TaskStatus(BaseModel):
    """任务状态查询响应"""
    task_id: str
    status: str           # queued | running | done | error
    progress: int = 0     # 0-100
    logs: List[LogEntry] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    final_score: Optional[int] = None
    error: Optional[str] = None


class TaskStatusResponse(BaseModel):
    """带任务状态的任务响应"""
    task_id: str
    status: str
    progress: int = 0
    logs: List[LogEntry] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    final_score: Optional[int] = None
    error: Optional[str] = None
    poster_paths: List[str] = Field(default_factory=list)


# =========================================================
#  配置查询
# =========================================================

class StyleOption(BaseModel):
    """风格选项"""
    key: str
    label: str
    base_preview: str = ""


class TemplateOption(BaseModel):
    """模板选项"""
    name: str
    description: str
    suitable_for: str = ""


class ConfigResponse(BaseModel):
    """配置信息"""
    styles: List[StyleOption]
    templates: List[TemplateOption]
    routing: Dict[str, str]
    health: Dict[str, Any]


# =========================================================
#  Clarifier
# =========================================================

class ClarifierKickoffRequest(BaseModel):
    """提交原始选题"""
    topic: str = Field(..., description="用户输入的原始选题")


class ClarifierQuestion(BaseModel):
    """单个框架问题"""
    key: str
    label: str
    question: str
    options: Optional[List[str]] = None
    examples: Optional[List[str]] = None


class ClarifierKickoffResponse(BaseModel):
    """Clarifier 初始化响应"""
    questions: List[ClarifierQuestion]
    raw_topic: str


class ClarifierFollowupRequest(BaseModel):
    """提交框架答案，获取 LLM 追问"""
    raw_topic: str
    answers: Dict[str, str]


class ClarifierFollowupResponse(BaseModel):
    """LLM 追问响应"""
    followup_question: str


class ClarifierBriefRequest(BaseModel):
    """提交全部信息，组装简报"""
    raw_topic: str
    framework_answers: Dict[str, str]
    style_key: str = ""
    mood: str = ""
    user_detail: str = ""
    llm_followup_question: str = ""
    llm_followup_answer: str = ""


class ClarifierBriefResponse(BaseModel):
    """选题简报响应"""
    brief: str


# =========================================================
#  风格 RAG 搜索
# =========================================================

class StyleSearchRequest(BaseModel):
    """风格搜索请求"""
    query: str = Field(..., description="选题关键词")


class StyleSearchResult(BaseModel):
    """单条搜索结果"""
    title: str
    content: str
    likes: int = 0
    tags: List[str] = Field(default_factory=list)


class StyleSearchResponse(BaseModel):
    """风格搜索响应"""
    results: List[StyleSearchResult]
    mode: str = "vector"


# =========================================================
#  标题候选生成
# =========================================================

class HeadlineRequest(BaseModel):
    topic: str = Field(..., description="选题关键词")


class HeadlineResponse(BaseModel):
    headlines: List[str] = Field(default_factory=list)
    error: Optional[str] = None


# =========================================================
#  健康检查
# =========================================================

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    kb_ready: bool = False
    kb_mode: str = "none"
    kb_count: int = 0
    config_valid: bool = False
