<<<<<<< HEAD
# 🌸 Xiaohongshu AI Studio (v1.4)
=======
# 🌸 Xiaohongshu AI Studio
>>>>>>> adbd2e355d559df602ff3d0c025ce103cdb6f217

多 Agent 协作 · 影子题库 RAG · 小红书爆款图文生成器

**v1.4 改动**：影子题库 RAG（方案一）+ Bocha 进阶搜索（方案二）双打数据源

---

## 📁 项目结构

```
xhs_studio/
├── app.py                  # Streamlit 主程序
├── agents.py               # 4 角色 + 自检循环
├── tools.py                # 5 个 Skill：影子题库/搜索/生图/审图/合规
├── knowledge_base.py       # 🆕 影子题库 RAG 引擎（三级降级）
├── build_kb.py             # 🆕 本地建库脚本（种子库 / MediaCrawler）
├── kb/seed_notes.json      # 🆕 40 篇种子库（零配置启动）
├── examples.py             # 5 篇 Few-shot 样本
├── templates.py            # 4 套海报模板
├── prompts.py              # 分品类图像 Prompt 库
├── compliance.py           # 违禁词合规审查
├── observability.py        # Langfuse 监控
├── config.py               # 配置单一真源
├── backend_architecture.md # 上线后端架构方案
├── DEPLOY.md               # 🆕 服务器部署指南
├── .env / .env.example / .gitignore
├── requirements.txt
└── README.md
```

## 🧠 数据源策略：双打方案

```
Trend Analyst 的检索逻辑：
  ┌─ 1. ShadowKBSearch（影子题库）── 首选
  │     本地真实爆款库，零成本、100%合规、纯正小红书语料
  │     三级降级：向量RAG → 关键词匹配 → 提示改用 Bocha
  │
  └─ 2. BochaWebSearch（进阶搜索）── 补充
        自动注入"爆款拆解"限定词，专挖公众号/知乎上
        MCN 操盘手写的拆解报告，白嫖别人的千瓜数据分析
```

## 🗂️ 影子题库（方案一核心）

**思路**：小红书 80% 常青品类的爆款底层逻辑变化很慢，与其实时爬小红书
（封 IP、不合规），不如维护本地"优质历史爆款库"做 RAG。

| 项 | 选型 |
|---|---|
| 存储 | 纯 JSON + 内存检索（单机零依赖，<2万篇够用）|
| Embedding | 通义 text-embedding-v3 |
| 检索 | 余弦相似度 Top-K |
| 降级 | 向量RAG → 关键词匹配 → Bocha |

### 建库流程

```bash
# 快速启动：内置 40 篇种子库
python build_kb.py --seed

# 正式：本地用 MediaCrawler 爬 5000+ 篇（见 DEPLOY.md）
python build_kb.py --input mediacrawler_output.json
```

⚠️ 建库在**本地电脑**做，别在服务器上爬。每半个月更新一次即可。

## 🚀 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env       # 填入 5 个 Key
python build_kb.py --seed  # 构建影子题库
streamlit run app.py
```

服务器部署见 `DEPLOY.md`（含 systemd / Nginx / 安全加固）。

## 🛣️ 模型路由（9 个模型协作）

| 角色/用途 | 模型 |
|---|---|
| Trend Analyst | qwen-max |
| Copywriter | doubao-1-5-pro |
| Art Director | deepseek-chat |
| Critic | qwen-plus |
| VLM 审图 | qwen-vl-max |
| Embedding | text-embedding-v3 |
| 主力生图 | doubao-seedream-4.0 |
| 备用生图 | cogview-3-plus |
| 搜索 | bocha → duckduckgo |

## ✅ Sprint 进度

| Sprint | 状态 |
|---|---|
| Sprint 1（救命修复）| ✅ 完成 |
| Sprint 2（上线必做）| 🟡 合规✅ 监控✅ 后端架构✅ 部署文档✅ / 后端代码待 DevOps |
| Sprint 3（差异化）| 🟡 多模板✅ 组图✅ 移动端✅ 影子题库✅ / 用户画像待数据积累 |

### 仍待办
- 后端工程化（FastAPI/Celery/DB，见 backend_architecture.md）
- 影子题库扩容到 5000+ 篇（本地跑 MediaCrawler）
- 用户画像 / 风格指纹（需先积累真实用户数据）
- 用户反馈数据落库 → 文案模型微调

## 🔐 上线 Checklist

<<<<<<< HEAD
见 `DEPLOY.md`。核心：所有 Key revoke 重发、Key 设月度配额、
服务器装中文字体、关闭 8501 公网、加 Nginx 鉴权。
=======
- [CrewAI](https://crewai.com/) — 多智能体编排框架
- [DeepSeek](https://deepseek.com/) — 高性能 LLM
- [智谱 AI](https://open.bigmodel.cn/) — CogView 图像生成
- [Streamlit](https://streamlit.io/) — 快速 Web 应用框架
- [Adobe 思源黑体](https://github.com/adobe-fonts/source-han-sans) — 免费可商用的高质量中文字体
>>>>>>> adbd2e355d559df602ff3d0c025ce103cdb6f217
