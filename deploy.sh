#!/bin/bash
# ============================================
#  TuLun AI Studio 一键部署脚本
#  在阿里云 ECS 上以 root 执行: bash deploy.sh
# ============================================
set -e

APP_DIR="/opt/tulun"
echo "🚀 TuLun AI Studio 部署开始..."

# 1. 系统依赖
echo "📦 安装系统依赖..."
apt update -qq
apt install -y -qq python3 python3-pip python3-venv nginx

# 2. 创建应用目录
mkdir -p $APP_DIR
cd $APP_DIR

# 3. 安装 Python 依赖
echo "📦 安装 Python 依赖..."
pip3 install -q fastapi uvicorn sse-starlette langgraph python-dotenv openai duckduckgo-search Pillow requests pydantic

# 4. 创建 .env 配置文件（如果你还没传 .env 文件的话）
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env 文件，请先创建 $APP_DIR/.env"
    echo "   需要配置：DEEPSEEK_API_KEY / QIANWEN_API_KEY / SILICONFLOW_API_KEY / BOCHA_API_KEY"
fi

# 5. 创建输出目录
mkdir -p $APP_DIR/outputs $APP_DIR/fonts

# 6. systemd 服务
echo "⚙️  配置 systemd 服务..."
cat > /etc/systemd/system/tulun.service << 'UNIT'
[Unit]
Description=TuLun AI Studio
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tulun
ExecStart=/usr/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable tulun

# 7. Nginx 反代
echo "⚙️  配置 Nginx..."
cat > /etc/nginx/sites-available/tulun << 'NGX'
server {
    listen 80;
    server_name _;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
NGX

ln -sf /etc/nginx/sites-available/tulun /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# 8. 启动
echo "🚀 启动服务..."
systemctl restart tulun
sleep 3
systemctl status tulun --no-pager

echo ""
echo "========================================"
echo "✅ 部署完成！"
echo "   访问: http://$(curl -s ifconfig.me)"
echo "   查看日志: journalctl -u tulun -f"
echo "   重启服务: systemctl restart tulun"
echo "========================================"
