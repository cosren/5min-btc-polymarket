#!/bin/bash
# VPS环境配置脚本
# 用于在AWS us-east-1或eu-central-1部署交易环境

set -euo pipefail

echo "=== BTC 5m Polymarket VPS Setup ==="
echo "Starting environment setup..."

# 1. 系统更新
echo "[1/8] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# 2. 安装基础工具
echo "[2/8] Installing base tools..."
sudo apt install -y \
    git \
    curl \
    wget \
    vim \
    htop \
    tmux \
    jq \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    chrony

# 3. 配置时钟同步(关键!)
echo "[3/8] Configuring NTP time synchronization..."
sudo systemctl enable chrony
sudo systemctl restart chrony
chronyc tracking

# 4. 安装Python依赖
echo "[4/8] Setting up Python virtual environment..."
cd "$(dirname "$0")/../.."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. 配置网络优化
echo "[5/8] Optimizing network settings..."
# TCP优化
sudo sysctl -w net.core.rmem_max=16777216
sudo sysctl -w net.core.wmem_max=16777216
sudo sysctl -w net.ipv4.tcp_rmem="4096 87380 16777216"
sudo sysctl -w net.ipv4.tcp_wmem="4096 87380 16777216"
sudo sysctl -w net.ipv4.tcp_congestion_control=bbr

# 6. 创建日志和数据目录
echo "[6/8] Creating directories..."
mkdir -p data/logs
mkdir -p data/historical
mkdir -p runtime
mkdir -p backups

# 7. 配置环境变量
echo "[7/8] Setting up environment variables..."
cat > .env.local << 'EOF'
# Polymarket API配置
PM_PRIVATE_KEY=
PM_FUNDER=
PM_ADDRESS=
PM_API_KEY=
PM_API_SECRET=
PM_API_PASSPHRASE=
PM_SIGNATURE_TYPE=2

# 交易配置
BTC5M_REPO=$(pwd)
BTC5M_ENV_FILE=$(pwd)/.env.local
BTC5M_RUNNER=$(pwd)/src/core/trade_runner.py

# 通知配置(可选)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF
chmod 600 .env.local
echo "Environment file created: .env.local"
echo "Please edit .env.local with your API credentials"

# 8. 创建systemd服务
echo "[8/8] Creating systemd service..."
sudo tee /etc/systemd/system/btc5m.service > /dev/null << EOF
[Unit]
Description=BTC 5m Polymarket Trading Bot
After=network.target chrony.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PYTHONUNBUFFERED=1
ExecStart=$(pwd)/.venv/bin/python $(pwd)/src/core/trade_runner.py --profile conservative
Restart=on-failure
RestartSec=10
StandardOutput=append:$(pwd)/runtime/btc5m.service.log
StandardError=append:$(pwd)/runtime/btc5m.service.error.log

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit .env.local with your API credentials"
echo "2. Test the runner: .venv/bin/python src/core/trade_runner.py --profile conservative --dry-run"
echo "3. Start the service: sudo systemctl enable btc5m && sudo systemctl start btc5m"
echo "4. Check status: sudo systemctl status btc5m"
echo "5. View logs: journalctl -u btc5m -f"
echo ""
echo "Network optimization applied:"
echo "- TCP buffer sizes increased"
echo "- BBR congestion control enabled"
echo "- NTP time synchronization configured"
echo ""
echo "Recommended: Deploy in AWS us-east-1 or eu-central-1 for lowest latency to Polymarket API
