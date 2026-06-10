"""
=============================================================
小红书 AI Studio - 全局配置
=============================================================
所有 API Key / Endpoint / Model ID / Agent-Model 路由的单一真源
启动时优先从 ./.env 加载（python-dotenv），然后用环境变量覆盖
=============================================================
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

# ---------- 加载 .env ----------
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
        print(f"[config] 已加载 {_env_path}")
    else:
        print(f"[config] 未发现 .env，将使用环境变量")
except ImportError:
    print("[config] python-dotenv 未安装，仅使用系统环境变量")


@dataclass
class Config:
    """全局配置 - 所有 Agent / Tool 通过这里取值，不直接 os.getenv"""

    # ======== API Keys ========
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "")
    )
    zhipu_api_key: str = field(
        default_factory=lambda: os.getenv("ZHIPU_API_KEY", "")
    )
    doubao_api_key: str = field(
        default_factory=lambda: os.getenv("DOUBAO_API_KEY", "")
    )
    qianwen_api_key: str = field(
        default_factory=lambda: os.getenv("QIANWEN_API_KEY", "")
    )
    bocha_api_key: str = field(
        default_factory=lambda: os.getenv("BOCHA_API_KEY", "")
    )
    siliconflow_api_key: str = field(
        default_factory=lambda: os.getenv("SILICONFLOW_API_KEY", "")
    )

    # ======== API Endpoints ========
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    qianwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bocha_search_url: str = "https://api.bochaai.com/v1/web-search"
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # ======== 文本模型 ID ========
    deepseek_chat_model: str = "deepseek-chat"

    # ======== Embedding 模型 ========
    qianwen_embedding_model: str = "text-embedding-v3"

    # ======== 影子题库路径 ========
    kb_dir: str = "./kb"
    kb_file: str = "./kb/shadow_kb.json"      
    seed_file: str = "./seed_notes.json"     

    # ======== 图像模型 ID ========
    siliconflow_image_model: str = "Kwai-Kolors/Kolors"

    # ======== Agent → Provider 路由（全部统一为 DeepSeek）========
    trend_analyst_provider: str = field(
        default_factory=lambda: os.getenv("TREND_ANALYST_PROVIDER", "deepseek")
    )
    copywriter_provider: str = field(
        default_factory=lambda: os.getenv("COPYWRITER_PROVIDER", "deepseek")
    )
    art_director_provider: str = field(
        default_factory=lambda: os.getenv("ART_DIRECTOR_PROVIDER", "deepseek")
    )
    critic_provider: str = field(
        default_factory=lambda: os.getenv("CRITIC_PROVIDER", "deepseek")
    )

    # ======== 质量阈值 ========
    quality_threshold: int = 80

    # ======== 默认模板/风格 ========
    default_template: str = "knowledge_card"
    fallback_template: str = "quote_card"
    default_subtitle: str = "干货分享"
    critic_weights: dict = field(
        default_factory=lambda: {
            "hook": 0.20, "authenticity": 0.20, "density": 0.25,
            "tags": 0.10, "visual": 0.25,
        }
    )

    # ======== API 服务配置 ========
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list = field(default_factory=lambda: ["*"])

    # ======== 业务参数 ========
    output_dir: str = "./outputs"

    def validate(self) -> List[str]:
        """返回缺失的关键 Key 列表（用于 UI 显示状态）"""
        missing = []
        if not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY (LLM 需要)")
        if not self.siliconflow_api_key:
            missing.append("SILICONFLOW_API_KEY (生图需要)")
        if not self.qianwen_api_key:
            missing.append("QIANWEN_API_KEY (Embedding 需要)")
        return missing

    def routing_summary(self) -> dict:
        """供 UI 展示当前路由配置"""
        return {
            "LLM": f"DeepSeek / {self.deepseek_chat_model}",
            "Embedding": f"Qianwen / {self.qianwen_embedding_model}",
            "图像模型": f"SiliconFlow / {self.siliconflow_image_model}",
            "搜索引擎": "Bocha → DuckDuckGo (降级)" if self.bocha_api_key else "DuckDuckGo",
        }

# 模块级单例
config = Config()