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

    # ======== API Endpoints ========
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    qianwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bocha_search_url: str = "https://api.bochaai.com/v1/web-search"

    # ======== 文本模型 ID ========
    # 如果上游升级了模型，只改这里
    deepseek_chat_model: str = "deepseek-chat"
    deepseek_reasoner_model: str = "deepseek-reasoner"
    doubao_pro_model: str = "doubao-1-5-pro-32k-250115"
    doubao_lite_model: str = "doubao-1-5-lite-32k-250115"
    qianwen_max_model: str = "qwen-max"
    qianwen_plus_model: str = "qwen-plus"

    # ======== 视觉理解模型 (用于 Critic 审图) ========
    qianwen_vl_model: str = "qwen-vl-max"  # 也可换 qwen-vl-plus 省钱

    # ======== Embedding 模型 (用于影子题库 RAG) ========
    qianwen_embedding_model: str = "text-embedding-v3"

    # ======== 影子题库路径 ========
    kb_dir: str = "./kb"
    kb_file: str = "./kb/shadow_kb.json"      # 构建后的向量库（含向量）
    seed_file: str = "./seed_notes.json"      # 内置种子库（项目根目录）

    # ======== 图像模型 ID ========
    zhipu_cogview_model: str = "cogview-3-plus"
    # Seedream 4.0 是当前最新（2025-09 上线 4K 能力），如果账号未开通可改回 3.0:
    #   "doubao-seedream-3-0-t2i-250415"
    doubao_seedream_model: str = "doubao-seedream-5-0-260128"

    # ======== Agent → Provider 路由（可被环境变量覆盖） ========
    trend_analyst_provider: str = field(
        default_factory=lambda: os.getenv("TREND_ANALYST_PROVIDER", "qianwen")
    )
    copywriter_provider: str = field(
        default_factory=lambda: os.getenv("COPYWRITER_PROVIDER", "doubao")
    )
    art_director_provider: str = field(
        default_factory=lambda: os.getenv("ART_DIRECTOR_PROVIDER", "deepseek")
    )
    critic_provider: str = field(
        default_factory=lambda: os.getenv("CRITIC_PROVIDER", "qianwen-plus")
    )

    # ======== 质量阈值 ========
    quality_threshold: int = 75  # 综合评分低于此值标红提示

    # 图像模型主备
    image_primary: str = field(
        default_factory=lambda: os.getenv("IMAGE_PRIMARY", "seedream")
    )

    # ======== 业务参数 ========
    output_dir: str = "./outputs"

    def validate(self) -> List[str]:
        """返回缺失的关键 Key 列表（用于 UI 显示状态）"""
        missing = []
        # 检查每个被路由用到的 provider 是否有 Key
        used_providers = {
            self.trend_analyst_provider,
            self.copywriter_provider,
            self.art_director_provider,
        }
        provider_key_map = {
            "deepseek": ("DEEPSEEK_API_KEY", self.deepseek_api_key),
            "doubao": ("DOUBAO_API_KEY", self.doubao_api_key),
            "qianwen": ("QIANWEN_API_KEY", self.qianwen_api_key),
        }
        for p in used_providers:
            if p in provider_key_map:
                name, val = provider_key_map[p]
                if not val:
                    missing.append(name)

        # 图像主模型
        if self.image_primary == "seedream" and not self.doubao_api_key:
            missing.append("DOUBAO_API_KEY (Seedream 需要)")
        if self.image_primary == "cogview" and not self.zhipu_api_key:
            missing.append("ZHIPU_API_KEY (CogView 需要)")

        # 至少一个图像 Key 兜底（降级用）
        if not self.zhipu_api_key and not self.doubao_api_key:
            missing.append("至少一个图像 Key (ZHIPU 或 DOUBAO)")

        # 搜索 Key（Bocha 缺失会降级 DDG，不算硬缺）
        # 不加进 missing

        return list(set(missing))

    def routing_summary(self) -> dict:
        """供 UI 展示当前路由配置"""
        return {
            "趋势分析": f"{self.trend_analyst_provider} / {self._model_for(self.trend_analyst_provider)}",
            "文案创作": f"{self.copywriter_provider} / {self._model_for(self.copywriter_provider)}",
            "视觉总监": f"{self.art_director_provider} / {self._model_for(self.art_director_provider)}",
            "质量审核": f"{self.critic_provider} / {self._model_for(self.critic_provider)}",
            "视觉审图": f"qwen-vl / {self.qianwen_vl_model}",
            "主力图像": (
                f"Seedream ({self.doubao_seedream_model})" if self.image_primary == "seedream"
                else f"CogView ({self.zhipu_cogview_model})"
            ),
            "图像降级": (
                f"CogView" if self.image_primary == "seedream"
                else "Seedream"
            ),
            "搜索引擎": "Bocha → DuckDuckGo (降级)" if self.bocha_api_key else "DuckDuckGo",
        }

    def _model_for(self, provider: str) -> str:
        return {
            "deepseek": self.deepseek_chat_model,
            "deepseek-reasoner": self.deepseek_reasoner_model,
            "doubao": self.doubao_pro_model,
            "doubao-lite": self.doubao_lite_model,
            "qianwen": self.qianwen_max_model,
            "qianwen-plus": self.qianwen_plus_model,
        }.get(provider, "?")


# 模块级单例
config = Config()
