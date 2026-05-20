#!/usr/bin/env python3
"""
=============================================================
小红书 AI Studio - 影子题库构建脚本
=============================================================
在【本地电脑】运行（不要在服务器上爬，避免封 IP）

用法：
    # 方式 1：用内置种子库快速构建（40 篇，立即可用）
    python build_kb.py --seed

    # 方式 2：用 MediaCrawler 爬取的数据构建（推荐，5000+ 篇）
    python build_kb.py --input mediacrawler_output.json

    # 方式 3：增量追加
    python build_kb.py --input new_notes.json --append

构建产物：kb/shadow_kb.json（含向量），上传到服务器即可

-----------------------------------------------------------
MediaCrawler 对接说明（方案一第 1 步）：
-----------------------------------------------------------
1. 在本地 clone：  git clone https://github.com/NanmiCoder/MediaCrawler
2. 按其文档配置，爬取小红书笔记（建议按品类关键词分批爬）
3. MediaCrawler 默认导出 json/csv 到 data/ 目录
4. 把导出文件整理成本脚本要求的格式（见 _normalize_mediacrawler）
   或直接用 --input 指向它的导出文件，本脚本会尽量自动适配字段

⚠️ 合规与风控提示：
   · 仅爬取公开的高赞笔记文本用于风格学习，不存储用户隐私
   · 控制爬取频率，本地家用 IP，别用服务器 IP
   · 每半个月更新一次库即可，爆款底层逻辑变化很慢
=============================================================
"""

import os
import sys
import json
import argparse
from pathlib import Path

# 确保能 import 同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from knowledge_base import embed_texts


def _normalize_mediacrawler(raw: list) -> list:
    """
    把 MediaCrawler 导出的原始数据归一化成标准格式
    MediaCrawler 小红书字段名可能是：title/desc/content/liked_count 等
    这里做尽量宽松的字段映射
    """
    normalized = []
    for i, item in enumerate(raw):
        title = (item.get("title") or item.get("note_title")
                 or item.get("display_title") or "")
        content = (item.get("desc") or item.get("content")
                   or item.get("note_desc") or item.get("text") or "")
        likes = (item.get("liked_count") or item.get("likes")
                 or item.get("like_count") or 0)
        # likes 可能是 "1.2万" 这种字符串
        if isinstance(likes, str):
            likes = _parse_count(likes)
        tags = item.get("tags") or item.get("tag_list") or []
        if isinstance(tags, str):
            tags = [t for t in tags.replace("，", ",").split(",") if t]
        category = item.get("category") or item.get("type") or "未分类"

        # 标题和正文都为空的跳过
        if not title and not content:
            continue

        normalized.append({
            "id": item.get("note_id") or item.get("id") or f"note_{i:05d}",
            "category": category,
            "title": title.strip(),
            "content": content.strip()[:600],  # 控制长度
            "likes": int(likes) if likes else 0,
            "tags": tags[:8],
        })
    return normalized


def _parse_count(s: str) -> int:
    """把 '1.2万' / '3000+' 这种字符串转成整数"""
    s = str(s).strip().replace("+", "").replace(",", "")
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        if "w" in s.lower():
            return int(float(s.lower().replace("w", "")) * 10000)
        return int(float(s))
    except Exception:
        return 0


def build(notes: list, append: bool = False):
    """对 notes 做向量化并写入 kb/shadow_kb.json"""
    os.makedirs(config.kb_dir, exist_ok=True)
    kb_path = Path(config.kb_file)

    # 增量模式：先读已有
    existing = []
    if append and kb_path.exists():
        with open(kb_path, "r", encoding="utf-8") as f:
            existing = json.load(f).get("notes", [])
        existing_ids = {n["id"] for n in existing}
        notes = [n for n in notes if n["id"] not in existing_ids]
        print(f"[build_kb] 增量模式：新增 {len(notes)} 篇（已有 {len(existing)} 篇）")

    if not notes:
        print("[build_kb] 没有需要处理的新笔记，退出")
        return

    # ----- 向量化 -----
    print(f"[build_kb] 开始向量化 {len(notes)} 篇笔记...")
    print(f"[build_kb] embedding 模型：{config.qianwen_embedding_model}")
    # 用 标题 + 正文 作为 embedding 输入
    texts = [f"{n['title']}。{n['content']}" for n in notes]

    try:
        vectors = embed_texts(texts, batch_size=10)
    except Exception as e:
        print(f"[build_kb] ❌ 向量化失败: {e}")
        print("[build_kb] 请检查 QIANWEN_API_KEY 是否有效、网络是否通畅")
        sys.exit(1)

    for note, vec in zip(notes, vectors):
        note["embedding"] = vec
    print(f"[build_kb] ✅ 向量化完成，维度 = {len(vectors[0])}")

    # ----- 写入 -----
    all_notes = existing + notes
    output = {
        "meta": {
            "version": "1.0",
            "count": len(all_notes),
            "embedding_model": config.qianwen_embedding_model,
            "embedding_dim": len(vectors[0]),
            "built_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        },
        "notes": all_notes,
    }
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    size_mb = kb_path.stat().st_size / 1024 / 1024
    print(f"[build_kb] ✅ 题库已构建：{kb_path}")
    print(f"[build_kb]    总计 {len(all_notes)} 篇，文件大小 {size_mb:.2f} MB")
    print(f"[build_kb] 👉 把这个文件上传到服务器的 kb/ 目录即可生效")


def main():
    parser = argparse.ArgumentParser(description="影子题库构建脚本")
    parser.add_argument("--seed", action="store_true",
                        help="用内置 40 篇种子库构建")
    parser.add_argument("--input", type=str,
                        help="MediaCrawler 导出的 json 文件路径")
    parser.add_argument("--append", action="store_true",
                        help="增量追加到现有题库")
    args = parser.parse_args()

    if args.seed:
        print("[build_kb] 模式：种子库构建")
        with open(config.seed_file, "r", encoding="utf-8") as f:
            notes = json.load(f)["notes"]
        build(notes, append=args.append)

    elif args.input:
        print(f"[build_kb] 模式：从 {args.input} 构建")
        with open(args.input, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # MediaCrawler 导出可能是 list 或 {data: [...]}
        if isinstance(raw, dict):
            raw = raw.get("data") or raw.get("notes") or []
        notes = _normalize_mediacrawler(raw)
        print(f"[build_kb] 归一化后有效笔记 {len(notes)} 篇")
        build(notes, append=args.append)

    else:
        parser.print_help()
        print("\n💡 快速开始：python build_kb.py --seed")


if __name__ == "__main__":
    main()
