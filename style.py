"""
=============================================================
小红书 AI Studio - 图像风格 + 海报合成 + 生图
=============================================================
合并自：prompts.py + templates.py + tools.py 生图函数
----------------------------------------------------------
职责：
  1. STYLE_LIBRARY — 12 种视觉风格定义
  2. render_poster — 底图叠字合成海报
  3. gen_image_siliconflow — 调 SiliconFlow Kolors API 生图
=============================================================
"""

import os
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont

from config import config


# =========================================================
#  1. 生图 API 调用
# =========================================================

from tools import _request_with_retry


def gen_image_siliconflow(prompt: str) -> str:
    """SiliconFlow Kolors 生图，返回图片 URL"""
    if not config.siliconflow_api_key:
        raise RuntimeError("SILICONFLOW_API_KEY 未配置")
    data = _request_with_retry(
        "POST", f"{config.siliconflow_base_url}/images/generations",
        headers={
            "Authorization": f"Bearer {config.siliconflow_api_key}",
            "Content-Type": "application/json",
        },
        json_body={
            "model": config.siliconflow_image_model,
            "prompt": prompt,
            "image_size": "1024x1024",
            "batch_size": 1,
            "num_inference_steps": 20,
            "guidance_scale": 7.5,
        },
        timeout=60, max_retries=2, label="SiliconFlow",
    )
    return data["data"][0]["url"]




# =========================================================
#  3. 海报渲染（Pillow 叠字）
# =========================================================

_FONT_CANDIDATES = [
    "./fonts/方正粉丝天下简体.ttf",
    "./fonts/ZCOOL_XiaoWei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]

_FONT_URL = (
    "https://github.com/adobe-fonts/source-han-sans/raw/release/"
    "OTF/SimplifiedChinese/SourceHanSansSC-Bold.otf"
)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """获取中文字体"""
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    os.makedirs("./fonts", exist_ok=True)
    local = "./fonts/SourceHanSansSC-Bold.otf"
    if not Path(local).exists():
        r = requests.get(_FONT_URL, timeout=90)
        with open(local, "wb") as f:
            f.write(r.content)
    return ImageFont.truetype(local, size)


def render_poster(base_img: Image.Image, headline: str) -> Image.Image:
    """在海报底图上叠文字（带描边阴影，浅色底也看得清）"""
    img = base_img.convert("RGBA")
    W, H = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))

    font_size = W // 11
    font = _get_font(font_size)
    outline_w = max(2, font_size // 36)  # 描边宽度，随字号缩放

    max_chars = 8 if len(headline) > 10 else max(len(headline), 1)
    lines = [headline[i:i + max_chars] for i in range(0, len(headline), max_chars)]
    line_height = int(font_size * 1.3)
    y_start = int(H * 0.12)

    for i, line in enumerate(lines):
        # 先画上层 overlay，再叠到底图上，避免描边互相覆盖
        line_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        line_draw = ImageDraw.Draw(line_overlay)

        bbox = line_draw.textbbox((0, 0), line, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2
        y = y_start + i * line_height

        # 描边：在 8 个方向画半透明黑色
        for dx in (-outline_w, 0, outline_w):
            for dy in (-outline_w, 0, outline_w):
                if dx == 0 and dy == 0:
                    continue
                line_draw.text((x + dx, y + dy), line, font=font,
                               fill=(0, 0, 0, 160))

        # 主体白色文字画在最上层
        line_draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

        overlay = Image.alpha_composite(overlay, line_overlay)

    return Image.alpha_composite(img, overlay)