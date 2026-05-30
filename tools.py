"""
=============================================================
小红书 AI Studio - Skill / Tool 工具集 (v1.1)
=============================================================
本版变更：
  · 检索 Skill 替换为博查 (Bocha) 中文搜索，自动降级 DuckDuckGo
  · 新增 Seedream (即梦) 生图能力，主力路径 → CogView 降级
  · 图像 + 叠字仍然原子化（Agent 一次调用完成）
  · 所有 Key/URL 从 config.py 取，不再 os.getenv
=============================================================
"""

import io
import os
import time
import traceback
from pathlib import Path
from typing import Optional, Type

import requests
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont

# CrewAI BaseTool 兼容
try:
    from crewai.tools import BaseTool
except ImportError:
    from crewai_tools import BaseTool  # type: ignore

from config import config


# =========================================================
#  通用工具：带退避的 HTTP 请求
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
            # 4xx 不重试（参数错了）
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
#  Skill 1: BochaSearchTool —— 中文社交内容检索（含进阶搜索）
# =========================================================

class _SearchInput(BaseModel):
    """搜索 Skill 入参"""
    query: str = Field(..., description="搜索关键词")


# 进阶搜索：MCN/运营操盘手写爆款拆解的高质量来源
_DECODE_BOOST_TERMS = "小红书 爆款拆解 OR 流量密码 OR 运营复盘"
_DECODE_PREFER_SITES = ["mp.weixin.qq.com", "zhihu.com", "bilibili.com"]


