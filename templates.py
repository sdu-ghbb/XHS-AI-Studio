"""
=============================================================
小红书 AI Studio - 海报模板引擎 (Sprint 3)
=============================================================
4 套主流小红书封面套路，每套对应不同内容调性：
    center_bold     ── 中央粗体（教程/干货类，原 v1.2 默认）
    top_label       ── 顶部小标签 + 底部大字（好物推荐类）
    minimalist      ── 极简单行（情感/治愈类）
    magazine_cover  ── 杂志风超大字（榜单/盘点类）

每个模板实现统一接口:
    render(base_img, headline, subtitle=None) -> Image
=============================================================
"""

import os
from pathlib import Path
from typing import Optional, Dict
from abc import ABC, abstractmethod

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# =========================================================
#  字体管理（与 tools.py 中的逻辑一致，避免循环依赖）
# =========================================================

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "./fonts/SourceHanSansSC-Bold.otf",
]

FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "./fonts/SourceHanSansSC-Regular.otf",
    "./fonts/SourceHanSansSC-Bold.otf",  # 兜底
]

FONT_DOWNLOAD_URL = (
    "https://github.com/adobe-fonts/source-han-sans/raw/release/"
    "OTF/SimplifiedChinese/SourceHanSansSC-Bold.otf"
)


