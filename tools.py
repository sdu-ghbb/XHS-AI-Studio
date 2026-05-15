"""
=============================================================
小红书爆款图文生成 Agent —— Skill / Tool 工具集
=============================================================
封装核心技能（Skills），供 CrewAI Agent 装配调用：
    Skill 1 ▸ WebSearchTool         —— 信息检索（Tavily ➜ DuckDuckGo 自动降级）
    Skill 2 ▸ ZhipuImagePosterTool  —— 智谱 CogView 生图 + Pillow 叠字（原子化）
    Skill 2.5 ▸ Pillow 中文叠字函数 —— 多级字体 Fallback，保证中文可读
=============================================================
"""

import io
import os
import re
import traceback
from pathlib import Path
from typing import Optional, Type

import requests
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont

# CrewAI 工具基类（兼容 0.5x ~ 最新版本）
try:
    from crewai.tools import BaseTool
except ImportError:                                          # 老版本兼容
    from crewai_tools import BaseTool                        # type: ignore


# =========================================================
#  Skill 1: WebSearchTool —— 信息检索
# =========================================================

class _SearchInput(BaseModel):
    """检索 Skill 入参 Schema"""
    query: str = Field(..., description="搜索关键词（中文/英文均可）")


class WebSearchTool(BaseTool):
    """
    多源 Web 搜索 Skill
    -----------------------------------
    工作策略：
        1. 优先 Tavily（如果环境变量 TAVILY_API_KEY 存在）—— 结果更结构化、噪声小
        2. 自动降级到 DuckDuckGo —— 无需 Key，cn-zh 区域
        3. 若都失败 —— 返回友好的失败说明，Agent 可自己用常识补救
    """
    name: str = "WebSearch"
    description: str = (
        "用于检索全网最新趋势、热门话题、用户痛点、爆款标题套路等信息。"
        "输入一个查询关键词字符串，返回若干条搜索结果的标题+摘要。"
    )
    args_schema: Type[BaseModel] = _SearchInput

    def _run(self, query: str) -> str:
        # ----- 方案 A: Tavily -----
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            try:
                from tavily import TavilyClient
                client = TavilyClient(api_key=tavily_key)
                resp = client.search(
                    query=query,
                    max_results=5,
                    search_depth="basic",
                )
                results = resp.get("results", [])
                if results:
                    return "\n\n".join([
                        f"【{r.get('title', '无标题')}】\n{(r.get('content') or '')[:400]}"
                        for r in results
                    ])
            except Exception as e:
                # 不抛出，进入 DuckDuckGo 降级
                print(f"[WebSearch] Tavily 失败，降级 DuckDuckGo: {e}")

        # ----- 方案 B: DuckDuckGo -----
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5, region="cn-zh"))
            if not results:
                return f"未搜索到 '{query}' 的相关结果。请基于常识与经验自行总结热点。"
            return "\n\n".join([
                f"【{r.get('title', '')}】\n{(r.get('body') or '')[:400]}"
                for r in results
            ])
        except Exception as e:
            return (
                f"[搜索失败] {e}\n"
                f"建议你基于自身的内容运营常识对 '{query}' 这个话题"
                f"进行痛点拆解和标题套路总结。"
            )


# =========================================================
#  Skill 2: ZhipuImagePosterTool —— CogView 生图 + Pillow 叠字
# =========================================================

class _PosterInput(BaseModel):
    """海报合成 Skill 入参 Schema"""
    prompt: str = Field(
        ...,
        description=(
            "图像生成的 Prompt 描述（英文效果更佳；不要在图里出现任何文字，"
            "文字将由后期 Pillow 叠加。请用 'no text, no letters' 等否定式提示）"
        ),
    )
    headline: str = Field(
        ...,
        description="需要叠加在图片正中上方的中文大标题，≤15 字",
    )


class ZhipuImagePosterTool(BaseTool):
    """
    视觉合成 Skill（原子化）
    -----------------------------------
    一次调用完成两件事：
        Step 1: 智谱 CogView-3-Plus 生成 1024x1024 底图
        Step 2: Pillow 在底图上叠加中文大标题（白字 + 黑色描边 + 半透明背景条）
    -----------------------------------
    返回：最终海报本地路径
    """
    name: str = "ZhipuImagePoster"
    description: str = (
        "生成小红书风格海报。输入：图像 prompt（英文）+ headline（中文 ≤15 字）。"
        "工具会先调用智谱 CogView 生成底图，再用 Pillow 叠字，"
        "返回最终海报在本地的保存路径字符串。"
    )
    args_schema: Type[BaseModel] = _PosterInput

    # 允许在外部注入输出目录
    output_dir: str = "./outputs"

    def _run(self, prompt: str, headline: str) -> str:
        try:
            api_key = os.getenv("ZHIPUAI_API_KEY")
            if not api_key:
                return "[ERROR] ZHIPUAI_API_KEY 未配置，请在侧边栏填写后重试。"

            # --------- Step 1: 智谱 CogView 生图 ---------
            from zhipuai import ZhipuAI
            client = ZhipuAI(api_key=api_key)
            print(f"[ZhipuImagePoster] 正在呼叫智谱 CogView-3-Plus 生图...")
            print(f"  prompt = {prompt[:120]}...")

            response = client.images.generations(
                model="cogview-3-plus",
                prompt=prompt,
                size="1024x1024",
            )
            image_url = response.data[0].url
            print(f"[ZhipuImagePoster] 智谱返回图片 URL: {image_url}")

            # 下载到内存
            img_resp = requests.get(image_url, timeout=60)
            img_resp.raise_for_status()
            base_img = Image.open(io.BytesIO(img_resp.content)).convert("RGBA")

            # --------- Step 2: Pillow 叠字排版 ---------
            print(f"[ZhipuImagePoster] 正在叠加中文标题: {headline}")
            poster = overlay_chinese_title(base_img, headline)

            # 保存
            os.makedirs(self.output_dir, exist_ok=True)
            output_path = os.path.join(self.output_dir, "poster_final.jpg")
            poster.convert("RGB").save(output_path, "JPEG", quality=95)

            print(f"[ZhipuImagePoster] ✅ 海报已落盘: {output_path}")
            return f"海报已生成: {output_path}"

        except Exception as e:
            tb = traceback.format_exc()
            print(f"[ZhipuImagePoster] ❌ 失败: {e}\n{tb}")
            return f"[ERROR] 海报生成失败: {e}"