class BochaSearchTool(BaseTool):
    """
    博查 AI 中文搜索 Skill（v1.4 进阶版 / 方案二）
    -----------------------------------
    普通搜索之外，内置"爆款拆解 Hack"：
        不直接搜小红书 App 内数据（搜不到），而是搜
        "那些专门拆解小红书爆款的文章"——公众号/知乎/B站上
        大量 MCN 机构和运营操盘手写的拆解报告。
        相当于白嫖别人买千瓜数据写出的分析。
    -----------------------------------
    降级链：Bocha → DuckDuckGo → 提示 Agent 用常识
    """
    name: str = "BochaWebSearch"
    description: str = (
        "中文 Web 检索，自动启用'爆款拆解'进阶模式：会优先找到公众号/知乎/B站上"
        "MCN 机构和运营操盘手撰写的小红书爆款拆解、流量密码分析文章。"
        "输入查询关键词，返回带标题/摘要/来源的结果。"
    )
    args_schema: Type[BaseModel] = _SearchInput

    def _enhance_query(self, query: str) -> str:
        """进阶搜索：给查询注入'爆款拆解'强限定词"""
        # 已含拆解类词则不重复加
        decode_kws = ["拆解", "爆款", "流量密码", "复盘", "运营"]
        if any(kw in query for kw in decode_kws):
            base = query
        else:
            base = f"{query} {_DECODE_BOOST_TERMS}"
        # 确保带"小红书"
        if "小红书" not in base:
            base = f"{base} 小红书"
        return base

    def _run(self, query: str) -> str:
        enhanced = self._enhance_query(query)
        print(f"[BochaSearch] 进阶查询: {enhanced}")

        # ----- Bocha 主路径 -----
        if config.bocha_api_key:
            try:
                data = _request_with_retry(
                    "POST", config.bocha_search_url,
                    headers={
                        "Authorization": f"Bearer {config.bocha_api_key}",
                        "Content-Type": "application/json",
                    },
                    json_body={
                        "query": enhanced,
                        "freshness": "oneYear",  # 拆解类文章时效性放宽到一年
                        "summary": True,
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
                    # 优先排序：来自 MCN/运营高质量站点的结果排前面
                    def _priority(p):
                        url = (p.get("url") or "").lower()
                        return 0 if any(s in url for s in _DECODE_PREFER_SITES) else 1
                    pages = sorted(pages, key=_priority)

                    lines = []
                    for p in pages[:6]:
                        title = p.get("name") or "无标题"
                        summary = p.get("summary") or p.get("snippet") or ""
                        site = p.get("siteName") or ""
                        date = (p.get("datePublished") or "")[:10]
                        meta = " · ".join(filter(None, [site, date]))
                        lines.append(f"【{title}】({meta})\n{summary[:450]}")
                    return "\n\n".join(lines)
                else:
                    print("[Bocha] 无结果，降级 DuckDuckGo")
            except Exception as e:
                print(f"[Bocha] 失败({e})，降级 DuckDuckGo")

        # ----- DuckDuckGo 降级 -----
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(enhanced, max_results=6, region="cn-zh"))
            if not results:
                return f"未搜索到 '{query}' 的相关内容，请基于运营常识补足。"
            return "\n\n".join([
                f"【{r.get('title', '')}】\n{(r.get('body') or '')[:400]}"
                for r in results
            ])
        except Exception as e:
            return f"[搜索失败] {e}，请基于运营常识对 '{query}' 进行总结。"


# =========================================================
#  Skill 2: SmartImagePosterTool —— 智能生图 + 模板化叠字 + 组图
# =========================================================

class _PosterInput(BaseModel):
    """海报合成入参"""
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
    template: str = Field(
        default="center_bold",
        description=(
            "海报模板名：center_bold(教程干货) / top_label(好物种草) / "
            "minimalist(治愈情感) / magazine_cover(盘点榜单)"
        ),
    )
    subtitle: str = Field(
        default="",
        description="副标题/标签文字（top_label 和 magazine_cover 模板会用到，≤6字）",
    )
    sub_headlines: str = Field(
        default="",
        description=(
            "可选。组图模式：用 ` | ` 分隔的 2-4 个分页小标题，"
            "如 '第一步备料 | 第二步翻炒 | 第三步装盘'。留空则只生成单张封面。"
        ),
    )


class SmartImagePosterTool(BaseTool):
    """
    智能图像合成 Skill (v1.3)
    -----------------------------------
    · 生图：Seedream 4.0 主力 → CogView 降级
    · 叠字：4 套模板任选（templates.py）
    · 组图：传入 sub_headlines 时额外生成 2-4 张正文配图
    """
    name: str = "ImagePoster"
    description: str = (
        "生成小红书海报。输入英文 prompt + 中文 headline (≤15字) + "
        "template(模板名) + subtitle(可选标签)。"
        "如需组图，额外传 sub_headlines（用 | 分隔的分页标题）。"
        "返回所有生成图片的本地路径。"
    )
    args_schema: Type[BaseModel] = _PosterInput

    output_dir: str = "./outputs"

    def _gen_one_image(self, prompt: str) -> Image.Image:
        """生成一张底图（主备降级），返回 PIL Image"""
        primary = config.image_primary
        order = [primary, "cogview" if primary == "seedream" else "seedream"]
        last_err = None
        for provider in order:
            try:
                print(f"[ImagePoster] 生图尝试 {provider}...")
                if provider == "seedream":
                    image_url = _gen_image_seedream(prompt)
                else:
                    image_url = _gen_image_cogview(prompt)
                img_bytes = requests.get(image_url, timeout=60).content
                return Image.open(io.BytesIO(img_bytes)).convert("RGBA")
            except Exception as e:
                last_err = e
                print(f"[ImagePoster] {provider} 失败: {e}")
                continue
        raise RuntimeError(f"所有图像模型均失败: {last_err}")

    def _run(
        self,
        prompt: str,
        headline: str,
        template: str = "center_bold",
        subtitle: str = "",
        sub_headlines: str = "",
    ) -> str:
        # 延迟导入避免循环依赖
        from templates import get_template

        try:
            os.makedirs(self.output_dir, exist_ok=True)
            tpl = get_template(template)
            results = []

            # ----- 1. 封面 -----
            base_img = self._gen_one_image(prompt)
            cover = tpl.render(base_img, headline, subtitle=subtitle or None)
            cover_path = os.path.join(self.output_dir, "poster_final.jpg")
            cover.convert("RGB").save(cover_path, "JPEG", quality=95)
            results.append(cover_path)
            print(f"[ImagePoster] ✅ 封面: {cover_path} (模板={template})")

            # ----- 2. 组图（可选）-----
            subs = [s.strip() for s in sub_headlines.split("|") if s.strip()]
            for idx, sub_title in enumerate(subs[:4], 1):  # 最多 4 张
                try:
                    # 正文图用稍微变化的 prompt
                    sub_prompt = prompt + f", detail shot variation {idx}"
                    sub_img = self._gen_one_image(sub_prompt)
                    # 正文图统一用 center_bold（信息传达优先）
                    from templates import CenterBoldTemplate
                    sub_poster = CenterBoldTemplate().render(sub_img, sub_title)
                    sub_path = os.path.join(self.output_dir, f"poster_sub_{idx}.jpg")
                    sub_poster.convert("RGB").save(sub_path, "JPEG", quality=95)
                    results.append(sub_path)
                    print(f"[ImagePoster] ✅ 正文图{idx}: {sub_path}")
                except Exception as e:
                    print(f"[ImagePoster] 正文图{idx} 生成失败（跳过）: {e}")

            if len(results) == 1:
                return f"海报已生成: {results[0]}"
            else:
                paths = "\n".join(f"  - {p}" for p in results)
                return f"海报组图已生成（共 {len(results)} 张）:\n{paths}"

        except Exception as e:
            tb = traceback.format_exc()
            print(f"[ImagePoster] 失败: {e}\n{tb}")
            return f"[ERROR] 海报生成失败: {e}"


def _gen_image_seedream(prompt: str) -> str:
    """字节豆包 Seedream 5.0 T2I，返回图片 URL"""
    if not config.doubao_api_key:
        raise RuntimeError("DOUBAO_API_KEY 未配置")
    data = _request_with_retry(
        "POST", f"{config.doubao_base_url}/images/generations",
        headers={
            "Authorization": f"Bearer {config.doubao_api_key}",
            "Content-Type": "application/json",
        },
        json_body={
            "model": config.doubao_seedream_model,
            "prompt": prompt,
            "size": "2K",            # Seedream 5.0 最低要求 3686400px，1024x1024 太小
            "response_format": "url",
            "watermark": True,
        },
        timeout=120,
        max_retries=2,
        label="Seedream",
    )
    return data["data"][0]["url"]


def _gen_image_cogview(prompt: str) -> str:
    """智谱 CogView-3-Plus，返回图片 URL"""
    if not config.zhipu_api_key:
        raise RuntimeError("ZHIPU_API_KEY 未配置")
    from zhipuai import ZhipuAI
    client = ZhipuAI(api_key=config.zhipu_api_key)
    response = client.images.generations(
        model=config.zhipu_cogview_model,
        prompt=prompt,
        size="1024x1024",
    )
    return response.data[0].url


# =========================================================
#  Pillow 中文叠字 - 多级 Fallback
# =========================================================

FONT_CANDIDATES = [
    # Linux
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/STKAITI.TTF",
    # 本地兜底
    "./fonts/SourceHanSansSC-Bold.otf",
    "./fonts/NotoSansSC-Bold.otf",
]

FONT_DOWNLOAD_URL = (
    "https://github.com/adobe-fonts/source-han-sans/raw/release/"
    "OTF/SimplifiedChinese/SourceHanSansSC-Bold.otf"
)


def find_chinese_font() -> Optional[str]:
    """寻找可用中文字体路径：系统 → 网络下载 → None"""
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    try:
        os.makedirs("./fonts", exist_ok=True)
        local_path = "./fonts/SourceHanSansSC-Bold.otf"
        if not Path(local_path).exists():
            print("[Font] 下载 Source Han Sans Bold...")
            r = requests.get(FONT_DOWNLOAD_URL, timeout=90, stream=True)
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            print(f"[Font] ✅ 已下载: {local_path}")
        return local_path
    except Exception as e:
        print(f"[Font] 下载失败: {e}")
        return None


def _wrap_text_cn(text: str, max_chars_per_line: int) -> list:
    text = text.strip().rstrip("。.！!")
    return [text[i:i + max_chars_per_line]
            for i in range(0, len(text), max_chars_per_line)]


def overlay_chinese_title(base_img: Image.Image, title: str) -> Image.Image:
    """白字 + 黑色描边 + 半透明背景条，上方居中"""
    img = base_img.convert("RGBA")
    W, H = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_path = find_chinese_font()
    font_size = W // 11
    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            print(f"[overlay] 字体 {font_path} 加载失败: {e}")
    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

    max_chars = 8 if len(title) > 10 else max(len(title), 1)
    lines = _wrap_text_cn(title, max_chars)
    line_height = int(font_size * 1.3)
    total_h = line_height * len(lines)
    y_start = int(H * 0.12)

    band_padding = int(font_size * 0.5)
    band_top = max(0, y_start - band_padding)
    band_bottom = min(H, y_start + total_h + band_padding)
    band = Image.new("RGBA", (W, band_bottom - band_top), (0, 0, 0, 110))
    overlay.paste(band, (0, band_top), band)
    draw = ImageDraw.Draw(overlay)

    for i, line in enumerate(lines):
        if font is None:
            text_w = len(line) * font_size // 2
        else:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
        x = (W - text_w) / 2
        y = y_start + i * line_height
        if font is not None:
            draw.text(
                (x, y), line, font=font,
                fill=(255, 255, 255, 255),
                stroke_width=max(2, font_size // 18),
                stroke_fill=(0, 0, 0, 235),
            )
        else:
            draw.text((x, y), line, fill=(255, 255, 255, 255))

    return Image.alpha_composite(img, overlay)


# =========================================================
#  Skill 3: VLMCritiqueTool —— Qwen-VL 审图打分
# =========================================================

class _VLMInput(BaseModel):
    """视觉审核入参"""
    image_path: str = Field(
        default="./outputs/poster_final.jpg",
        description="海报图像本地路径（默认 ./outputs/poster_final.jpg）",
    )


class VLMCritiqueTool(BaseTool):
    """
    视觉审核 Skill - 调用 Qwen-VL-Max 看图打分
    -----------------------------------
    输入海报本地路径，返回三维评分 + 改进建议
        · 视觉吸引力  (0-30)
        · 文字可读性  (0-30)
        · 平台契合度  (0-40)
    -----------------------------------
    被 Critic Agent 装配使用
    """
    name: str = "VLMCritique"
    description: str = (
        "对生成的海报图像做视觉审核。输入图像本地路径，"
        "返回详细的视觉评分（总分 100）和具体改进建议。"
    )
    args_schema: Type[BaseModel] = _VLMInput

    def _run(self, image_path: str = "./outputs/poster_final.jpg") -> str:
        try:
            import base64
            from openai import OpenAI

            if not os.path.exists(image_path):
                return f"[VLM ERROR] 图像不存在: {image_path}"

            # ---- 缩图以节省 token / 加速 ----
            with Image.open(image_path) as im:
                im = im.convert("RGB")
                if max(im.size) > 768:
                    im.thumbnail((768, 768))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=85)
                b64 = base64.b64encode(buf.getvalue()).decode()

            client = OpenAI(
                api_key=config.qianwen_api_key,
                base_url=config.qianwen_base_url,
                timeout=60,
            )

            prompt = """你是资深小红书内容质量审核员。请严格审核这张海报。

评分维度（中文输出）：
1. **视觉吸引力** (0-30)：构图、色彩、氛围是否抓眼球，是否有"打开看看"的冲动
2. **文字可读性** (0-30)：标题叠字是否清晰、字号合适、不被背景纹理干扰
3. **平台契合度** (0-40)：是否符合小红书"清新/有质感/温柔/ins 风"的平台调性

⚠️ 严格打分（80+ 才算爆款潜力，72 是及格线）

请按以下格式严格输出（不要任何代码块标记）：
视觉吸引力: X/30 - 一句话原因
文字可读性: X/30 - 一句话原因
平台契合度: X/40 - 一句话原因
海报总分: X/100

问题:
- 问题1
- 问题2

建议:
- 建议1（要可执行，比如 "下次 prompt 增加 soft natural light"）
- 建议2"""

            resp = client.chat.completions.create(
                model=config.qianwen_vl_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}"
                            },
                        },
                    ],
                }],
                temperature=0.2,
                max_tokens=600,
            )
            return resp.choices[0].message.content.strip()

        except Exception as e:
            tb = traceback.format_exc()
            print(f"[VLMCritique] 失败: {e}\n{tb}")
            return f"[VLM ERROR] {e}（视觉审核暂不可用，请按经验评估海报）"


