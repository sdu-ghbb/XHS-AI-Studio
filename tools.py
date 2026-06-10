"""
=============================================================
小红书 AI Studio - Tool 工具集
=============================================================
本版变更：
  · 检索 Skill 替换为博查 (Bocha) 中文搜索，自动降级 DuckDuckGo
  · 图像生成统一使用 SiliconFlow Kolors
  · 图像 + 叠字仍然原子化（Agent 一次调用完成）
  · 所有 Key/URL 从 config.py 取，不再 os.getenv
=============================================================
"""

import io
import os
import time
import traceback
from typing import Optional, Type
import requests
from pydantic import BaseModel, Field
from PIL import Image
from config import config


# ---- 最小化 Tool 基类（替代 crewai.tools.BaseTool） ----
class BaseTool:
    """工具基类：name / description 供 LLM 理解，_run 供代码调用"""
    name: str = "base_tool"
    description: str = ""
    args_schema: type = None

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def _run(self, *args, **kwargs) -> str:
        raise NotImplementedError


# =========================================================
#  通用工具：HTTP 请求
# =========================================================
def _request_with_retry(
    method: str,
    url: str,
    *,
    headers=None,
    json_body=None,
    timeout: int = 60,
    max_retries: int = 3,
    label: str = "request",
) -> Optional[dict]:
    """对外部 API 的统一封装：N 次重试 + 指数退避"""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(
                method, url,
                headers=headers,
                json=json_body,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and 400 <= e.response.status_code < 500:
                print(f"[{label}] HTTP {e.response.status_code}: {e.response.text[:200]}")
                raise
            last_exc = e
        except Exception as e:
            last_exc = e
        if attempt < max_retries:
            wait = 2 ** attempt
            print(f"[{label}] 第 {attempt} 次失败({last_exc})，{wait}s 后重试...")
            time.sleep(wait)
    raise last_exc


# =========================================================
#  Tool 1: BochaSearchTool —— 检索工具
# =========================================================

class _SearchInput(BaseModel):
    """搜索 Skill 入参"""
    query: str = Field(..., description="搜索关键词")  # 告知 Agent 输入的参数及其类型

# 搜索偏好站点
_PREFER_SITES = ["xiaohongshu.com", "zhihu.com", "mp.weixin.qq.com"]


class BochaSearchTool(BaseTool):
    name: str = "BochaWebSearch"
    description: str = (
        "中文 Web 检索工具。输入查询关键词，"  # 告知 Agent 什么时候调用
        "返回带标题/摘要/来源的搜索结果。"
    )
    args_schema: Type[BaseModel] = _SearchInput  # 定义输入参数

    def _run(self, query: str) -> str:
        print(f"[BochaSearch] 搜索: {query}")

        # ----- Bocha -----
        if config.bocha_api_key:
            try:
                data = _request_with_retry(
                    "POST", config.bocha_search_url,
                    headers={
                        "Authorization": f"Bearer {config.bocha_api_key}",
                        "Content-Type": "application/json",
                    },
                    json_body={
                        "query": query,
                        "count": 10,
                    },
                    timeout=30,
                    max_retries=2,
                    label="Bocha",
                )
                pages = (
                    data.get("data", {})
                    .get("webPages", {})
                    .get("value", [])
                )
                if pages:
                    def _priority(p):
                        url = (p.get("url") or "").lower()
                        return 0 if any(s in url for s in _PREFER_SITES) else 1
                    pages = sorted(pages, key=_priority)

                    lines = []
                    for p in pages[:6]:
                        title = p.get("name") or "无标题"
                        url = p.get("url") or ""
                        summary = p.get("summary") or p.get("snippet") or ""
                        site = p.get("siteName") or ""
                        date = (p.get("datePublished") or "")[:10]
                        meta = " · ".join(filter(None, [site, date]))
                        lines.append(f"【{title}】({meta})\n{url}\n{summary[:450]}")
                    return "\n\n".join(lines)
                else:
                    print("[Bocha] 无结果，降级 DuckDuckGo")
            except Exception as e:
                print(f"[Bocha] 失败({e})，降级 DuckDuckGo")

        # ----- DuckDuckGo -----
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=6))
            if not results:
                return f"未搜索到 '{query}' 的相关内容，请基于运营常识补足。"
            return "\n\n".join([
                f"【{r.get('title', '')}】\n{(r.get('body') or '')[:400]}"
                for r in results
            ])
        except Exception as e:
            return f"[搜索失败] {e}，请基于运营常识对 '{query}' 进行总结。"


# =========================================================
#  Tool 2: 生图 + 模板化叠字 + 组图
# =========================================================

class _PosterInput(BaseModel):
    prompt: str = Field(
        ...,
        description=(
            "图像生成 prompt（英文效果最佳；务必包含 'no text, no letters, "
            "no words, no typography' 避免底图自带文字）"
        ),
    )
    headline: str = Field(
        ...,
        description="叠加在图片正中的中文大标题（≤15 字）",
    )
    sub_headlines: str = Field(
        default="",
        description=(
            "可选。组图模式：用 ` | ` 分隔的 2-4 个分页小标题，"
            "如 '第一步备料 | 第二步翻炒 | 第三步装盘'。留空则只生成单张封面。"
        ),
    )
    sub_prompts: str = Field(
        default="",
        description=(
            "可选。每张正文图各自的 prompt，用 ` ||| ` 分隔。"
            "数量应与 sub_headlines 的分页数一致。"
            "每张图的 prompt 应描述与该页标题内容相符的独立画面。"
            "留空则自动用主 prompt 加 variation 后缀。"
        ),
    )