def _find_font(candidates) -> Optional[str]:
    for p in candidates:
        if Path(p).exists():
            return p
    try:
        os.makedirs("./fonts", exist_ok=True)
        local = "./fonts/SourceHanSansSC-Bold.otf"
        if not Path(local).exists():
            r = requests.get(FONT_DOWNLOAD_URL, timeout=90, stream=True)
            r.raise_for_status()
            with open(local, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        return local
    except Exception:
        return None


def find_bold_font() -> Optional[str]:
    return _find_font(FONT_CANDIDATES_BOLD)


def find_regular_font() -> Optional[str]:
    return _find_font(FONT_CANDIDATES_REGULAR)


def _wrap_cn(text: str, max_chars: int) -> list:
    text = text.strip().rstrip("。.！!")
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


# =========================================================
#  Template 基类
# =========================================================

class PosterTemplate(ABC):
    """所有海报模板的统一接口"""
    name: str = "base"
    description: str = ""
    suitable_for: str = ""

    @abstractmethod
    def render(
        self,
        base_img: Image.Image,
        headline: str,
        subtitle: Optional[str] = None,
    ) -> Image.Image:
        ...


# =========================================================
#  Template 1: 中央粗体（教程/干货类）
# =========================================================

class CenterBoldTemplate(PosterTemplate):
    name = "center_bold"
    description = "中央粗体大字 + 黑色描边 + 半透明背景条"
    suitable_for = "教程/干货/方法论类，标题信息量大需要清晰传达"

    def render(self, base_img, headline, subtitle=None):
        img = base_img.convert("RGBA")
        W, H = img.size
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))

        font_path = find_bold_font()
        font_size = W // 11
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()

        max_chars = 8 if len(headline) > 10 else max(len(headline), 1)
        lines = _wrap_cn(headline, max_chars)
        line_height = int(font_size * 1.3)
        total_h = line_height * len(lines)
        y_start = int(H * 0.12)

        # 半透明背景条
        band_padding = int(font_size * 0.5)
        band_top = max(0, y_start - band_padding)
        band_bottom = min(H, y_start + total_h + band_padding)
        band = Image.new("RGBA", (W, band_bottom - band_top), (0, 0, 0, 110))
        overlay.paste(band, (0, band_top), band)

        draw = ImageDraw.Draw(overlay)
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (W - text_w) / 2
            y = y_start + i * line_height
            draw.text(
                (x, y), line, font=font,
                fill=(255, 255, 255, 255),
                stroke_width=max(2, font_size // 18),
                stroke_fill=(0, 0, 0, 235),
            )

        return Image.alpha_composite(img, overlay)


# =========================================================
#  Template 2: 顶部标签 + 底部大字（好物推荐类）
# =========================================================

class TopLabelTemplate(PosterTemplate):
    name = "top_label"
    description = "顶部彩色小标签 + 底部大字标题，对比鲜明"
    suitable_for = "好物推荐/测评/种草类，需要给内容贴一个标签"

    def render(self, base_img, headline, subtitle="种草测评"):
        img = base_img.convert("RGBA")
        W, H = img.size
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        bold_font = find_bold_font()
        reg_font = find_regular_font() or bold_font

        # ----- 顶部标签 -----
        tag_text = subtitle or "种草测评"
        tag_size = W // 28
        tag_font = ImageFont.truetype(reg_font, tag_size) if reg_font else ImageFont.load_default()
        tag_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
        tag_w = tag_bbox[2] - tag_bbox[0]
        tag_h = tag_bbox[3] - tag_bbox[1]
        pad_x, pad_y = int(tag_size * 0.7), int(tag_size * 0.4)
        tag_x = int(W * 0.06)
        tag_y = int(H * 0.06)
        # 圆角彩色色块
        accent_color = (255, 107, 157, 255)  # 小红书粉
        draw.rounded_rectangle(
            [tag_x, tag_y, tag_x + tag_w + 2 * pad_x, tag_y + tag_h + 2 * pad_y],
            radius=int(tag_size * 0.6),
            fill=accent_color,
        )
        draw.text(
            (tag_x + pad_x, tag_y + pad_y - tag_size // 8),
            tag_text, font=tag_font, fill=(255, 255, 255, 255),
        )

        # ----- 底部大字标题 -----
        font_size = W // 10
        font = ImageFont.truetype(bold_font, font_size) if bold_font else ImageFont.load_default()
        max_chars = 7 if len(headline) > 8 else max(len(headline), 1)
        lines = _wrap_cn(headline, max_chars)
        line_height = int(font_size * 1.2)
        total_h = line_height * len(lines)
        y_start = int(H * 0.72) - total_h

        # 底部渐变背景（增强可读性）
        gradient = Image.new("RGBA", (W, int(H * 0.45)), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gradient)
        for yy in range(gradient.height):
            alpha = int(180 * (yy / gradient.height))
            gd.line([(0, yy), (W, yy)], fill=(0, 0, 0, alpha))
        overlay.paste(gradient, (0, int(H * 0.55)), gradient)

        draw = ImageDraw.Draw(overlay)
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = int(W * 0.06)  # 左对齐
            y = y_start + i * line_height
            draw.text(
                (x, y), line, font=font,
                fill=(255, 255, 255, 255),
                stroke_width=max(2, font_size // 24),
                stroke_fill=(0, 0, 0, 200),
            )

        return Image.alpha_composite(img, overlay)


# =========================================================
#  Template 3: 极简单行（治愈/情感类）
# =========================================================

class MinimalistTemplate(PosterTemplate):
    name = "minimalist"
    description = "极简单行白字 + 柔和阴影，无背景条"
    suitable_for = "情感/治愈/生活方式类，画面留白多，文字克制"

    def render(self, base_img, headline, subtitle=None):
        img = base_img.convert("RGBA")
        W, H = img.size

        # 先做轻微模糊和压暗（让文字更突出）
        # 仅对上半部分模糊
        top_half = img.crop((0, 0, W, int(H * 0.5)))
        top_blurred = top_half.filter(ImageFilter.GaussianBlur(radius=4))
        darkening = Image.new("RGBA", top_half.size, (0, 0, 0, 60))
        top_final = Image.alpha_composite(top_blurred.convert("RGBA"), darkening)
        img.paste(top_final, (0, 0))

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))

        font_path = find_regular_font()
        font_size = W // 13
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()

        # 单行优先
        max_chars = 12 if len(headline) > 12 else max(len(headline), 1)
        lines = _wrap_cn(headline, max_chars)
        line_height = int(font_size * 1.4)
        total_h = line_height * len(lines)
        y_start = int(H * 0.18)

        # 双层阴影（柔和高级）
        shadow_offsets = [(3, 3, 100), (6, 6, 50)]
        for ox, oy, alpha in shadow_offsets:
            shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow)
            for i, line in enumerate(lines):
                bbox = sd.textbbox((0, 0), line, font=font)
                text_w = bbox[2] - bbox[0]
                x = (W - text_w) / 2 + ox
                y = y_start + i * line_height + oy
                sd.text((x, y), line, font=font, fill=(0, 0, 0, alpha))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=3))
            overlay = Image.alpha_composite(overlay, shadow)

        # 主文字
        draw = ImageDraw.Draw(overlay)
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (W - text_w) / 2
            y = y_start + i * line_height
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

        return Image.alpha_composite(img, overlay)