# =========================================================
#  Skill 4: ComplianceCheckTool —— 小红书违禁词审查
# =========================================================

class _ComplianceInput(BaseModel):
    """合规审查入参"""
    text: str = Field(..., description="待审查的文案全文")


class ComplianceCheckTool(BaseTool):
    """
    合规审查 Skill
    -----------------------------------
    检测文案中的违禁词（极限词/医疗功效词/引流词等）
    返回风险等级 + 命中清单 + 修改建议
    被 Copywriter 装配，在产出后自查
    """
    name: str = "ComplianceCheck"
    description: str = (
        "检查文案是否含小红书/广告法违禁词（极限词、医疗功效词、"
        "引流营销词等）。输入文案全文，返回风险等级和需要修改的词清单。"
    )
    args_schema: Type[BaseModel] = _ComplianceInput

    def _run(self, text: str) -> str:
        from compliance import check_compliance, format_compliance_report
        result = check_compliance(text)
        report = format_compliance_report(result)
        # 给 Agent 一个明确的行动指令
        if not result["safe"]:
            report += (
                f"\n\n⚠️ 行动要求：上述违禁词必须全部替换或删除后才能发布。"
                f"请改写文案，用建议中的安全说法替代。"
            )
        return report


# =========================================================
#  Skill 5: ShadowKBTool —— 影子题库 RAG 检索（方案一）
# =========================================================

class _KBSearchInput(BaseModel):
    """影子题库检索入参"""
    query: str = Field(..., description="选题关键词")
    category: str = Field(
        default="",
        description="可选品类过滤：穿搭/护肤美妆/美食/旅行/家居好物/学习职场/健身减脂/数码",
    )


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
        "输入选题关键词（可选品类过滤），返回 Top-N 篇真实爆款的标题+正文+点赞数。"
        "这是分析爆款痛点和标题套路的首选数据源，应优先于网络搜索使用。"
    )
    args_schema: Type[BaseModel] = _KBSearchInput

    def _run(self, query: str, category: str = "") -> str:
        try:
            from knowledge_base import get_kb
            kb = get_kb()

            if not kb.is_ready():
                return (
                    "[影子题库未构建] 本地题库为空。"
                    "请改用 BochaWebSearch 工具进行网络搜索。"
                    "（提示：运行 python build_kb.py --seed 可快速构建题库）"
                )

            results = kb.search(
                query=query,
                top_k=15,
                category=category or None,
            )
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