class SmartImagePosterTool(BaseTool):
    name: str = "ImagePoster"
    description: str = (
        "生成小红书海报。输入英文 prompt + 中文 headline (≤15字)。"
        "如需组图，额外传 sub_headlines（用 | 分隔的分页标题）。"
        "返回所有生成图片的本地路径。"
    )
    args_schema: Type[BaseModel] = _PosterInput

    output_dir: str = "./outputs"

    def _gen_one_image(self, prompt: str) -> Image.Image:
        from style import gen_image_siliconflow
        image_url = gen_image_siliconflow(prompt)
        img_bytes = requests.get(image_url, timeout=60).content
        return Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    def _run(
        self,
        prompt: str,
        headline: str,
        sub_headlines: str = "",
        sub_prompts: str = "",
    ) -> str:
        from style import render_poster as _render_img
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            os.makedirs(self.output_dir, exist_ok=True)
            results = [None]

            subs = [s.strip() for s in sub_headlines.split("|") if s.strip()]
            sub_prompts_list = [p.strip() for p in sub_prompts.split("|||") if p.strip()]
            gen_tasks = [(prompt, "cover")]
            for idx, sub_title in enumerate(subs[:4], 1):
                sp = sub_prompts_list[idx - 1] if idx - 1 < len(sub_prompts_list) else (
                    prompt + f", detail shot variation {idx}"
                )
                gen_tasks.append((sp, f"sub_{idx}"))

            images = {}
            with ThreadPoolExecutor(max_workers=min(len(gen_tasks), 4)) as pool:
                future_map = {}
                for i, (p, role) in enumerate(gen_tasks):
                    future = pool.submit(self._gen_one_image, p)
                    future_map[future] = (i, role)

                for future in as_completed(future_map):
                    i, role = future_map[future]
                    try:
                        images[i] = future.result()
                        print(f"[ImagePoster] ✅ 底图生成完成: {role}")
                    except Exception as e:
                        print(f"[ImagePoster] ❌ 底图生成失败 {role}: {e}")

            if 0 in images:
                cover = _render_img(images[0], headline)
                cover_path = os.path.join(self.output_dir, "poster_final.jpg")
                cover.convert("RGB").save(cover_path, "JPEG", quality=95)
                results[0] = cover_path
                print(f"[ImagePoster] ✅ 封面: {cover_path}")

            for idx, sub_title in enumerate(subs[:4], 1):
                if idx in images:
                    try:
                        from style import render_poster as _render_sub
                        sub_poster = _render_sub(images[idx], sub_title)
                        sub_path = os.path.join(self.output_dir, f"poster_sub_{idx}.jpg")
                        sub_poster.convert("RGB").save(sub_path, "JPEG", quality=95)
                        results.append(sub_path)
                        print(f"[ImagePoster] ✅ 正文图{idx}: {sub_path}")
                    except Exception as e:
                        print(f"[ImagePoster] 正文图{idx} 生成失败（跳过）: {e}")

            results = [r for r in results if r is not None]
            if len(results) == 1:
                return f"海报已生成: {results[0]}"
            else:
                paths = "\n".join(f"  - {p}" for p in results)
                return f"海报组图已生成（共 {len(results)} 张）:\n{paths}"

        except Exception as e:
            tb = traceback.format_exc()
            print(f"[ImagePoster] 失败: {e}\n{tb}")
            return f"[ERROR] 海报生成失败: {e}"


# =========================================================
#  Tool 3: ShadowKBTool —— 影子题库 RAG 检索
# =========================================================

class _KBSearchInput(BaseModel):
    query: str = Field(..., description="选题关键词")


class ShadowKBTool(BaseTool):
    """
    影子题库检索 Skill（方案一：本地 RAG）
    -----------------------------------
    从本地维护的"优质历史爆款库"检索与选题最相关的真实爆款笔记。
    相比实时网络搜索：
        · 零成本、100% 合规（不爬小红书）
        · 喂给 LLM 的是 100% 纯正小红书语料
    检索结果供 Trend Analyst 提炼痛点和标题公式。
    -----------------------------------
    若题库未构建，返回明确提示，Trend Analyst 应改用 BochaWebSearch。
    """
    name: str = "ShadowKBSearch"
    description: str = (
        "从本地影子题库（历史真实爆款笔记库）检索与选题最相关的爆款样本。"
        "输入选题关键词，返回 Top-N 篇真实爆款的标题+正文+点赞数。"
        "这是分析爆款痛点和标题套路的首选数据源，应优先于网络搜索使用。"
    )
    args_schema: Type[BaseModel] = _KBSearchInput

    def _run(self, query: str) -> str:
        try:
            from knowledge_base import get_kb
            kb = get_kb()

            if not kb.is_ready():
                return (
                    "[影子题库未构建] 本地题库为空。"
                    "请改用 BochaWebSearch 工具进行网络搜索。"
                    "（提示：运行 python build_kb.py --seed 可快速构建题库）"
                )

            results = kb.search(query=query, top_k=15)
            mode_note = (
                "向量 RAG 检索" if kb.mode == "vector"
                else "关键词匹配（题库未向量化，建议运行 build_kb.py）"
            )
            header = f"[影子题库 · {mode_note}]\n"
            return header + kb.format_for_agent(results)

        except Exception as e:
            import traceback
            print(f"[ShadowKB] 检索失败: {e}\n{traceback.format_exc()}")
            return (
                f"[影子题库检索异常] {e}。"
                "请改用 BochaWebSearch 工具。"
            )