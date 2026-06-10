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
#  Template 5: 知识卡片(知识博主主打)
# =========================================================

class KnowledgeCardTemplate(PosterTemplate):
    name = "knowledge_card"
    description = "白底卡片 + 顶部主标题 + 下方 3 个干货点"
    suitable_for = "知识博主主打模板:学习/职场/技能/经验复盘类"

    def render(self, base_img, headline, subtitle="干货笔记"):
        """
        覆盖式渲染:白底卡片几乎覆盖整图,留少量底图做装饰
        headline: 主标题
        subtitle: 可以用 `|` 分隔三个要点,如 "技巧1 | 技巧2 | 技巧3"
        """
        img = base_img.convert("RGBA")
        W, H = img.size
        bold = find_bold_font()
        reg = find_regular_font() or bold

        # 半透明白色卡片(留 8% 边距让底图当装饰)
        margin = int(W * 0.06)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        card = Image.new("RGBA",
                         (W - 2 * margin, H - 2 * margin),
                         (252, 252, 250, 245))
        overlay.paste(card, (margin, margin), card)

        draw = ImageDraw.Draw(overlay)

        # ----- 顶部小标签(类别) -----
        tag_text = "KNOWLEDGE · 干货"
        tag_size = W // 38
        tag_font = ImageFont.truetype(reg, tag_size) if reg else ImageFont.load_default()
        tag_y = int(margin + W * 0.05)
        draw.text((margin + int(W * 0.05), tag_y),
                  tag_text, font=tag_font, fill=(180, 100, 200, 255))

        # 紧贴标签下方一条短装饰线
        line_y = tag_y + tag_size + 8
        draw.line([(margin + int(W * 0.05), line_y),
                   (margin + int(W * 0.18), line_y)],
                  fill=(180, 100, 200, 255), width=3)

        # ----- 主标题 -----
        font_size = W // 13
        font = ImageFont.truetype(bold, font_size) if bold else ImageFont.load_default()
        max_chars = 9 if len(headline) > 10 else max(len(headline), 1)
        lines = _wrap_cn(headline, max_chars)
        line_height = int(font_size * 1.25)

        y = line_y + int(font_size * 0.7)
        for line in lines:
            draw.text((margin + int(W * 0.05), y),
                      line, font=font, fill=(30, 30, 40, 255))
            y += line_height

        # ----- 中部分隔线 -----
        sep_y = y + int(font_size * 0.4)
        draw.line([(margin + int(W * 0.05), sep_y),
                   (W - margin - int(W * 0.05), sep_y)],
                  fill=(220, 220, 225, 255), width=1)

        # ----- 三个干货点(subtitle 用 | 切) -----
        points = [p.strip() for p in (subtitle or "").split("|") if p.strip()][:3]
        if not points:
            points = ["核心要点 1", "核心要点 2", "核心要点 3"]
        if len(points) < 3:
            # 用占位词补齐(避免布局空洞)
            points += [""] * (3 - len(points))

        bullet_size = W // 28
        bullet_font = ImageFont.truetype(reg, bullet_size) if reg else ImageFont.load_default()
        py = sep_y + int(bullet_size * 1.2)

        for i, point in enumerate(points, 1):
            if not point:
                continue
            # 圆形数字徽章
            badge_d = int(bullet_size * 1.4)
            badge_x = margin + int(W * 0.05)
            draw.ellipse(
                [badge_x, py, badge_x + badge_d, py + badge_d],
                fill=(255, 107, 157, 255),
            )
            num_font = ImageFont.truetype(bold, int(bullet_size * 0.9)) if bold else bullet_font
            num_str = str(i)
            n_bbox = draw.textbbox((0, 0), num_str, font=num_font)
            n_w = n_bbox[2] - n_bbox[0]
            n_h = n_bbox[3] - n_bbox[1]
            draw.text(
                (badge_x + (badge_d - n_w) // 2,
                 py + (badge_d - n_h) // 2 - 2),
                num_str, font=num_font, fill=(255, 255, 255, 255),
            )

            # 文本(自动换行 1-2 行)
            text_x = badge_x + badge_d + 14
            max_w_chars = 14
            wrapped = _wrap_cn(point, max_w_chars)[:2]
            for j, wline in enumerate(wrapped):
                draw.text(
                    (text_x, py + j * int(bullet_size * 1.2)),
                    wline, font=bullet_font, fill=(60, 60, 70, 255),
                )
            py += int(badge_d * 1.7)

        # ----- 底部 brand 角标 -----
        brand_size = W // 50
        brand_font = ImageFont.truetype(reg, brand_size) if reg else ImageFont.load_default()
        draw.text(
            (margin + int(W * 0.05), H - margin - brand_size - 14),
            "—— 收藏起来慢慢看 ——",
            font=brand_font, fill=(150, 150, 160, 255),
        )

        return Image.alpha_composite(img, overlay)


# =========================================================
#  Template 6: 治愈语录卡(治愈系主打)
# =========================================================

class QuoteCardTemplate(PosterTemplate):
    name = "quote_card"
    description = "大段衬线字体居中 + 风景底图 + 顶部署名"
    suitable_for = "治愈语录主打模板:情感/共鸣/晚安/毒鸡汤类"

    def render(self, base_img, headline, subtitle="—— 致 屏幕前的你"):
        img = base_img.convert("RGBA")
        W, H = img.size

        # 整体压暗,突出文字(treat 底图为氛围)
        dark = Image.new("RGBA", img.size, (0, 0, 0, 80))
        img = Image.alpha_composite(img, dark)

        # 中间区域再加更深的渐变(让文字超清晰)
        gradient = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(gradient)
        for y in range(H):
            # 中间最深,两边渐隐
            t = 1.0 - abs(y - H/2) / (H/2)
            alpha = int(70 * t)
            gd.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img, gradient)

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        reg = find_regular_font()
        bold = find_bold_font() or reg

        # ----- 顶部署名 / 引文符 -----
        sub_size = W // 40
        sub_font = ImageFont.truetype(reg, sub_size) if reg else ImageFont.load_default()
        sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        sub_w = sub_bbox[2] - sub_bbox[0]
        draw.text(((W - sub_w) // 2, int(H * 0.18)),
                  subtitle, font=sub_font,
                  fill=(255, 255, 255, 200))

        # 大引号装饰
        quote_size = W // 8
        quote_font = ImageFont.truetype(bold, quote_size) if bold else ImageFont.load_default()
        draw.text((int(W * 0.10), int(H * 0.28)),
                  '"', font=quote_font, fill=(255, 255, 255, 180))

        # ----- 主语录(自动多行) -----
        font_size = W // 16
        font = ImageFont.truetype(reg, font_size) if reg else ImageFont.load_default()
        max_chars = 14
        lines = _wrap_cn(headline, max_chars)
        line_height = int(font_size * 1.7)
        total_h = line_height * len(lines)
        y_start = int(H * 0.42) - total_h // 2

        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (W - text_w) / 2
            y = y_start + i * line_height
            # 柔和阴影
            for dx, dy, a in [(2, 2, 80)]:
                draw.text((x + dx, y + dy), line, font=font,
                          fill=(0, 0, 0, a))
            draw.text((x, y), line, font=font,
                      fill=(255, 255, 255, 255))

        # 结尾引号(右下)
        end_quote_y = y_start + total_h + int(font_size * 0.2)
        draw.text((W - int(W * 0.18), end_quote_y - quote_size // 3),
                  '"', font=quote_font, fill=(255, 255, 255, 180))

        # ----- 底部细线装饰 -----
        line_y = int(H * 0.85)
        draw.line([(int(W * 0.35), line_y), (int(W * 0.65), line_y)],
                  fill=(255, 255, 255, 150), width=1)

        return Image.alpha_composite(img, overlay)


# =========================================================
#  Template Registry
# =========================================================

TEMPLATE_REGISTRY: Dict[str, PosterTemplate] = {
    "knowledge_card": KnowledgeCardTemplate(),     # 知识博主主打 ⭐
    "quote_card": QuoteCardTemplate(),             # 治愈语录主打 ⭐
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
