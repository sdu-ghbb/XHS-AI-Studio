"""
=============================================================
小红书 AI Studio - 全局配置
=============================================================
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

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

    # ======== API Keys ========
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "")
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

    # ======== 模型 ID ========
    deepseek_chat_model: str = "deepseek-v4-flash"
    qianwen_embedding_model: str = "text-embedding-v3"
    siliconflow_image_model: str = "Kwai-Kolors/Kolors"

    # ======== 路径 ========
    kb_dir: str = "./kb"
    kb_file: str = "./kb/shadow_kb.json"
    output_dir: str = "./outputs"

    # ======== 质量阈值 ========
    quality_threshold: int = 80

    # ======== API 服务 ========
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list = field(default_factory=lambda: ["*"])

    def validate(self) -> List[str]:
        missing = []
        if not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY")
        if not self.siliconflow_api_key:
            missing.append("SILICONFLOW_API_KEY")
        if not self.qianwen_api_key:
            missing.append("QIANWEN_API_KEY")
        return missing

    def routing_summary(self) -> dict:
        return {
            "LLM": f"DeepSeek / {self.deepseek_chat_model}",
            "Embedding": f"Qianwen / {self.qianwen_embedding_model}",
            "图像模型": f"SiliconFlow / {self.siliconflow_image_model}",
            "搜索引擎": "Bocha" if self.bocha_api_key else "DuckDuckGo",
        }


config = Config()
