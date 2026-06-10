# 🌸 小红书 AI Studio

AI 驱动的小红书爆款图文生成器——输入话题，自动生成文案 + 海报组图。

## ✨ 功能

- **选题 → 标题**：输入宽泛话题，AI 生成 3 个不同角度的爆款标题
- **标题 → 文案**：基于影子题库 RAG 检索 + 网络搜索，撰写地道小红书文案
- **文案 → 海报**：自动生成封面 + 3 张正文配图（SiliconFlow 生图 + Pillow 叠字）
- **质量审核**：事实核查 + 风格评分，不达标自动返修（最多 3 轮）

## 🏗️ 架构

```
用户选题
  │
  ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  Research   │ →  │  Copywriter  │ →  │   Critic    │
│  资料搜索    │    │  文案撰写     │    │  质量审核    │
│  KB + Web   │    │  合规自查     │    │  事实核查    │
└─────────────┘    └──────────────┘    └──────┬──────┘
                                              │ score ≥ 80?
                                     ┌────────┴────────┐
                                     │ YES             │ NO
                                     ▼                 ▼
                              ┌──────────┐    ┌──────────────┐
                              │  Visual  │    │ 返修 Copywriter │
                              │  海报生成 │    │ (带改进建议)    │
                              └──────────┘    └──────────────┘
```

- **编排引擎**：LangGraph StateGraph
- **LLM**：DeepSeek（_llm_call 直接调 API）
- **Embedding**：通义千问 text-embedding-v3
- **生图**：SiliconFlow Kolors
- **搜索**：Bocha + trafilatura 网页正文提取
- **前端**：纯 HTML/CSS/JS（SSE 实时日志流）
- **后端**：FastAPI + uvicorn

## 📁 项目结构

```
├── agents.py              # LangGraph 编排引擎（Research → Copy → Critic → Visual）
├── orchestrator.py        # SSE 桥接层（线程 + 队列 + 事件推送）
├── config.py              # 全局配置
├── knowledge_base.py      # 影子题库 RAG（向量检索 + 余弦相似度）
├── tools.py               # 工具集（Bocha 搜索 / SmartImagePoster 生图 / ShadowKB）
├── style.py               # 海报渲染（Pillow 叠字）
├── build_kb.py            # 本地建库脚本
├── api/
│   ├── main.py            # FastAPI 入口
│   ├── routes.py          # API 路由
│   ├── schemas.py         # Pydantic 模型
│   ├── deps.py            # 依赖注入
│   └── static/
│       └── index.html     # 前端页面
├── app.py                 # Streamlit 备用前端
├── deploy.sh              # 一键部署脚本
└── requirements.txt
```

## 🚀 本地启动

```bash
pip install -r requirements.txt
cp .env.example .env        # 填入 API Key
python build_kb.py --input crawl_merged.jsonl   # 构建向量库
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

打开 http://localhost:8000

## 🖥️ 服务器部署

```bash
# 上传文件到服务器
scp deploy.sh root@你的IP:/opt/
scp agents.py config.py ... root@你的IP:/opt/tulun/
scp -r api kb root@你的IP:/opt/tulun/

# SSH 进去执行
cd /opt && bash deploy.sh
```

服务通过 systemd 托管，崩溃自动重启。Nginx 反代 80 → 8000。

## 🔑 需要的 API Key

| Key | 用途 |
|-----|------|
| `DEEPSEEK_API_KEY` | LLM 文本生成 |
| `QIANWEN_API_KEY` | Embedding 向量化 |
| `SILICONFLOW_API_KEY` | 图像生成 |
| `BOCHA_API_KEY` | 网络搜索（可选，缺失降级 DuckDuckGo） |

在 `.env` 文件中配置。