# =========================================================
#  Template 4: 杂志风超大字（盘点/榜单类）
# =========================================================

class MagazineCoverTemplate(PosterTemplate):
    name = "magazine_cover"
    description = "杂志封面风超大字 + 装饰线"
    suitable_for = "盘点/榜单/合集类，TOP X / N 个 等格式"

    def render(self, base_img, headline, subtitle="2024 精选"):
        img = base_img.convert("RGBA")
        W, H = img.size
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        bold = find_bold_font()
        reg = find_regular_font() or bold

        # 顶部装饰横线 + 副标题
        line_y = int(H * 0.10)
        draw.line([(int(W * 0.06), line_y), (int(W * 0.94), line_y)],
                  fill=(255, 255, 255, 200), width=2)

        sub_size = W // 30
        sub_font = ImageFont.truetype(reg, sub_size) if reg else ImageFont.load_default()
        sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        sub_w = sub_bbox[2] - sub_bbox[0]
        draw.rectangle(
            [(W - sub_w) // 2 - 12, line_y - sub_size // 2 - 2,
             (W + sub_w) // 2 + 12, line_y + sub_size // 2 + 4],
            fill=(10, 14, 39, 255),  # 与 app 暗色调一致
        )
        draw.text(
            ((W - sub_w) // 2, line_y - sub_size // 2),
            subtitle, font=sub_font, fill=(255, 255, 255, 255),
        )

        # 主标题（超大字）
        font_size = W // 8  # 极大字
        font = ImageFont.truetype(bold, font_size) if bold else ImageFont.load_default()
        max_chars = 5 if len(headline) > 6 else max(len(headline), 1)
        lines = _wrap_cn(headline, max_chars)
        line_height = int(font_size * 1.15)
        total_h = line_height * len(lines)
        y_start = int(H * 0.18)

        # 主文字带强描边
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (W - text_w) / 2
            y = y_start + i * line_height
            draw.text(
                (x, y), line, font=font,
                fill=(255, 255, 255, 255),
                stroke_width=max(3, font_size // 22),
                stroke_fill=(0, 0, 0, 240),
            )

        # 底部装饰横线
        bottom_y = y_start + total_h + int(font_size * 0.3)
        draw.line([(int(W * 0.15), bottom_y), (int(W * 0.85), bottom_y)],
                  fill=(255, 255, 255, 180), width=2)

        return Image.alpha_composite(img, overlay)


# =========================================================
#  Template Registry
# =========================================================

TEMPLATE_REGISTRY: Dict[str, PosterTemplate] = {
    "center_bold": CenterBoldTemplate(),
    "top_label": TopLabelTemplate(),
    "minimalist": MinimalistTemplate(),
    "magazine_cover": MagazineCoverTemplate(),
}


def get_template(name: str) -> PosterTemplate:
    """根据名称获取模板，未知名则用 center_bold 兜底"""
    return TEMPLATE_REGISTRY.get(name, TEMPLATE_REGISTRY["center_bold"])


def list_templates_for_llm() -> str:
    """生成给 Art Director LLM 看的模板选择菜单（中文）"""
    lines = ["可用海报模板（根据文案调性选择）："]
    for name, tpl in TEMPLATE_REGISTRY.items():
        lines.append(f"  · `{name}`: {tpl.description}（适用：{tpl.suitable_for}）")
    return "\n".join(lines)
