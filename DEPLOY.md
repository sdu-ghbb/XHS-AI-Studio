# 🚀 Xiaohongshu AI Studio · 服务器部署指南

> 目标服务器：`118.190.142.182`（公网） / `172.29.249.239`（私网）
> 本文档覆盖：影子题库构建 → 上传 → 服务器部署 → 进程守护

---

## 第一步：本地构建影子题库（不在服务器上做）

⚠️ **重要：题库构建涉及爬取，必须在你本地电脑做，不要在服务器上爬，避免服务器公网 IP 被小红书封禁。**

### 1.1 零配置快速启动（先用种子库跑通）

```bash
# 本地项目目录
pip install -r requirements.txt
python build_kb.py --seed          # 用内置 40 篇种子库构建
```

产物：`kb/shadow_kb.json`（约几百 KB）

### 1.2 正式构建（推荐：MediaCrawler 爬 5000+ 篇）

```bash
# 1. 本地 clone MediaCrawler
git clone https://github.com/NanmiCoder/MediaCrawler
cd MediaCrawler
# 按其 README 配置环境、登录小红书

# 2. 按品类分批爬取高赞笔记（建议每品类 600-1000 篇）
#    穿搭 / 护肤美妆 / 美食 / 旅行 / 家居好物 / 学习职场 / 健身减脂 / 数码
#    控制爬取频率，用家用 IP

# 3. MediaCrawler 导出 json 后，回到本项目构建
python build_kb.py --input /path/to/mediacrawler_output.json

# 增量追加（后续补充）
python build_kb.py --input new_batch.json --append
```

建议**每半个月在本地更新一次题库**——爆款底层逻辑变化慢，不需要实时。

### 1.3 把题库上传到服务器

```bash
scp kb/shadow_kb.json root@118.190.142.182:/opt/xhs_studio/kb/
```

---

## 第二步：服务器环境准备

```bash
ssh root@118.190.142.182

# Python 3.10+
apt update && apt install -y python3.10 python3.10-venv python3-pip git

# 中文字体（关键！否则海报叠字会是方框）
apt install -y fonts-noto-cjk

# 创建项目目录
mkdir -p /opt/xhs_studio && cd /opt/xhs_studio
```

---

## 第三步：部署项目

```bash
# 上传项目代码（本地执行）
scp -r ./xhs_studio/* root@118.190.142.182:/opt/xhs_studio/

# 服务器上：建虚拟环境
cd /opt/xhs_studio
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 确认 .env 已上传且 Key 正确
cat .env
```

⚠️ **生产环境不要直接传 `.env`**。更安全的做法：
```bash
# 用环境变量注入（写进 systemd 配置或 /etc/environment）
export DEEPSEEK_API_KEY=xxx
export QIANWEN_API_KEY=xxx
# ... 其余 Key
```

---

## 第四步：用 systemd 守护进程

创建 `/etc/systemd/system/xhs-studio.service`：

```ini
[Unit]
Description=Xiaohongshu AI Studio
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/xhs_studio
Environment="PATH=/opt/xhs_studio/.venv/bin"
# 如果用环境变量管理 Key，在这里加 Environment= 行
ExecStart=/opt/xhs_studio/.venv/bin/streamlit run app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动：
```bash
systemctl daemon-reload
systemctl enable xhs-studio
systemctl start xhs-studio
systemctl status xhs-studio        # 查看状态
journalctl -u xhs-studio -f        # 看实时日志
```

---

## 第五步：Nginx 反代 + HTTPS（推荐）

直接暴露 8501 端口不安全。建议加 Nginx：

```nginx
# /etc/nginx/sites-available/xhs-studio
server {
    listen 80;
    server_name 118.190.142.182;   # 有域名就换域名

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;       # Agent 跑得久，超时调大
    }
}
```

```bash
ln -s /etc/nginx/sites-available/xhs-studio /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

有域名的话用 certbot 上 HTTPS：
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

---

## 第六步：安全加固（上线必做）

### 6.1 防火墙
```bash
# 阿里云：在控制台安全组放行 80/443，关闭 8501 对公网
ufw allow 22
ufw allow 80
ufw allow 443
ufw enable
```

### 6.2 加访问密码（Streamlit 没有内置鉴权）
Streamlit 单体应用建议用 Nginx Basic Auth 临时挡一下：
```bash
apt install -y apache2-utils
htpasswd -c /etc/nginx/.htpasswd admin
```
Nginx location 里加：
```nginx
auth_basic "Restricted";
auth_basic_user_file /etc/nginx/.htpasswd;
```

> 长期方案见 `backend_architecture.md` —— 上 FastAPI + JWT。

### 6.3 API Key 配额
去 DeepSeek / 豆包 / 通义 / 智谱 / 博查 各控制台，**给每个 Key 设月度消费上限**，防止被刷爆。

---

## 验证清单

- [ ] `python build_kb.py --seed` 本地能跑通
- [ ] `kb/shadow_kb.json` 已上传服务器
- [ ] 服务器装了 `fonts-noto-cjk`（海报中文不乱码）
- [ ] `systemctl status xhs-studio` 显示 active (running)
- [ ] 浏览器访问 `http://118.190.142.182` 能打开
- [ ] 侧边栏「系统状态」显示所有 Key 已加载
- [ ] 跑一次完整生成，影子题库日志显示「向量 RAG 检索」
- [ ] 阿里云安全组已关闭 8501 公网访问
- [ ] 每个 API Key 已设月度配额

---

## 常见问题

**Q: 海报上的中文是方框？**
A: 服务器没装中文字体。`apt install -y fonts-noto-cjk` 后重启服务。

**Q: 影子题库日志显示「关键词模式」？**
A: `shadow_kb.json` 没上传或没构建。本地 `python build_kb.py --seed` 后 scp 上去。

**Q: Agent 跑到一半超时？**
A: Nginx `proxy_read_timeout` 调大到 300s；检查各 API 是否可从服务器访问。

**Q: 想换 Agent 用的模型？**
A: 改 `.env` 里的 `*_PROVIDER` 变量，重启服务即可。