# =========================================================
#  Skill 2.5: Pillow 中文叠字（核心鲁棒函数）
# =========================================================

#: 系统常见中文字体路径（优先级从上到下）
FONT_CANDIDATES = [
    # Linux —— Noto / 文泉驿
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
    # 项目本地（网络下载的兜底）
    "./fonts/SourceHanSansSC-Bold.otf",
    "./fonts/NotoSansSC-Bold.otf",
]

#: 网络下载备用字体（Adobe 思源黑体 Bold，免费可商用）
FONT_DOWNLOAD_URL = (
    "https://github.com/adobe-fonts/source-han-sans/raw/release/"
    "OTF/SimplifiedChinese/SourceHanSansSC-Bold.otf"
)


def find_chinese_font() -> Optional[str]:
    """
    寻找可用的中文字体路径
    1) 遍历系统常见路径
    2) 若全部缺失，则下载 Source Han Sans 到 ./fonts/
    3) 网络也失败时返回 None，由调用方做兜底
    """
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path

    # 网络下载
    try:
        os.makedirs("./fonts", exist_ok=True)
        local_path = "./fonts/SourceHanSansSC-Bold.otf"
        if not Path(local_path).exists():
            print("[Font] 系统未发现中文字体，正在下载 Source Han Sans Bold...")
            resp = requests.get(FONT_DOWNLOAD_URL, timeout=90, stream=True)
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            print(f"[Font] ✅ 字体已下载: {local_path}")
        return local_path
    except Exception as e:
        print(f"[Font] ❌ 字体下载失败: {e}")
        return None


def _wrap_text_cn(text: str, max_chars_per_line: int) -> list:
    """按字符数粗暴换行，对中文足够用"""
    text = text.strip().rstrip("。.！!")
    return [text[i:i + max_chars_per_line]
            for i in range(0, len(text), max_chars_per_line)]


def overlay_chinese_title(base_img: Image.Image, title: str) -> Image.Image:
    """
    在底图上叠加中文大标题
    -----------------------------------
    设计：
        - 上方 12% 位置开始
        - 白字 + 黑色描边 + 半透明黑色背景条 → 任何底图都能保证可读性
        - 字号根据图宽自适应
    """
    img = base_img.convert("RGBA")
    W, H = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # ----- 字体加载（多级 Fallback）-----
    font_path = find_chinese_font()
    font_size = W // 11  # 1024 px 时约 93 pt
    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            print(f"[overlay] 字体 {font_path} 加载失败: {e}")

    if font is None:
        # 终极兜底：用默认字体，避免崩溃（但会显示方框/拼音）
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

    # ----- 换行 -----
    max_chars = 8 if len(title) > 10 else max(len(title), 1)
    lines = _wrap_text_cn(title, max_chars)
    line_height = int(font_size * 1.3)
    total_h = line_height * len(lines)

    y_start = int(H * 0.12)

    # ----- 半透明背景条（提升对比度）-----
    band_padding = int(font_size * 0.5)
    band_top = max(0, y_start - band_padding)
    band_bottom = min(H, y_start + total_h + band_padding)
    band = Image.new("RGBA", (W, band_bottom - band_top), (0, 0, 0, 110))
    overlay.paste(band, (0, band_top), band)
    draw = ImageDraw.Draw(overlay)  # 重新拿 draw

    # ----- 逐行绘制：白字 + 黑色描边 -----
    for i, line in enumerate(lines):
        if font is None:
            # 没字体的兜底估算
            text_w = len(line) * font_size // 2
        else:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
        x = (W - text_w) / 2
        y = y_start + i * line_height

        if font is not None:
            draw.text(
                (x, y), line,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=max(2, font_size // 18),
                stroke_fill=(0, 0, 0, 235),
            )
        else:
            draw.text((x, y), line, fill=(255, 255, 255, 255))

    return Image.alpha_composite(img, overlay)
