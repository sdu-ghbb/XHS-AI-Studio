"""
=============================================================
小红书 AI Studio - 影子题库 RAG 引擎
=============================================================
"""

import os
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import math
import time
from pathlib import Path
from typing import List, Dict, Optional

from config import config


# =========================================================
#  Embedding：通义 text-embedding
# =========================================================

def embed_texts(texts: List[str], batch_size: int = 10) -> List[List[float]]:
    """
    批量文本向量化（通义 text-embedding-v3）
    -----------------------------------
    被 build_kb.py（嵌入语料）和本模块（嵌入查询）共用
    返回每条文本对应的向量；失败抛异常由调用方处理
    """
    if not config.qianwen_api_key:
        raise RuntimeError("QIANWEN_API_KEY 未配置，无法做 embedding")

    from openai import OpenAI
    client = OpenAI(
        api_key=config.qianwen_api_key,
        base_url=config.qianwen_base_url,
        timeout=60,
    )

    all_vectors: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        # 通义 embedding 单条文本有长度限制, 截断保护
        batch = [t[:2000] for t in batch]
        resp = client.embeddings.create(
            model=config.qianwen_embedding_model,
            input=batch,
        )
        # resp.data 按输入顺序返回
        for item in sorted(resp.data, key=lambda x: x.index):
            all_vectors.append(item.embedding)
        if i + batch_size < len(texts):
            time.sleep(0.3)  # 轻微限速

    return all_vectors


# =========================================================
#  余弦相似度（利用 cos 余弦值来表征向量之间的相关度）
# =========================================================

def _cosine(v1: List[float], v2: List[float]) -> float:
    """两个向量的余弦相似度"""
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


# =========================================================
#  影子题库主类
# =========================================================

class ShadowKnowledgeBase:
    """
    影子题库
    -----------------------------------
    使用方式：
        kb = ShadowKnowledgeBase()
        if kb.is_ready():
            notes = kb.search("考研复试", top_k=20)
    """

    def __init__(self):
        self.notes: List[Dict] = []
        self.mode: str = "none"   # "vector" | "keyword" | "none"
        self.meta: Dict = {}
        self._load()

    # ---------- 加载 ----------
    def _load(self):
        kb_path = Path(config.kb_file)

        # 加载向量库
        if kb_path.exists():
            try:
                with open(kb_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                notes = data.get("notes", [])
                if notes and notes[0].get("embedding"):
                    self.notes = notes
                    self.meta = data.get("meta", {})
                    self.mode = "vector"
                    print(f"[ShadowKB] ✅ 向量库已加载：{len(notes)} 篇 "
                          f"（{self.meta.get('embedding_model', '?')}）")
                    return
            except Exception as e:
                print(f"[ShadowKB] 向量库加载失败: {e}")

        # 空
        self.mode = "none"
        print("[ShadowKB] ❌ 未发现题库，调用方需降级到 Bocha")

    def is_ready(self) -> bool:
        return self.mode in ("vector", "keyword") and len(self.notes) > 0

    # ---------- 检索 ----------
    def search(
        self,
        query: str,
        top_k: int = 20,
    ) -> List[Dict]:
        """
        检索最相关的爆款笔记
        :param query: 用户选题
        :param top_k: 返回条数
        :return: [{title, content, category, likes, score}, ...]
        """
        if not self.is_ready():
            return []

        if self.mode == "vector":
            return self._vector_search(query, self.notes, top_k)
        else:
            return self._keyword_search(query, self.notes, top_k)

    def _vector_search(self, query: str, pool: List[Dict], top_k: int) -> List[Dict]:
        """向量 RAG 检索"""
        try:
            q_vec = embed_texts([query])[0]  # 从原有二维列表结构提取一维列表数据
        except Exception as e:
            print(f"[ShadowKB] 查询向量化失败，采用关键词检索: {e}")
            return self._keyword_search(query, pool, top_k)

        scored = []
        for note in pool:
            emb = note.get("embedding")
            if not emb:
                continue
            sim = _cosine(q_vec, emb)
            scored.append((sim, note))
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for sim, note in scored[:top_k]:
            results.append({
                "title": note.get("title", ""),
                "content": note.get("content", ""),
                "category": note.get("category", ""),
                "likes": note.get("likes", 0),
                "tags": note.get("tags", []),
                "score": round(sim, 4),
            })
        return results

    def _keyword_search(self, query: str, pool: List[Dict], top_k: int) -> List[Dict]:
        q_chars = set(query)
        scored = []
        for note in pool:
            text = note.get("title", "") + note.get("content", "")
            text += " ".join(note.get("tags", []))
            overlap = len(q_chars & set(text))
            like_bonus = math.log10(max(note.get("likes", 1), 1)) / 10
            score = overlap + like_bonus
            scored.append((score, note))
        scored.sort(key=lambda x: x[0], reverse=True)  # 按照余弦相似度（评分）进行排序

        results = []
        for score, note in scored[:top_k]:
            results.append({
                "title": note.get("title", ""),
                "content": note.get("content", ""),
                "category": note.get("category", ""),
                "likes": note.get("likes", 0),
                "tags": note.get("tags", []),
                "score": round(score, 2),
            })
        return results

    # ---------- 格式化 ----------
    @staticmethod
    def format_for_agent(results: List[Dict]) -> str:
        """把检索结果格式化成适合喂给 LLM 的文本"""
        if not results:
            return "（影子题库未检索到相关爆款，建议改用网络搜索）"
        lines = [f"从影子题库检索到 {len(results)} 篇高相关真实爆款笔记：\n"]
        for i, r in enumerate(results, 1):
            lines.append(
                f"【{i}】{r['title']}（{r['category']} · {r['likes']}赞 · "
                f"相关度{r['score']}）\n{r['content']}\n"
                f"话题标签：{' '.join(r.get('tags', []))}\n"
            )
        return "\n".join(lines)

    def search_style(
        self,
        query: str,
        top_k: int = 5,
        min_likes: int = 0,
    ) -> List[Dict]:
        if not self.is_ready():
            return []

        results = self.search(query, top_k=top_k * 3)
        # 按点赞数排序，取最高赞的
        results.sort(key=lambda x: x.get("likes", 0), reverse=True)

        if min_likes > 0:
            results = [r for r in results if r.get("likes", 0) >= min_likes]

        return results[:top_k]

    @staticmethod
    def format_style_for_agent(results: List[Dict]) -> str:
        if not results:
            return "（影子题库未检索到相关爆款，请使用自身训练语料维持风格）"
        lines = ["📝 以下是从影子题库检索到的相关高赞笔记，请学习其写作风格：\n"]
        for i, r in enumerate(results, 1):
            lines.append(
                f"【范文 {i}】{r['title']} (👍{r['likes']}赞)\n"
                f"{r['content'][:500]}\n"
                f"标签：{', '.join(r.get('tags', []))}\n"
            )
        return "\n".join(lines)


_kb_instance: Optional[ShadowKnowledgeBase] = None


def get_kb() -> ShadowKnowledgeBase:  # 整个项目共用一个实例, JSON 只加载一次
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = ShadowKnowledgeBase()
    return _kb_instance


def reload_kb() -> ShadowKnowledgeBase:
    global _kb_instance
    _kb_instance = ShadowKnowledgeBase()
    return _kb_instance
