"""
=============================================================
小红书 AI Studio - 可观测性模块 (Sprint 2)
=============================================================
集成 Langfuse 做 LLM 调用追踪：成本、延迟、token、错误率

设计为「可选开关」：
  · .env 中配置 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 即自动启用
  · 未配置则所有埋点变成 no-op，不影响主流程
  · LiteLLM（CrewAI 底层）原生支持 Langfuse callback

上线建议：
  · 生产环境必开，否则成本和故障完全是黑盒
  · 也可换 Helicone（改一个 base_url 即可）
=============================================================
"""

import os
import time
from contextlib import contextmanager


# =========================================================
#  Langfuse 启用检测
# =========================================================

def langfuse_enabled() -> bool:
    """是否配置了 Langfuse 凭证"""
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY")
        and os.getenv("LANGFUSE_SECRET_KEY")
    )


def setup_observability():
    """
    初始化可观测性
    在 app.py 启动时调用一次。
    若配置了 Langfuse，把它挂到 LiteLLM 的全局 callback 上，
    这样 CrewAI 所有 LLM 调用都会自动上报。
    """
    if not langfuse_enabled():
        print("[observability] 未配置 Langfuse，监控功能关闭")
        return False

    try:
        import litellm
        # LiteLLM 原生支持 langfuse callback
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        # langfuse host 可选（自托管时用）
        host = os.getenv("LANGFUSE_HOST")
        if host:
            os.environ["LANGFUSE_HOST"] = host
        print("[observability] ✅ Langfuse 已挂载到 LiteLLM callback")
        return True
    except Exception as e:
        print(f"[observability] Langfuse 初始化失败（降级为无监控）: {e}")
        return False


# =========================================================
#  轻量本地成本追踪（不依赖外部服务，始终可用）
# =========================================================

# 各模型每千 token 价格（人民币，参考价，需按实际调整）
PRICE_PER_1K = {
    "deepseek-chat": 0.001,
    "deepseek-reasoner": 0.004,
    "doubao-1-5-pro-32k-250115": 0.0008,
    "qwen-max": 0.0024,
    "qwen-plus": 0.0008,
    "qwen-vl-max": 0.008,
}
# 图像按张计价
PRICE_PER_IMAGE = {
    "doubao-seedream-4-0-250828": 0.20,
    "cogview-3-plus": 0.25,
}


class CostTracker:
    """
    会话级成本追踪器
    在主流程中手动记账（LLM token 数 / 图片张数）
    用于在 UI 上给用户/运营一个成本概览
    """
    def __init__(self):
        self.llm_calls = []      # [{model, tokens, cost}]
        self.image_calls = []    # [{model, cost}]
        self.start_ts = time.time()

    def record_llm(self, model: str, tokens: int):
        unit = PRICE_PER_1K.get(model, 0.002)  # 未知模型给个保守估计
        cost = tokens / 1000 * unit
        self.llm_calls.append({"model": model, "tokens": tokens, "cost": cost})

    def record_image(self, model: str, n: int = 1):
        unit = PRICE_PER_IMAGE.get(model, 0.25)
        for _ in range(n):
            self.image_calls.append({"model": model, "cost": unit})

    def summary(self) -> dict:
        llm_cost = sum(c["cost"] for c in self.llm_calls)
        img_cost = sum(c["cost"] for c in self.image_calls)
        return {
            "llm_calls": len(self.llm_calls),
            "total_tokens": sum(c["tokens"] for c in self.llm_calls),
            "image_count": len(self.image_calls),
            "llm_cost": round(llm_cost, 4),
            "image_cost": round(img_cost, 4),
            "total_cost": round(llm_cost + img_cost, 4),
            "elapsed_sec": round(time.time() - self.start_ts, 1),
        }


@contextmanager
def trace_span(name: str):
    """
    简易耗时追踪上下文管理器
    用法：
        with trace_span("Trend Analyst"):
            ...
    """
    t0 = time.time()
    print(f"[trace] ▶ {name} 开始")
    try:
        yield
    finally:
        print(f"[trace] ◀ {name} 结束，耗时 {time.time()-t0:.1f}s")
